"""
SAM3 inference service: model loading, image embedding, point-prompt segmentation

Uses the high-level Ultralytics SAM API (works with SAM/SAM2/SAM3).
Lazy loading: the model is not loaded at startup but on the first embed_image/predict_mask call.
"""

import logging
import threading
from collections import OrderedDict
from pathlib import Path

import numpy as np
import torch
from PIL import Image

logger = logging.getLogger("sam3-server")

# ── Global state ──────────────────────────────────────────────
_model = None
_model_loading = False       # loading in progress (prevents concurrent duplicate loads)
_model_path: str | None = None
_selected_device = "auto"    # auto | cpu | cuda:0 | cuda:1 ...
_EMBEDDING_MAX = 50          # max number of cached embeddings
_embeddings: dict = {}  # {embedding_id: {"path": str, "size": tuple}}

# Image-encoder feature cache (GPU tensors, a few MB each): point prompts only need the decoder, so the image is not re-encoded.
# Only the latest _FEATURE_MAX entries are kept; evicted ones are re-encoded on demand at predict time.
_FEATURE_MAX = 8
_features: "OrderedDict[str, object]" = OrderedDict()
# Internal predictor state (features/dataset) is shared and mutable, so inference must be serialised
_infer_lock = threading.RLock()


def is_loaded() -> bool:
    """Whether the model is loaded and ready"""
    return _model is not None and not _model_loading


def is_loading() -> bool:
    """Whether the model is currently loading"""
    return _model_loading


def set_weights_path(weights_path: str):
    """Record the weights path at startup (does not load the model)"""
    global _model_path
    _model_path = weights_path


