"""
SAM3 推理服务 — 模型加载、图像嵌入、点提示分割

使用 Ultralytics SAM 高层 API，兼容 SAM/SAM2/SAM3。
懒加载: 启动时不加载模型，首次调用 embed_image/predict_mask 时自动加载。
"""

import logging
import threading
from collections import OrderedDict
from pathlib import Path

import numpy as np
import torch
from PIL import Image

logger = logging.getLogger("sam3-server")

# ── 全局状态 ──────────────────────────────────────────────────
_model = None
_model_loading = False       # 正在加载中（防止并发重复加载）
_model_path: str | None = None
_selected_device = "auto"    # auto | cpu | cuda:0 | cuda:1 ...
_EMBEDDING_MAX = 50          # 最大嵌入缓存数量
_embeddings: dict = {}  # {embedding_id: {"path": str, "size": tuple}}

# 图像编码器特征缓存 (GPU 张量, 每条约数 MB): 点提示只需过解码器, 不必重复编码图像。
# 只保留最近 _FEATURE_MAX 条, 被淘汰者在 predict 时按需重新编码。
_FEATURE_MAX = 8
_features: "OrderedDict[str, object]" = OrderedDict()
# predictor 内部状态 (features/dataset) 是共享可变的, 推理必须串行
_infer_lock = threading.RLock()


def is_loaded() -> bool:
    """模型是否已加载就绪"""
    return _model is not None and not _model_loading


def is_loading() -> bool:
    """模型是否正在加载中"""
    return _model_loading


def set_weights_path(weights_path: str):
    """启动时记录权重路径（不加载模型）"""
    global _model_path
    _model_path = weights_path


def list_devices() -> list[dict]:
    """列出可用于 SAM 推理的设备"""
    devices = [{"id": "auto", "name": "Auto (GPU 优先)", "type": "auto"},
               {"id": "cpu", "name": "CPU", "type": "cpu"}]
    if torch.cuda.is_available():
        for i in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(i)
            total_mb = props.total_memory / (1024 * 1024)
            devices.append({
                "id": f"cuda:{i}",
                "name": f"GPU {i}: {props.name} ({total_mb:.0f} MB)",
                "type": "cuda",
                "index": i,
                "memory_mb": round(total_mb),
            })
    return devices


def get_selected_device() -> str:
    return _selected_device


def set_device(device_id: str) -> dict:
    """
    选择 SAM 推理设备。仅允许在模型未加载时切换，避免运行中迁移模型。
    """
    global _selected_device
    valid = {d["id"] for d in list_devices()}
    if device_id not in valid:
        raise ValueError(f"无效设备: {device_id}")
    if _model is not None:
        raise RuntimeError("SAM3 模型已加载，切换设备前请重启服务")
    _selected_device = device_id
    logger.info("SAM3 推理设备已选择: %s", device_id)
    return {"selected_device": _selected_device, "devices": list_devices()}


def ensure_loaded():
    """
    懒加载入口 — 首次调用时加载模型，后续调用直接返回。
    如果权重文件不存在或加载失败，抛出 RuntimeError。
    """
    global _model, _model_loading

    if _model is not None:
        return

    if _model_path is None:
        raise RuntimeError("权重路径未配置，请先调用 set_weights_path()")

    wp = Path(_model_path)
    if not wp.exists():
        raise RuntimeError(f"权重文件未找到: {wp}")

    _model_loading = True
    try:
        load_model(_model_path)
    finally:
        _model_loading = False


def load_model(weights_path: str):
    """内部加载函数 — 读取权重文件、根据 _selected_device 选择 GPU/CPU"""
    global _model

    logger.info("正在加载 SAM3 模型 (Ultralytics), 设备偏好: %s ...", _selected_device)
    from ultralytics import SAM

    _model = SAM(weights_path)

    # 根据 _selected_device 决定目标设备
    target_gpu = None
    if _selected_device == "cpu":
        # 强制 CPU
        logger.info("用户选择 CPU 模式")
        _model.model = _model.model.float().cpu()
        logger.info("SAM3 模型已加载到 CPU")
        return
    elif _selected_device.startswith("cuda:"):
        idx = int(_selected_device.split(":")[1])
        if torch.cuda.is_available() and idx < torch.cuda.device_count():
            target_gpu = idx
    # "auto" 或未识别 → target_gpu = None → 下面自动选 cuda:0

    if torch.cuda.is_available():
        gpu_idx = target_gpu if target_gpu is not None else 0
        gpu_total = torch.cuda.get_device_properties(gpu_idx).total_memory
        gpu_total_mb = gpu_total / (1024 * 1024)
        logger.info("GPU %d 显存: %.0f MB", gpu_idx, gpu_total_mb)

        try:
            with torch.cuda.device(gpu_idx):
                _model.model = _model.model.half().cuda(gpu_idx)
            gpu_used = torch.cuda.memory_allocated(gpu_idx) / (1024 * 1024)
            logger.info("SAM3 模型已加载到 GPU %d (fp16), 占用 %.0f MB / %.0f MB",
                        gpu_idx, gpu_used, gpu_total_mb)
        except torch.cuda.OutOfMemoryError:
            logger.warning("GPU %d 显存不足 (fp16), 回退到 CPU", gpu_idx)
            _model.model = _model.model.float().cpu()
    else:
        logger.info("SAM3 模型加载完成 (CPU 模式, 无 GPU)")


