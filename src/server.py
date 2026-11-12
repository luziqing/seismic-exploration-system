"""
SamForGeophysics — FastAPI 主入口

启动方式:
    pip install -r requirements.txt
    python src/server.py

访问: http://localhost:9339
API 文档: http://localhost:9339/docs
"""

import os
import uuid
import json as json_mod
import logging
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import numpy as np

# ── 项目路径 ──────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

WEIGHTS_PATH = DATA_DIR / "weights" / "sam3.pt"
UPLOAD_DIR = DATA_DIR / "uploads"
SGY_DIR = DATA_DIR / "sgy"
IMAGES_DIR = DATA_DIR / "images"

for d in [UPLOAD_DIR, SGY_DIR, DATA_DIR / "weights", DATA_DIR / "db",
          DATA_DIR / "npy", DATA_DIR / "zarr", DATA_DIR / "vds",
          IMAGES_DIR / "inline", IMAGES_DIR / "crossline", IMAGES_DIR / "timeslice"]:
    d.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sam3-server")

# ── 导入业务模块 ──────────────────────────────────────────────
import sam_service
import sgy_service
import npy_service
import zarr_service
import lowfreq_service
import volume_mask_service
import propagation_service
import refine_service
import validation_service
import vds_service
import database
import llm_service

# 初始化数据库
database.init_db()

# ── FastAPI 应用 ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app):
    """启动时配置 SAM3 路径（不加载模型，首次推理时懒加载）"""
    sam_service.set_weights_path(str(WEIGHTS_PATH))
    yield

app = FastAPI(title="SAM3 Seismic Segmentation Server", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件（只暴露明确的资源目录，绝不挂载仓库根目录）
app.mount("/images", StaticFiles(directory=str(IMAGES_DIR)), name="images")
# 前端静态资源 (CSS/JS)
_static_frontend = SRC_DIR / "static"
if _static_frontend.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static_frontend)), name="static")

# ── 数据模型 ──────────────────────────────────────────────────

class PredictRequest(BaseModel):
    embedding_id: str
    points: list[list[float]]
    labels: list[int]

class SliceRequest(BaseModel):
    sgy_filename: str | None = None
    inline_indices: list[int] = []
    crossline_indices: list[int] = []
    timeslice_indices: list[int] = []

class PointsBatchRequest(BaseModel):
    session_id: int
    points: list[dict]   # [{il, xl, depth, px_x, px_y, label}, ...]

class SamResultRequest(BaseModel):
    mask_path: str = ""
    score: float = 0
    mask_shape: list[int] = []


class ValidationRequest(BaseModel):
    sam_result_id: int | None = None
    predicted_mask: list[list[float]]
    ground_truth_mask: list[list[float]]
    prediction_threshold: float = 0.5
    ground_truth_threshold: float = 0.5
    acceptance: dict[str, float] = {}
    metadata: dict = {}

class LLMConfigRequest(BaseModel):
    provider: str = "local"
    api_key: str = ""
    model: str = ""
    local_url: str = ""
    system_prompt: str = ""

class LLMChatRequest(BaseModel):
    messages: list[dict]  # [{"role": "user"/"assistant"/"system", "content": "..."}]

class LLMAnalyzeRequest(BaseModel):
    image_base64: str          # 画布截图 base64 (不含 data: 前缀)
    context: dict = {}         # 切片元数据、拾取点统计、SAM3 结果等

class VdsUploadRequest(BaseModel):
    filename: str
    connection_string: str = ""  # 云端 VDS 凭证 (可选)
    convert_to_zarr: bool = False  # 是否同时转换为 Zarr

class VdsSliceRequest(BaseModel):
    inline_indices: list[int] = []
    crossline_indices: list[int] = []
    timeslice_indices: list[int] = []
    connection_string: str = ""
    channel: int = 0


# ── 启动时配置 SAM3 路径（不加载模型，首次推理时懒加载）────────────
# 已迁移到 lifespan 上下文管理器，见上方 lifespan()


# ══════════════════════════════════════════════════════════════
# 页面 & 静态文件
# ══════════════════════════════════════════════════════════════

@app.get("/")
async def serve_frontend():
    """服务前端页面 index.html"""
    index_path = BASE_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(404, f"前端文件未找到: {index_path}")
    return FileResponse(str(index_path), media_type="text/html; charset=utf-8")


# ══════════════════════════════════════════════════════════════
# SAM3 API
# ══════════════════════════════════════════════════════════════

@app.post("/api/embed")
async def embed_image(file: UploadFile = File(...)):
    ext = Path(file.filename or "image.jpg").suffix or ".jpg"
    save_path = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    try:
        save_path.write_bytes(await file.read())
        # to_thread: 模型懒加载可能阻塞几秒，不卡事件循环
        return await asyncio.to_thread(sam_service.embed_image, str(save_path))
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/predict")
async def predict_mask(req: PredictRequest):
    try:
        # to_thread: 模型懒加载或推理可能阻塞，不卡事件循环
        return await asyncio.to_thread(
            sam_service.predict_mask, req.embedding_id, req.points, req.labels
        )
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except KeyError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/status")
async def model_status():
    info = sam_service.get_device_info()
    sgy = sgy_service.get_current()
    return {
        "model_loaded": sam_service.is_loaded(),
        "model_loading": sam_service.is_loading(),
        "weights_exists": WEIGHTS_PATH.exists(),
        "gpu_available": info["gpu_available"],
        "gpu_name": info["gpu_name"],
        "sgy_loaded": sgy["sgy_path"] is not None,
        "sgy_filename": sgy.get("sgy_filename"),
        "zarr_path": sgy.get("zarr_path"),
        "openvds_available": vds_service.is_available(),
    }