def list_devices() -> list[dict]:
    """List the devices available for SAM inference"""
    devices = [{"id": "auto", "name": "Auto (GPU if available)", "type": "auto"},
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
    Select the SAM inference device. Only allowed before the model is loaded, so a running model is never moved.
    """
    global _selected_device
    valid = {d["id"] for d in list_devices()}
    if device_id not in valid:
        raise ValueError(f"Invalid device: {device_id}")
    if _model is not None:
        raise RuntimeError("SAM3 is already loaded; restart the server to switch device")
    _selected_device = device_id
    logger.info("SAM3 inference device selected: %s", device_id)
    return {"selected_device": _selected_device, "devices": list_devices()}


def ensure_loaded():
    """
    Lazy-load entry point: loads the model on the first call, later calls return at once.
    Raises RuntimeError if the weights file is missing or loading fails.
    """
    global _model, _model_loading

    if _model is not None:
        return

    if _model_path is None:
        raise RuntimeError("SAM3 weights path is not configured (call set_weights_path())")

    wp = Path(_model_path)
    if not wp.exists():
        raise RuntimeError(f"SAM3 weights not found: {wp}. Download sam3.pt from https://huggingface.co/facebook/sam3 (request access first) and place it at data/weights/sam3.pt")

    _model_loading = True
    try:
        load_model(_model_path)
    finally:
        _model_loading = False


def load_model(weights_path: str):
    """Internal loader: reads the weights file and picks GPU/CPU from _selected_device"""
    global _model

    logger.info("Loading SAM3 model (Ultralytics), preferred device: %s ...", _selected_device)
    from ultralytics import SAM

    _model = SAM(weights_path)

    # Pick the target device from _selected_device
    target_gpu = None
    if _selected_device == "cpu":
        # Force CPU
        logger.info("CPU mode selected by user")
        _model.model = _model.model.float().cpu()
        logger.info("SAM3 model loaded on CPU")
        return
    elif _selected_device.startswith("cuda:"):
        idx = int(_selected_device.split(":")[1])
        if torch.cuda.is_available() and idx < torch.cuda.device_count():
            target_gpu = idx
    # "auto" or unrecognised -> target_gpu = None -> cuda:0 is picked below

    if torch.cuda.is_available():
        gpu_idx = target_gpu if target_gpu is not None else 0
        gpu_total = torch.cuda.get_device_properties(gpu_idx).total_memory
        gpu_total_mb = gpu_total / (1024 * 1024)
        logger.info("GPU %d memory: %.0f MB", gpu_idx, gpu_total_mb)

        try:
            with torch.cuda.device(gpu_idx):
                _model.model = _model.model.half().cuda(gpu_idx)
            gpu_used = torch.cuda.memory_allocated(gpu_idx) / (1024 * 1024)
            logger.info("SAM3 model loaded on GPU %d (fp16), using %.0f MB / %.0f MB",
                        gpu_idx, gpu_used, gpu_total_mb)
        except torch.cuda.OutOfMemoryError:
            logger.warning("GPU %d out of memory (fp16), falling back to CPU", gpu_idx)
            _model.model = _model.model.float().cpu()
    else:
        logger.info("SAM3 model loaded (CPU mode, no GPU)")


def get_device_info() -> dict:
    return {
        "gpu_available": torch.cuda.is_available(),
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    }


# ── Image embedding ───────────────────────────────────────────

def embed_image(image_path: str) -> dict:
    """Compute the image embedding; returns {embedding_id, image_size}. Loads the model on the first call."""
    import uuid
    import time

    t0 = time.perf_counter()
    ensure_loaded()  # lazy loading: the model is loaded on the first call
    t_load = time.perf_counter() - t0

    with Image.open(image_path) as im:
        img_size = im.size  # (w, h)

    # Encode the image once and cache the features (this used to run a prompt-free "segment everything" pass and discard the result)
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
    # LRU eviction: drop the oldest entry when over the limit
    while len(_embeddings) > _EMBEDDING_MAX:
        oldest_key = next(iter(_embeddings))
        del _embeddings[oldest_key]
        _features.pop(oldest_key, None)
        logger.debug("Evicted old embedding: %s", oldest_key)
    logger.info("Image embedded: id=%s, size=%s, load=%.2fs, encode=%.2fs", embedding_id, img_size, t_load, t_infer)
    return {"embedding_id": embedding_id, "image_size": list(img_size)}


def get_embedding(embedding_id: str) -> dict:
    return _embeddings.get(embedding_id)


def drop_embedding(embedding_id: str):
    """Release an embedding (including its GPU feature cache). Used for one-off images such as cross-slice propagation."""
    _embeddings.pop(embedding_id, None)
    _features.pop(embedding_id, None)


def _store_features(embedding_id: str, feats):
    _features[embedding_id] = feats
    _features.move_to_end(embedding_id)
    while len(_features) > _FEATURE_MAX:
        _features.popitem(last=False)


def _encode_image(image_path: str):
    """Run the image encoder and return the features (caller must hold _infer_lock)."""
    pred = getattr(_model, "predictor", None)
    if pred is None:
        # The predictor is created on the first predict: initialise it with one prompted prediction (no prompt-free full-image pass)
        with Image.open(image_path) as im:
            w, h = im.size
        _model.predict(source=image_path, points=[[w / 2, h / 2]], labels=[1], verbose=False)
        pred = _model.predictor
    try:
        # Ultralytics' set_image does not use inference_mode: encoder activations stay on the features' autograd graph
        # (measured ~35 GB of GPU memory per call), so gradients are switched off explicitly here.
        with torch.inference_mode():
            pred.set_image(image_path)
        return pred.features
    finally:
        pred.reset_image()  # keep stale features from leaking into inference on other images


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


# ── Point-prompt segmentation ────────────────────────────────

def _run_prompted(embedding_id: str, image_path: str, points, labels):
    """Point-prompt inference reusing the cached encoder features (re-encodes once if evicted)."""
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
    """Run SAM3 segmentation; returns {mask, mask_shape, scores}. Loads the model on the first call."""
    out = predict_mask_np(embedding_id, points, labels)
    return {
        "mask": out["mask"].tolist(),
        "mask_shape": [out["mask"].shape[0], out["mask"].shape[1]],
        "scores": out["scores"],
    }


def predict_mask_np(embedding_id: str, points: list[list[float]],
                    labels: list[int]) -> dict:
    """Same as predict_mask, but returns the mask as a float32 ndarray (for cross-slice propagation, skips JSON/list conversion)."""
    import time

    ensure_loaded()  # lazy loading: the model is loaded on the first call

    if embedding_id not in _embeddings:
        raise KeyError(f"Invalid embedding_id: {embedding_id}")

    info = _embeddings[embedding_id]
    image_path = info["path"]

    t0 = time.perf_counter()
    results = _run_prompted(embedding_id, image_path, points, labels)
    t_infer = time.perf_counter() - t0

    if not results or results[0].masks is None:
        return _empty_mask_np(image_path, "results empty or masks is None")

    # Extract mask data
    masks_data = results[0].masks.data  # shape: [N, H, W]
    if masks_data is None:
        return _empty_mask_np(image_path, "masks.data is None")
    if getattr(masks_data, "shape", None) is None or len(masks_data.shape) < 3:
        return _empty_mask_np(image_path, f"unexpected mask shape: {getattr(masks_data, 'shape', None)}")
    if int(masks_data.shape[0]) == 0:
        return _empty_mask_np(image_path, "masks.data contains zero masks")

    # Post-processing: extract the mask and downsample
    t1 = time.perf_counter()
    # Take the first mask (highest confidence)
    if isinstance(masks_data, torch.Tensor):
        mask = masks_data[0].cpu().numpy().astype(np.float32)
    else:
        mask = np.array(masks_data[0], dtype=np.float32)

    # score: boxes.conf first, then masks.iou, finally an estimate from the mask area fraction
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
    # Final fallback: use the non-zero mask area fraction as the confidence estimate
    if score <= 0.0 and mask is not None:
        positive_ratio = float(np.mean(mask > 0.5))
        if positive_ratio > 0:
            score = min(0.5, positive_ratio)  # conservative estimate, capped at 0.5

    h, w = mask.shape

    # Downsample to cut transfer size (1024 keeps more detail, BICUBIC is sharper)
    max_dim = 1024
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        new_w, new_h = int(w * scale), int(h * scale)
        img_pil = Image.fromarray((mask * 255).astype(np.uint8))
        img_pil = img_pil.resize((new_w, new_h), Image.BICUBIC)
        mask = np.array(img_pil).astype(np.float32) / 255.0
    t_post = time.perf_counter() - t1

    logger.info("Inference done: points=%d, mask_shape=%s, score=%.3f, infer=%.2fs, postprocess=%.2fs",
                len(points), mask.shape, score, t_infer, t_post)

    return {"mask": mask, "scores": [score]}