def get_device_info() -> dict:
    return {
        "gpu_available": torch.cuda.is_available(),
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    }


# ── 图像嵌入 ──────────────────────────────────────────────────

def embed_image(image_path: str) -> dict:
    """计算图像嵌入, 返回 {embedding_id, image_size}。首次调用时自动加载模型。"""
    import uuid
    import time

    t0 = time.perf_counter()
    ensure_loaded()  # 懒加载：首次调用时才加载模型
    t_load = time.perf_counter() - t0

    with Image.open(image_path) as im:
        img_size = im.size  # (w, h)

    # 只做一次图像编码并缓存特征 (原先这里跑了一次无提示"全图分割"后丢弃结果)
    t1 = time.perf_counter()
    with _infer_lock:
        feats = _encode_image(image_path)
    t_infer = time.perf_counter() - t1

    embedding_id = uuid.uuid4().hex[:12]
    _embeddings[embedding_id] = {
        "path": str(image_path),
        "size": img_size,
    }
    _store_features(embedding_id, feats)
    # LRU 淘汰：超过上限时删除最早的条目
    while len(_embeddings) > _EMBEDDING_MAX:
        oldest_key = next(iter(_embeddings))
        del _embeddings[oldest_key]
        _features.pop(oldest_key, None)
        logger.debug("淘汰旧嵌入: %s", oldest_key)
    logger.info("图像嵌入完成: id=%s, size=%s, 加载=%.2fs, 编码=%.2fs", embedding_id, img_size, t_load, t_infer)
    return {"embedding_id": embedding_id, "image_size": list(img_size)}


def get_embedding(embedding_id: str) -> dict:
    return _embeddings.get(embedding_id)


def drop_embedding(embedding_id: str):
    """释放某个嵌入 (含 GPU 特征缓存)。用于一次性使用的图像, 如跨切片传播。"""
    _embeddings.pop(embedding_id, None)
    _features.pop(embedding_id, None)


def _store_features(embedding_id: str, feats):
    _features[embedding_id] = feats
    _features.move_to_end(embedding_id)
    while len(_features) > _FEATURE_MAX:
        _features.popitem(last=False)


def _encode_image(image_path: str):
    """运行图像编码器并返回特征 (调用方需持有 _infer_lock)。"""
    pred = getattr(_model, "predictor", None)
    if pred is None:
        # predictor 在首次 predict 时才创建: 用一次带提示的预测初始化 (不依赖无提示的全图分割)
        with Image.open(image_path) as im:
            w, h = im.size
        _model.predict(source=image_path, points=[[w / 2, h / 2]], labels=[1], verbose=False)
        pred = _model.predictor
    try:
        # Ultralytics 的 set_image 不带 inference_mode: 编码器激活会挂在特征的 autograd 图上
        # (实测单次约 35 GB 显存), 这里显式关闭梯度。
        with torch.inference_mode():
            pred.set_image(image_path)
        return pred.features
    finally:
        pred.reset_image()  # 避免陈旧特征泄漏到其他图像的推理


def _empty_mask_np(image_path: str, reason: str = "") -> dict:
    with Image.open(image_path) as img:
        w, h = img.size
    if reason:
        logger.warning("No SAM mask generated: %s", reason)
    return {"mask": np.zeros((h, w), dtype=np.float32), "scores": [0.0]}


def _empty_mask_response(image_path: str, reason: str = "") -> dict:
    out = _empty_mask_np(image_path, reason)
    h, w = out["mask"].shape
    return {"mask": out["mask"].tolist(), "mask_shape": [h, w], "scores": [0.0]}


# ── 点提示分割 ────────────────────────────────────────────────