@app.get("/api/devices")
async def list_devices():
    """列出可用推理设备 (CPU / GPU)"""
    return {
        "devices": sam_service.list_devices(),
        "selected": sam_service.get_selected_device(),
        "model_loaded": sam_service.is_loaded(),
    }


@app.post("/api/device")
async def set_device(device_id: str):
    """切换推理设备 (仅模型未加载时可用)"""
    try:
        return sam_service.set_device(device_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(409, str(e))


# ══════════════════════════════════════════════════════════════
# SGY API
# ══════════════════════════════════════════════════════════════

@app.post("/api/sgy/upload")
async def upload_sgy(file: UploadFile = File(...)):
    filename = file.filename or "upload.sgy"
    save_path = SGY_DIR / filename
    try:
        save_path.write_bytes(await file.read())
    except Exception as e:
        raise HTTPException(500, f"文件保存失败: {e}")

    try:
        info = sgy_service.upload_and_convert(str(save_path), filename)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # 写入数据库
    db_id = database.insert_sgy(filename, str(save_path), {
        "il_min": info["il_range"][0], "il_max": info["il_range"][1],
        "xl_min": info["xl_range"][0], "xl_max": info["xl_range"][1],
        "n_inlines": info["n_inlines"], "n_crosslines": info["n_crosslines"],
        "n_samples": info["n_samples"], "dt_us": info["dt_us"],
    })
    sgy_service._current["db_id"] = db_id

    return {**info, "db_id": db_id}


@app.get("/api/sgy/info")
async def sgy_info():
    sgy = sgy_service.get_current()
    if not sgy["sgy_path"]:
        return {"loaded": False}
    return {
        "loaded": True,
        "filename": sgy["sgy_filename"],
        "il_range": [sgy["ilines"][0], sgy["ilines"][-1]] if sgy["ilines"] else [0, 0],
        "xl_range": [sgy["xlines"][0], sgy["xlines"][-1]] if sgy["xlines"] else [0, 0],
        "n_inlines": sgy["n_inlines"],
        "n_crosslines": sgy["n_crosslines"],
        "n_samples": sgy["n_samples"],
        "dt_us": sgy["dt_us"],
        "zarr_path": sgy.get("zarr_path"),
        "npy_path": sgy.get("npy_path"),
    }


@app.get("/api/sgy/slices")
async def list_slices():
    return sgy_service.list_existing_slices()


@app.post("/api/sgy/generate_slices")
async def generate_slices(req: SliceRequest):
    try:
        return sgy_service.generate_slices(
            req.inline_indices or None,
            req.crossline_indices or None,
            req.timeslice_indices or None,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


# ══════════════════════════════════════════════════════════════
# 数据库 API — 拾取点 & SAM 结果
# ══════════════════════════════════════════════════════════════

@app.post("/api/db/session")
async def create_session(slice_id: int = 0):
    """创建或获取拾取会话"""
    sid = database.get_or_create_session(slice_id)
    return {"session_id": sid}


@app.get("/api/db/session/{session_id}/points")
async def get_points(session_id: int):
    """获取会话中的所有拾取点"""
    return {"points": database.get_points_by_session(session_id)}


@app.post("/api/db/session/{session_id}/points")
async def add_points(session_id: int, req: PointsBatchRequest):
    """批量添加拾取点"""
    count = database.insert_points_batch(session_id, req.points)
    return {"added": count}


@app.delete("/api/db/session/{session_id}/points/last")
async def delete_last_point(session_id: int):
    """撤销最后一个拾取点"""
    ok = database.delete_last_point(session_id)
    return {"deleted": ok}


@app.delete("/api/db/session/{session_id}/points")
async def clear_all_points(session_id: int):
    """清空会话中所有拾取点"""
    database.clear_points(session_id)
    return {"cleared": True}


@app.get("/api/db/session/{session_id}/sam_result")
async def get_sam_result(session_id: int):
    """获取会话中最近的 SAM 推理结果"""
    result = database.get_latest_sam_result(session_id)
    return result or {"result": None}


@app.post("/api/db/session/{session_id}/sam_result")
async def save_sam_result(session_id: int, req: SamResultRequest):
    """保存 SAM 推理结果"""
    rid = database.insert_sam_result(session_id, req.mask_path, req.score, tuple(req.mask_shape))
    return {"result_id": rid}


@app.post("/api/db/session/{session_id}/validation")
async def validate_sam_result(session_id: int, req: ValidationRequest):
    """Validate a predicted SAM mask against a ground-truth mask."""
    try:
        summary = validation_service.validate_segmentation(
            req.predicted_mask,
            req.ground_truth_mask,
            req.prediction_threshold,
            req.ground_truth_threshold,
            req.acceptance,
        )
        rid = database.insert_validation_run(
            session_id=session_id,
            summary=summary,
            sam_result_id=req.sam_result_id,
            metadata=req.metadata,
        )
        return {"validation_id": rid, "session_id": session_id, **summary}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/db/session/{session_id}/validation")
async def get_latest_validation(session_id: int):
    """Get the most recent validation result for a pick session."""
    result = database.get_latest_validation_run(session_id)
    return result or {"result": None}


@app.get("/api/db/session/{session_id}/validations")
async def list_validations(session_id: int):
    """List all validation runs for a pick session."""
    return {"runs": database.list_validation_runs(session_id)}


# ══════════════════════════════════════════════════════════════
# Zarr API — 卷数据存储管理
# ══════════════════════════════════════════════════════════════

@app.get("/api/zarr/list")
async def list_zarr():
    """列出所有已转换的 Zarr 卷"""
    return {"volumes": zarr_service.list_zarr_volumes()}


@app.get("/api/zarr/{zarr_name}/meta")
async def zarr_metadata(zarr_name: str):
    """获取 Zarr 卷元数据"""
    zarr_path = DATA_DIR / "zarr" / zarr_name
    if not zarr_path.exists():
        raise HTTPException(404, f"Zarr 卷不存在: {zarr_name}")
    return zarr_service.get_zarr_metadata(str(zarr_path))


@app.get("/api/zarr/{zarr_name}/slice/inline/{il_index}")
async def zarr_read_inline(zarr_name: str, il_index: int):
    """从 Zarr 读取 Inline 切片数据 (numpy -> list)"""
    if il_index < 0:
        raise HTTPException(400, f"索引不能为负数: {il_index}")
    zarr_path = DATA_DIR / "zarr" / zarr_name
    if not zarr_path.exists():
        raise HTTPException(404, f"Zarr 卷不存在: {zarr_name}")
    try:
        data = zarr_service.read_inline(str(zarr_path), il_index)
        return {"shape": list(data.shape), "data": data.tolist()}
    except (IndexError, KeyError) as e:
        raise HTTPException(400, f"索引越界: {e}")
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/zarr/{zarr_name}/slice/crossline/{xl_index}")
async def zarr_read_crossline(zarr_name: str, xl_index: int):
    """从 Zarr 读取 Crossline 切片数据"""
    if xl_index < 0:
        raise HTTPException(400, f"索引不能为负数: {xl_index}")
    zarr_path = DATA_DIR / "zarr" / zarr_name
    if not zarr_path.exists():
        raise HTTPException(404, f"Zarr 卷不存在: {zarr_name}")
    try:
        data = zarr_service.read_crossline(str(zarr_path), xl_index)
        return {"shape": list(data.shape), "data": data.tolist()}
    except (IndexError, KeyError) as e:
        raise HTTPException(400, f"索引越界: {e}")
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/zarr/{zarr_name}/slice/timeslice/{sample_index}")
async def zarr_read_timeslice(zarr_name: str, sample_index: int):
    """从 Zarr 读取 TimeSlice 切片数据"""
    if sample_index < 0:
        raise HTTPException(400, f"索引不能为负数: {sample_index}")
    zarr_path = DATA_DIR / "zarr" / zarr_name
    if not zarr_path.exists():
        raise HTTPException(404, f"Zarr 卷不存在: {zarr_name}")
    try:
        data = zarr_service.read_timeslice(str(zarr_path), sample_index)
        return {"shape": list(data.shape), "data": data.tolist()}
    except (IndexError, KeyError) as e:
        raise HTTPException(400, f"索引越界: {e}")
    except Exception as e:
        raise HTTPException(500, str(e))


# ══════════════════════════════════════════════════════════════
# NumPy API — memmap 二进制切片 (替代 Zarr, 更快更简单)
# ══════════════════════════════════════════════════════════════

from fastapi.responses import Response

def _npy_binary_response(data: np.ndarray) -> Response:
    """将 numpy 数组包装为二进制 float32 响应, 附带 shape 头"""
    return Response(
        content=data.astype(np.float32).tobytes(),
        media_type="application/octet-stream",
        headers={
            "X-Rows": str(data.shape[0]),
            "X-Cols": str(data.shape[1]) if len(data.shape) > 1 else "1",
        },
    )


class NpySliceEmbedRequest(BaseModel):
    direction: str
    index: int
    mode: str = "raw"   # raw | lowfreq


@app.post("/api/npy/{vol_name}/embed")
async def npy_embed_slice(vol_name: str, req: NpySliceEmbedRequest):
    """
    Embed a slice rendered on the server (grey 2-98 % stretch, uniform integer upscale) for SAM.

    The browser must not embed a canvas screenshot: it carries pick markers, the display
    colour map and SAM overlays, and SAM segments the marker instead of the geology (bug B1).
    Point prompts for this embedding are sent as image pixels: x = (col + 0.5) * scale[0],
    y = (row + 0.5) * scale[1], where (row, col) is the position in the native slice grid.
    """
    npy_dir = _npy_vol_dir(vol_name)
    if req.index < 0:
        raise HTTPException(400, f"Index must not be negative: {req.index}")
    try:
        data = _npy_slice_array(npy_dir, req.direction, req.index, req.mode)
    except (IndexError, ValueError) as e:
        raise HTTPException(400, str(e))
    img, sy, sx = propagation_service.render_slice_image(data)
    save_path = UPLOAD_DIR / f"{uuid.uuid4().hex}.png"
    img.save(save_path, "PNG")
    try:
        emb = await asyncio.to_thread(sam_service.embed_image, str(save_path))
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    return {**emb, "grid_shape": list(data.shape), "scale": [sx, sy],
            "direction": req.direction, "index": req.index, "mode": req.mode}


@app.get("/api/npy/list")
async def list_npy():
    """列出所有 NumPy 卷"""
    return {"volumes": npy_service.list_volumes()}


@app.get("/api/npy/{vol_name}/meta")
async def npy_metadata(vol_name: str):
    """获取 NumPy 卷元数据"""
    npy_dir = DATA_DIR / "npy" / vol_name
    if not npy_dir.exists():
        raise HTTPException(404, f"NumPy 卷不存在: {vol_name}")
    return npy_service.get_metadata(str(npy_dir))


_NPY_READERS = {
    "inline": npy_service.read_inline,
    "crossline": npy_service.read_crossline,
    "timeslice": npy_service.read_timeslice,
}


def _npy_dt_us(npy_dir: Path) -> int:
    try:
        return int(npy_service.get_metadata(str(npy_dir)).get("dt_us") or lowfreq_service.DEFAULT_DT_US)
    except FileNotFoundError:
        return lowfreq_service.DEFAULT_DT_US


def _npy_slice_array(npy_dir: Path, direction: str, index: int, mode: str) -> np.ndarray:
    """Raw or low-frequency slice in slice-image orientation. Raises IndexError / ValueError on bad input."""
    if mode not in lowfreq_service.SLICE_MODES:
        raise ValueError(f"Unknown mode: {mode!r} (expected one of {', '.join(lowfreq_service.SLICE_MODES)})")
    if direction not in _NPY_READERS:
        raise ValueError(f"Unknown direction: {direction!r}")
    if mode == "lowfreq" and direction == "timeslice":
        return lowfreq_service.lowfreq_timeslice(str(npy_dir / "amplitude.npy"), index, _npy_dt_us(npy_dir))
    data = _NPY_READERS[direction](str(npy_dir), index)
    if mode == "lowfreq":  # inline / crossline: rows are samples, filter along axis 0
        data = lowfreq_service.condition_slice(data, dt_us=_npy_dt_us(npy_dir), time_axis=0)
    return data


def _npy_slice_response(vol_name: str, direction: str, index: int, mode: str) -> Response:
    """Read one slice (raw or low-frequency conditioned) as binary float32 + X-Rows/X-Cols."""
    if mode not in lowfreq_service.SLICE_MODES:
        raise HTTPException(400, f"Unknown mode: {mode!r} (expected one of {', '.join(lowfreq_service.SLICE_MODES)})")
    if index < 0:
        raise HTTPException(400, f"索引不能为负数: {index}")
    npy_dir = DATA_DIR / "npy" / vol_name
    if not npy_dir.exists():
        raise HTTPException(404, f"NumPy 卷不存在: {vol_name}")
    try:
        return _npy_binary_response(_npy_slice_array(npy_dir, direction, index, mode))
    except (IndexError, ValueError) as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/npy/{vol_name}/slice/inline/{il_index}")
async def npy_read_inline(vol_name: str, il_index: int, mode: str = "raw"):
    """读取 Inline 切片 (二进制 float32); mode=lowfreq 返回低频条件化结果, 原始体不变"""
    return _npy_slice_response(vol_name, "inline", il_index, mode)


@app.get("/api/npy/{vol_name}/slice/crossline/{xl_index}")
async def npy_read_crossline(vol_name: str, xl_index: int, mode: str = "raw"):
    """读取 Crossline 切片 (二进制 float32); mode=lowfreq 同上"""
    return _npy_slice_response(vol_name, "crossline", xl_index, mode)


@app.get("/api/npy/{vol_name}/slice/timeslice/{sample_index}")
async def npy_read_timeslice(vol_name: str, sample_index: int, mode: str = "raw"):
    """读取 TimeSlice 切片 (二进制 float32); mode=lowfreq 先沿时间轴滤波整道再取样点"""
    return _npy_slice_response(vol_name, "timeslice", sample_index, mode)

# ══════════════════════════════════════════════════════════════
# 三维体 mask API — SAM 切片 mask 回映射并写入体素 mask
# ══════════════════════════════════════════════════════════════

class SliceMaskRequest(BaseModel):
    direction: str                       # inline | crossline | timeslice
    index: int                           # 切片序号 (0 基)
    mask: list[list[float]]              # SAM 返回的 2D mask (任意尺寸, 覆盖整张切片图像)
    mask_name: str = "sam_mask"
    threshold: float = 0.5
    mode: str = "replace"                # replace | union
    score: float | None = None
    points: list[dict] = []


def _npy_vol_dir(vol_name: str) -> Path:
    base = (DATA_DIR / "npy").resolve()
    p = (base / vol_name).resolve()
    if p.parent != base or not (p / "amplitude.npy").exists():
        raise HTTPException(404, f"NumPy 卷不存在: {vol_name}")
    return p


@app.post("/api/npy/{vol_name}/mask")
async def npy_write_slice_mask(vol_name: str, req: SliceMaskRequest):
    """把一张切片的 2D mask 回映射到体网格并写入体 mask"""
    npy_dir = _npy_vol_dir(vol_name)
    try:
        return volume_mask_service.write_slice_mask(
            str(npy_dir), req.mask_name, req.direction, req.index, req.mask,
            threshold=req.threshold, mode=req.mode, score=req.score, points=req.points)
    except IndexError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


class PropagateRequest(BaseModel):
    direction: str                 # 种子切片方向, 也是传播方向
    index: int                     # 种子切片序号 (0 基)
    mask_name: str = "sam_mask"
    max_il: int = 5                # IL 半宽 (inline 传播=步数上限; 其他方向=横向外扩上限)
    max_xl: int = 5                # XL 半宽
    max_vertical: int = 30         # 纵向(采样点)半宽
    min_iou: float = 0.1           # 与上一张 IoU 低于此值则停止 (防漂移)


@app.post("/api/npy/{vol_name}/propagate")
def npy_propagate(vol_name: str, req: PropagateRequest):
    """以体 mask 中的种子切片为起点, 跨切片传播 SAM 分割 (范围受 max_il/max_xl/max_vertical 限制)"""
    npy_dir = _npy_vol_dir(vol_name)
    try:
        return propagation_service.propagate(
            str(npy_dir), req.mask_name, req.direction, req.index,
            max_il=req.max_il, max_xl=req.max_xl, max_vertical=req.max_vertical, min_iou=req.min_iou)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except (IndexError, ValueError) as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(500, str(e))


@app.get("/api/npy/{vol_name}/masks")
async def npy_list_masks(vol_name: str):
    return {"masks": volume_mask_service.list_masks(str(_npy_vol_dir(vol_name)))}


@app.get("/api/npy/{vol_name}/mask/{mask_name}/info")
async def npy_mask_info(vol_name: str, mask_name: str):
    """体 mask 信息: 逐切片来源、体素数、以 il/xl/采样 表示的包围盒与质心"""
    npy_dir = _npy_vol_dir(vol_name)
    try:
        meta = npy_service.get_metadata(str(npy_dir))
        return volume_mask_service.get_mask_info(str(npy_dir), mask_name, meta)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/npy/{vol_name}/mask/{mask_name}/footprint")
async def npy_mask_footprint(vol_name: str, mask_name: str):
    """Plan view of a volume mask for the survey map: voxels per trace, binary float32 (nIL, nXL)."""
    npy_dir = _npy_vol_dir(vol_name)
    try:
        return _npy_binary_response(volume_mask_service.mask_footprint(str(npy_dir), mask_name))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/npy/{vol_name}/mask/{mask_name}/slice/{direction}/{index}")
async def npy_read_mask_slice(vol_name: str, mask_name: str, direction: str, index: int):
    """读取体 mask 的某张切片 (二进制 float32 0/1, 朝向与振幅切片一致)"""
    npy_dir = _npy_vol_dir(vol_name)
    try:
        vol = volume_mask_service.read_mask_volume(str(npy_dir), mask_name)
        if direction not in volume_mask_service.DIRECTIONS:
            raise ValueError(f"未知方向: {direction}")
        if not (0 <= index < volume_mask_service.slice_max_index(direction, vol.shape)):
            raise IndexError(f"索引 {index} 超出范围")
        view = volume_mask_service._slice_view(vol, direction, index)
        return _npy_binary_response(np.array(view, dtype=np.float32))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except (IndexError, ValueError) as e:
        raise HTTPException(400, str(e))


# ══════════════════════════════════════════════════════════════
# QC-driven refine loop (spec qc-refine-loop, Requirement 4)
# ══════════════════════════════════════════════════════════════

class RefineRequest(BaseModel):
    direction: str
    index: int
    mode: str = "raw"                    # view SAM segments; QC always uses the raw slice
    target_type: str = "deep_target"     # deep_target | fault
    points: list[list[float]]            # [[nx, ny], ...] normalised to the slice, in [0, 1]
    labels: list[int]                    # 1 include, 0 exclude
    max_rounds: int = refine_service.MAX_ROUNDS
    write_mask: bool = True


def _refine_response(run: dict) -> dict:
    """JSON-safe copy of a run: masks as 0/1 nested lists."""
    out = {k: v for k, v in run.items() if k != "rounds"}
    out["rounds"] = [{**{k: v for k, v in r.items() if k != "mask"},
                      "mask": np.asarray(r["mask"], dtype=np.uint8).tolist()} for r in run["rounds"]]
    return out


@app.post("/api/npy/{vol_name}/refine")
def npy_refine(vol_name: str, req: RefineRequest):
    """Run the QC-driven prompt loop on one slice and store the round log (sync: runs in the thread pool)."""
    npy_dir = _npy_vol_dir(vol_name)
    if req.index < 0:
        raise HTTPException(400, f"Index must not be negative: {req.index}")
    if not req.points or len(req.points) != len(req.labels):
        raise HTTPException(400, "points and labels must be non-empty and of equal length")
    if any(len(p) != 2 or not (0.0 <= p[0] <= 1.0 and 0.0 <= p[1] <= 1.0) for p in req.points):
        raise HTTPException(400, "points must be [nx, ny] pairs normalised to [0, 1]")
    if any(lb not in (0, 1) for lb in req.labels):
        raise HTTPException(400, "labels must be 0 (exclude) or 1 (include)")
    try:
        raw = _npy_slice_array(npy_dir, req.direction, req.index, "raw")
        view = raw if req.mode == "raw" else _npy_slice_array(npy_dir, req.direction, req.index, req.mode)
    except (IndexError, ValueError) as e:
        raise HTTPException(400, str(e))
    rows, cols = raw.shape
    user_points = [{"row": min(rows - 1.0, max(0.0, ny * rows - 0.5)), "col": min(cols - 1.0, max(0.0, nx * cols - 0.5)),
                    "label": int(lb), "nx": nx, "ny": ny} for (nx, ny), lb in zip(req.points, req.labels)]

    img, sy, sx = propagation_service.render_slice_image(view)
    save_path = UPLOAD_DIR / f"{uuid.uuid4().hex}.png"
    img.save(save_path, "PNG")
    try:
        emb_id = sam_service.embed_image(str(save_path))["embedding_id"]     # once for all rounds
    except RuntimeError as e:
        raise HTTPException(503, str(e))

    def segment(points_rc, labels):
        pts = [[(c + 0.5) * sx, (r + 0.5) * sy] for r, c in points_rc]
        out = sam_service.predict_mask_np(emb_id, pts, list(labels))
        return volume_mask_service.resample_mask_to_grid(out["mask"], (rows, cols))

    try:
        result = refine_service.run(raw, user_points, segment, target_type=req.target_type,
                                    direction=req.direction, max_rounds=req.max_rounds)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    finally:
        sam_service.drop_embedding(emb_id)

    truth_path = npy_dir / "truth" / f"{req.target_type}_mask.npy"
    truth = None
    if truth_path.exists():
        tv = np.load(str(truth_path), mmap_mode="r")
        truth = np.array(volume_mask_service._slice_view(tv, req.direction, req.index), dtype=bool)
    refine_service.attach_truth(result, truth)

    run_id = database.insert_refine_run(vol_name, req.direction, req.index, req.mode, req.target_type,
                                        (rows, cols), result)
    best = result["rounds"][result["best_round"] - 1]
    if req.write_mask and best["mask"].any():
        volume_mask_service.write_slice_mask(
            str(npy_dir), "sam_mask", req.direction, req.index, best["mask"].astype(np.float32),
            mode="replace", score=best["score"],
            points=[{**p, "source": f"refine_run_{run_id}_round_{best['round']}:{p['source']}"} for p in best["prompts"]])
    return _refine_response({"run_id": run_id, "volume": vol_name, "direction": req.direction, "index": req.index,
                             "mode": req.mode, "target_type": req.target_type, "grid_shape": [rows, cols],
                             **result})


@app.get("/api/refine/{run_id}")
def get_refine(run_id: int):
    run = database.get_refine_run(run_id)
    if run is None:
        raise HTTPException(404, f"Refine run not found: {run_id}")
    return _refine_response(run)

# ══════════════════════════════════════════════════════════════
# VDS API — OpenVDS 卷数据 (本地 .vds 或 S3/Azure URL)
# ══════════════════════════════════════════════════════════════

@app.get("/api/vds/status")
async def vds_status():
    """检查 OpenVDS 是否可用 + 已注册的 VDS 卷数量"""
    if not vds_service.is_available():
        return {
            "available": False,
            "message": "openvds 未安装。运行: pip install openvds",
        }
    try:
        volumes = vds_service.list_vds_volumes()
        return {"available": True, "n_volumes": len(volumes)}
    except Exception as e:
        return {"available": True, "n_volumes": 0, "error": str(e)}


@app.get("/api/vds/list")
async def list_vds():
    """列出所有本地 VDS 卷"""
    if not vds_service.is_available():
        raise HTTPException(503, "openvds 未安装")
    return {"volumes": vds_service.list_vds_volumes()}


@app.post("/api/vds/upload")
async def upload_vds(file: UploadFile = File(...), convert_to_zarr: bool = False):
    """
    上传本地 .vds / .vdso 文件。
    注意: OpenVDS 也支持 S3/Azure URL, 但需通过 connection_string 参数指定, 走 /api/vds/open 路由。
    """
    if not vds_service.is_available():
        raise HTTPException(503, "openvds 未安装, pip install openvds")

    filename = file.filename or "upload.vds"
    vds_path = DATA_DIR / "vds" / filename
    try:
        vds_path.write_bytes(await file.read())
    except Exception as e:
        raise HTTPException(500, f"文件保存失败: {e}")

    try:
        meta = vds_service.get_vds_metadata(str(vds_path))
    except Exception as e:
        raise HTTPException(400, f"无法打开 VDS: {e}")

    # 写入数据库
    db_id = database.insert_sgy(filename, str(vds_path), {
        "il_min": meta["il_range"][0], "il_max": meta["il_range"][1],
        "xl_min": meta["xl_range"][0], "xl_max": meta["xl_range"][1],
        "n_inlines": meta["n_inlines"], "n_crosslines": meta["n_crosslines"],
        "n_samples": meta["n_samples"], "dt_us": 0,
    })

    result = {
        "filename": filename,
        "vds_path": str(vds_path),
        "db_id": db_id,
        "il_range": meta["il_range"],
        "xl_range": meta["xl_range"],
        "n_inlines": meta["n_inlines"],
        "n_crosslines": meta["n_crosslines"],
        "n_samples": meta["n_samples"],
        "sample_range": meta["sample_range"],
        "channels": meta["channels"],
    }

    # 可选: 转换为 Zarr 以加速后续切片
    if convert_to_zarr:
        try:
            zarr_result = vds_service.vds_to_zarr(str(vds_path))
            result["zarr_path"] = zarr_result["zarr_path"]
            result["zarr_size_mb"] = zarr_result["size_mb"]
        except Exception as e:
            result["zarr_error"] = str(e)

    return result


@app.post("/api/vds/open")
async def open_remote_vds(req: dict):
    """
    注册一个云端 VDS URL (S3 / Azure), 返回元数据。
    不下载数据, 仅记录 URL。
    """
    if not vds_service.is_available():
        raise HTTPException(503, "openvds 未安装")

    url = req.get("url", "")
    connection_string = req.get("connection_string", "")
    if not url:
        raise HTTPException(400, "url 不能为空")

    try:
        meta = vds_service.get_vds_metadata(url, connection_string)
    except Exception as e:
        raise HTTPException(400, f"无法打开远程 VDS: {e}")

    return {
        "url": url,
        "il_range": meta["il_range"],
        "xl_range": meta["xl_range"],
        "n_inlines": meta["n_inlines"],
        "n_crosslines": meta["n_crosslines"],
        "n_samples": meta["n_samples"],
        "sample_range": meta["sample_range"],
        "channels": meta["channels"],
    }


@app.get("/api/vds/{vds_name}/meta")
async def vds_metadata(vds_name: str):
    """获取 VDS 文件的完整元数据"""
    if not vds_service.is_available():
        raise HTTPException(503, "openvds 未安装")
    vds_path = DATA_DIR / "vds" / vds_name
    if not vds_path.exists():
        raise HTTPException(404, f"VDS 文件不存在: {vds_name}")
    try:
        return vds_service.get_vds_metadata(str(vds_path))
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/vds/{vds_name}/slice/inline/{il_index}")
async def vds_read_inline(vds_name: str, il_index: int, channel: int = 0):
    """从 VDS 读取 Inline 切片数据 (numpy -> list)"""
    if not vds_service.is_available():
        raise HTTPException(503, "openvds 未安装")
    vds_path = DATA_DIR / "vds" / vds_name
    if not vds_path.exists():
        raise HTTPException(404, f"VDS 文件不存在: {vds_name}")
    try:
        data = vds_service.read_inline(str(vds_path), il_index, channel=channel)
        return {"shape": list(data.shape), "data": data.tolist()}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/vds/{vds_name}/slice/crossline/{xl_index}")
async def vds_read_crossline(vds_name: str, xl_index: int, channel: int = 0):
    """从 VDS 读取 Crossline 切片数据"""
    if not vds_service.is_available():
        raise HTTPException(503, "openvds 未安装")
    vds_path = DATA_DIR / "vds" / vds_name
    if not vds_path.exists():
        raise HTTPException(404, f"VDS 文件不存在: {vds_name}")
    try:
        data = vds_service.read_crossline(str(vds_path), xl_index, channel=channel)
        return {"shape": list(data.shape), "data": data.tolist()}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/vds/{vds_name}/slice/timeslice/{sample_index}")
async def vds_read_timeslice(vds_name: str, sample_index: int, channel: int = 0):
    """从 VDS 读取时间切片"""
    if not vds_service.is_available():
        raise HTTPException(503, "openvds 未安装")
    vds_path = DATA_DIR / "vds" / vds_name
    if not vds_path.exists():
        raise HTTPException(404, f"VDS 文件不存在: {vds_name}")
    try:
        data = vds_service.read_timeslice(str(vds_path), sample_index, channel=channel)
        return {"shape": list(data.shape), "data": data.tolist()}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/vds/{vds_name}/generate_slices")
async def vds_generate_slices(vds_name: str, req: VdsSliceRequest):
    """从 VDS 生成 Inline/XL/TimeSlice 图片 (类似 SGY generate_slices)"""
    if not vds_service.is_available():
        raise HTTPException(503, "openvds 未安装")
    vds_path = DATA_DIR / "vds" / vds_name
    if not vds_path.exists():
        raise HTTPException(404, f"VDS 文件不存在: {vds_name}")

    try:
        meta = vds_service.get_vds_metadata(str(vds_path), req.connection_string)
    except Exception as e:
        raise HTTPException(500, str(e))

    n_il, n_xl, n_samp = meta["n_inlines"], meta["n_crosslines"], meta["n_samples"]
    ilines = np.array(meta["il_coords"], dtype=np.int32)
    xlines = np.array(meta["xl_coords"], dtype=np.int32)
    samples = np.array(meta["sample_coords"], dtype=np.float64)

    if not req.inline_indices:
        idx = np.linspace(0, n_il - 1, 7, dtype=int)[1:-1]
        req.inline_indices = [int(ilines[i]) for i in idx]
    if not req.crossline_indices:
        idx = np.linspace(0, n_xl - 1, 7, dtype=int)[1:-1]
        req.crossline_indices = [int(xlines[i]) for i in idx]
    if not req.timeslice_indices:
        idx = np.linspace(0, n_samp - 1, 7, dtype=int)[1:-1]
        req.timeslice_indices = [int(samples[i]) for i in idx]

    # 复用 sgy_service 的渲染函数
    generated = {"inline": [], "crossline": [], "timeslice": []}

    for il_val in req.inline_indices:
        name = f"IL_{il_val:04d}.png"
        save_path = IMAGES_DIR / "inline" / name
        try:
            il_idx = int(np.argmin(np.abs(ilines - il_val)))
            data = vds_service.read_inline(
                str(vds_path), il_idx,
                connection_string=req.connection_string,
                channel=req.channel,
            )
            sgy_service._render_slice(
                data.T, [xlines[0], xlines[-1], samples[-1], samples[0]],
                f"Inline {il_val} (VDS)", "Crossline", "Time (ms)", save_path,
            )
            generated["inline"].append(name)
        except Exception as e:
            logger.warning("VDS Inline %d 失败: %s", il_val, e)

    for xl_val in req.crossline_indices:
        name = f"XL_{xl_val:04d}.png"
        save_path = IMAGES_DIR / "crossline" / name
        try:
            xl_idx = int(np.argmin(np.abs(xlines - xl_val)))
            data = vds_service.read_crossline(
                str(vds_path), xl_idx,
                connection_string=req.connection_string,
                channel=req.channel,
            )
            sgy_service._render_slice(
                data.T, [ilines[0], ilines[-1], samples[-1], samples[0]],
                f"Crossline {xl_val} (VDS)", "Inline", "Time (ms)", save_path,
            )
            generated["crossline"].append(name)
        except Exception as e:
            logger.warning("VDS Crossline %d 失败: %s", xl_val, e)

    for ts_val in req.timeslice_indices:
        name = f"TS_{ts_val:04d}ms.png"
        save_path = IMAGES_DIR / "timeslice" / name
        try:
            samp_idx = int(np.argmin(np.abs(samples - ts_val)))
            data = vds_service.read_timeslice(
                str(vds_path), samp_idx,
                connection_string=req.connection_string,
                channel=req.channel,
            )
            sgy_service._render_slice(
                data, [xlines[0], xlines[-1], ilines[-1], ilines[0]],
                f"TimeSlice {ts_val} ms (VDS)", "Crossline", "Inline", save_path,
            )
            generated["timeslice"].append(name)
        except Exception as e:
            logger.warning("VDS TimeSlice %d 失败: %s", ts_val, e)

    total = sum(len(v) for v in generated.values())
    return {"generated": total, "slices": generated, "source": "vds"}


# ══════════════════════════════════════════════════════════════
# LLM Chat API
# ══════════════════════════════════════════════════════════════

@app.get("/api/llm/providers")
async def list_llm_providers():
    """列出可用 LLM 提供商及默认配置"""
    return {"providers": llm_service.list_providers()}


@app.get("/api/llm/config")
async def get_llm_config():
    """获取当前 LLM 配置 (API key 脱敏)"""
    return llm_service.get_config()


@app.post("/api/llm/config")
async def update_llm_config(config: LLMConfigRequest):
    """更新 LLM 配置并保存到 data/llm_config.json"""
    try:
        return llm_service.update_config(config.model_dump())
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/llm/chat")
async def llm_chat(req: LLMChatRequest):
    """SSE 流式聊天端点"""
    async def event_stream():
        try:
            async for token in llm_service.chat(req.messages, stream=True):
                yield f"data: {json_mod.dumps({'token': token}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except ValueError as e:
            yield f"data: {json_mod.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error("LLM chat error: %s", e)
            yield f"data: {json_mod.dumps({'error': f'对话失败: {e}'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/llm/analyze")
async def llm_analyze(req: LLMAnalyzeRequest):
    """VLM 地震切片智能解读 (SSE 流式)"""
    async def event_stream():
        try:
            async for token in llm_service.analyze_image(req.image_base64, req.context):
                yield f"data: {json_mod.dumps({'token': token}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except ValueError as e:
            yield f"data: {json_mod.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error("LLM analyze error: %s", e)
            yield f"data: {json_mod.dumps({'error': f'分析失败: {e}'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ══════════════════════════════════════════════════════════════
# 启动入口
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("SAM3_HOST", "0.0.0.0")
    port = int(os.environ.get("SAM3_PORT", "9339"))
    logger.info("启动 SAM3 地震分割服务器: http://%s:%d", host, port)
    uvicorn.run(app, host=host, port=port)
