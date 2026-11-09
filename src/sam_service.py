"""
SAM3 推理服务 — 模型加载、图像嵌入、点提示分割

使用 Ultralytics SAM 高层 API，兼容 SAM/SAM2/SAM3。
懒加载: 启动时不加载模型，首次调用 embed_image/predict_mask 时自动加载。
"""

import logging
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

    img = Image.open(image_path).convert("RGB")
    img_size = img.size  # (w, h)

    # 用 predict 触发图像嵌入 (首次会初始化 predictor)
    t1 = time.perf_counter()
    _model.predict(source=image_path, verbose=False)
    t_infer = time.perf_counter() - t1

    embedding_id = uuid.uuid4().hex[:12]
    _embeddings[embedding_id] = {
        "path": str(image_path),
        "size": img_size,
    }
    # LRU 淘汰：超过上限时删除最早的条目
    while len(_embeddings) > _EMBEDDING_MAX:
        oldest_key = next(iter(_embeddings))
        del _embeddings[oldest_key]
        logger.debug("淘汰旧嵌入: %s", oldest_key)
    logger.info("图像嵌入完成: id=%s, size=%s, 加载=%.2fs, 推理=%.2fs", embedding_id, img_size, t_load, t_infer)
    return {"embedding_id": embedding_id, "image_size": list(img_size)}


def get_embedding(embedding_id: str) -> dict:
    return _embeddings.get(embedding_id)


def _empty_mask_response(image_path: str, reason: str = "") -> dict:
    img = Image.open(image_path)
    h, w = img.size[1], img.size[0]
    empty = np.zeros((h, w), dtype=np.float32)
    if reason:
        logger.warning("No SAM mask generated: %s", reason)
    return {"mask": empty.tolist(), "mask_shape": [h, w], "scores": [0.0]}


# ── 点提示分割 ────────────────────────────────────────────────

def predict_mask(embedding_id: str, points: list[list[float]],
                 labels: list[int]) -> dict:
    """执行 SAM3 分割推理, 返回 {mask, mask_shape, scores}。首次调用时自动加载模型。"""
    import time

    ensure_loaded()  # 懒加载：首次调用时才加载模型

    if embedding_id not in _embeddings:
        raise KeyError(f"无效的 embedding_id: {embedding_id}")

    info = _embeddings[embedding_id]
    image_path = info["path"]

    # 使用 Ultralytics 高层 API: 传入 points + labels
    t0 = time.perf_counter()
    results = _model.predict(
        source=image_path,
        points=[points],     # shape: [1, N, 2]
        labels=[labels],      # shape: [1, N]
        verbose=False,
    )
    t_infer = time.perf_counter() - t0

    if not results or results[0].masks is None:
        return _empty_mask_response(image_path, "results empty or masks is None")

    # 提取 mask 数据
    masks_data = results[0].masks.data  # shape: [N, H, W]
    if masks_data is None:
        return _empty_mask_response(image_path, "masks.data is None")
    if getattr(masks_data, "shape", None) is None or len(masks_data.shape) < 3:
        return _empty_mask_response(image_path, f"unexpected mask shape: {getattr(masks_data, 'shape', None)}")
    if int(masks_data.shape[0]) == 0:
        return _empty_mask_response(image_path, "masks.data contains zero masks")

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

    return {
        "mask": mask.tolist(),
        "mask_shape": [mask.shape[0], mask.shape[1]],
        "scores": [score],
    }