def _run_prompted(embedding_id: str, image_path: str, points, labels):
    """点提示推理, 复用缓存的编码器特征 (被淘汰则重新编码一次)。"""
    with _infer_lock:
        feats = _features.get(embedding_id)
        if feats is None and getattr(_model, "predictor", None) is not None:
            feats = _encode_image(image_path)
            _store_features(embedding_id, feats)
        pred = getattr(_model, "predictor", None)
        if pred is not None:
            pred.features = feats
        try:
            return _model.predict(
                source=image_path,
                points=[points],     # shape: [1, N, 2]
                labels=[labels],     # shape: [1, N]
                verbose=False,
            )
        finally:
            if pred is not None:
                pred.reset_image()


def predict_mask(embedding_id: str, points: list[list[float]],
                 labels: list[int]) -> dict:
    """执行 SAM3 分割推理, 返回 {mask, mask_shape, scores}。首次调用时自动加载模型。"""
    out = predict_mask_np(embedding_id, points, labels)
    return {
        "mask": out["mask"].tolist(),
        "mask_shape": [out["mask"].shape[0], out["mask"].shape[1]],
        "scores": out["scores"],
    }


def predict_mask_np(embedding_id: str, points: list[list[float]],
                    labels: list[int]) -> dict:
    """同 predict_mask, 但 mask 以 float32 ndarray 返回 (跨切片传播用, 省去 JSON/列表转换)。"""
    import time

    ensure_loaded()  # 懒加载：首次调用时才加载模型

    if embedding_id not in _embeddings:
        raise KeyError(f"无效的 embedding_id: {embedding_id}")

    info = _embeddings[embedding_id]
    image_path = info["path"]

    t0 = time.perf_counter()
    results = _run_prompted(embedding_id, image_path, points, labels)
    t_infer = time.perf_counter() - t0

    if not results or results[0].masks is None:
        return _empty_mask_np(image_path, "results empty or masks is None")

    # 提取 mask 数据
    masks_data = results[0].masks.data  # shape: [N, H, W]
    if masks_data is None:
        return _empty_mask_np(image_path, "masks.data is None")
    if getattr(masks_data, "shape", None) is None or len(masks_data.shape) < 3:
        return _empty_mask_np(image_path, f"unexpected mask shape: {getattr(masks_data, 'shape', None)}")
    if int(masks_data.shape[0]) == 0:
        return _empty_mask_np(image_path, "masks.data contains zero masks")

    # 后处理: 提取 mask、降采样
    t1 = time.perf_counter()
    # 取第一个 mask (最高置信度)
    if isinstance(masks_data, torch.Tensor):
        mask = masks_data[0].cpu().numpy().astype(np.float32)
    else:
        mask = np.array(masks_data[0], dtype=np.float32)

    # score: 优先取 boxes.conf, 回退到 masks.iou, 最后用 mask 占比估算
    score = 0.0
    boxes = getattr(results[0], "boxes", None)
    box_conf = getattr(boxes, "conf", None) if boxes is not None else None
    if box_conf is not None and len(box_conf) > 0:
        conf_arr = box_conf.cpu().numpy() if isinstance(box_conf, torch.Tensor) else np.array(box_conf)
        score = float(conf_arr[0])
    else:
        masks_obj = getattr(results[0], "masks", None)
        iou = getattr(masks_obj, "iou", None) if masks_obj is not None else None
        if iou is not None:
            iou_arr = iou.cpu().numpy() if isinstance(iou, torch.Tensor) else np.array(iou)
            if len(iou_arr) > 0:
                score = float(iou_arr[0])
    # 最终 fallback: 用 mask 非零面积占比作为置信度估计
    if score <= 0.0 and mask is not None:
        positive_ratio = float(np.mean(mask > 0.5))
        if positive_ratio > 0:
            score = min(0.5, positive_ratio)  # 保守估计，上限 0.5

    h, w = mask.shape

    # 降采样以减少传输数据量 (1024 保留更多细节, BICUBIC 更锐利)
    max_dim = 1024
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        new_w, new_h = int(w * scale), int(h * scale)
        img_pil = Image.fromarray((mask * 255).astype(np.uint8))
        img_pil = img_pil.resize((new_w, new_h), Image.BICUBIC)
        mask = np.array(img_pil).astype(np.float32) / 255.0
    t_post = time.perf_counter() - t1

    logger.info("推理完成: points=%d, mask_shape=%s, score=%.3f, 推理=%.2fs, 后处理=%.2fs",
                len(points), mask.shape, score, t_infer, t_post)

    return {"mask": mask, "scores": [score]}
