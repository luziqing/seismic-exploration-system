"""sam_service: 图像编码必须在 inference_mode 下运行 (桩模型, 不需 GPU / 权重)

回归: Ultralytics 的 Predictor.set_image 不带 inference_mode, 缓存的特征会挂着编码器的
autograd 图, 实测单次嵌入约 35 GB 显存, predict 约 3 s, 跨切片传播因此失效。
"""
import sys
from pathlib import Path

import numpy as np
import pytest
import torch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import sam_service  # noqa: E402


class _StubPredictor:
    def __init__(self):
        self.features = None
        self.inference_mode_seen = None

    def set_image(self, path):
        self.inference_mode_seen = torch.is_inference_mode_enabled()
        w = torch.ones(4, requires_grad=True)
        self.features = {"image_embed": w * 2, "high_res_feats": []}

    def reset_image(self):
        self.features = None


class _StubModel:
    def __init__(self):
        self.predictor = _StubPredictor()


@pytest.fixture()
def stub_model(monkeypatch):
    m = _StubModel()
    monkeypatch.setattr(sam_service, "_model", m)
    monkeypatch.setattr(sam_service, "_features", type(sam_service._features)())
    monkeypatch.setattr(sam_service, "_embeddings", {})
    return m


def test_encode_image_runs_without_autograd(stub_model, tmp_path):
    img = tmp_path / "s.png"
    Image.fromarray(np.zeros((8, 4), dtype=np.uint8)).save(img)
    feats = sam_service._encode_image(str(img))
    assert stub_model.predictor.inference_mode_seen is True
    assert feats["image_embed"].requires_grad is False
    assert stub_model.predictor.features is None  # 共享 predictor 状态已复位


def test_embed_caches_features_and_drop_releases(stub_model, tmp_path):
    img = tmp_path / "s.png"
    Image.fromarray(np.zeros((8, 4), dtype=np.uint8)).save(img)
    emb = sam_service.embed_image(str(img))
    eid = emb["embedding_id"]
    assert emb["image_size"] == [4, 8]
    assert eid in sam_service._features
    sam_service.drop_embedding(eid)
    assert eid not in sam_service._features and sam_service.get_embedding(eid) is None
