"""
Unit tests for SAM3 seismic segmentation system.

Tests cover:
  - database.py  : SQLite CRUD operations
  - npy_service.py : NumPy memmap volume storage
  - zarr_service.py : Zarr volume storage

Usage:
  pytest tests/test_core.py -v
"""

import sys
from pathlib import Path

# Ensure src/ is on the import path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import json
import sqlite3
import numpy as np
import pytest

# ---------------------------------------------------------------------------
# database.py tests
# ---------------------------------------------------------------------------

class TestDatabase:
    """Tests for src/database.py using a temporary SQLite database."""

    @pytest.fixture(autouse=True)
    def _patch_db(self, tmp_path, monkeypatch):
        """Redirect all database operations to a temporary file."""
        import database
        db_path = tmp_path / "test_seismic.db"
        monkeypatch.setattr(database, "DB_PATH", db_path)

    # -- init_db --

    def test_init_db_creates_tables(self):
        import database
        database.init_db()
        conn = database.get_conn()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        conn.close()
        table_names = {t["name"] for t in tables}
        assert {"sgy_files", "slices", "pick_sessions", "points", "sam_results", "sam_validation_runs"} <= table_names

    def test_init_db_is_idempotent(self):
        import database
        database.init_db()
        database.init_db()  # second call should not raise
        conn = database.get_conn()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        conn.close()
        assert len(tables) >= 5

    # -- insert_sgy / get_latest_sgy --

    def test_insert_and_get_latest_sgy(self):
        import database
        database.init_db()
        info = {
            "il_min": 100, "il_max": 200,
            "xl_min": 300, "xl_max": 400,
            "n_inlines": 101, "n_crosslines": 101,
            "n_samples": 500, "dt_us": 4000,
        }
        rid = database.insert_sgy("test.sgy", "/data/test.sgy", info)
        assert rid > 0

        latest = database.get_latest_sgy()
        assert latest is not None
        assert latest["filename"] == "test.sgy"
        assert latest["il_min"] == 100
        assert latest["il_max"] == 200
        assert latest["n_inlines"] == 101
        assert latest["dt_us"] == 4000

    def test_get_latest_sgy_returns_none_when_empty(self):
        import database
        database.init_db()
        assert database.get_latest_sgy() is None

    def test_insert_sgy_with_defaults(self):
        import database
        database.init_db()
        rid = database.insert_sgy("empty.sgy", "/data/empty.sgy", {})
        latest = database.get_latest_sgy()
        assert latest["filename"] == "empty.sgy"
        assert latest["il_min"] == 0
        assert latest["n_samples"] == 0

    # -- create_session / get_or_create_session --

    def test_create_session(self):
        import database
        database.init_db()
        sid = database.create_session(slice_id=1, name="test_session")
        assert sid > 0

    def test_get_or_create_session_creates_new(self):
        import database
        database.init_db()
        sid = database.get_or_create_session(slice_id=42)
        assert sid > 0

    def test_get_or_create_session_returns_existing(self):
        import database
        database.init_db()
        sid1 = database.get_or_create_session(slice_id=10)
        sid2 = database.get_or_create_session(slice_id=10)
        assert sid1 == sid2

    # -- insert_point / get_points_by_session --

    def test_insert_point_and_retrieve(self):
        import database
        database.init_db()
        sid = database.create_session(slice_id=1)
        pid = database.insert_point(sid, il=150.0, xl=250.0, depth=1000.0,
                                     px_x=10.5, px_y=20.5, label=1)
        assert pid > 0

        pts = database.get_points_by_session(sid)
        assert len(pts) == 1
        assert pts[0]["il"] == 150.0
        assert pts[0]["xl"] == 250.0
        assert pts[0]["depth"] == 1000.0
        assert pts[0]["label"] == 1

    def test_insert_multiple_points(self):
        import database
        database.init_db()
        sid = database.create_session(slice_id=1)
        for i in range(5):
            database.insert_point(sid, il=float(i), xl=float(i * 10),
                                  depth=500.0, label=1 if i % 2 == 0 else 0)
        pts = database.get_points_by_session(sid)
        assert len(pts) == 5
        assert pts[0]["label"] == 1
        assert pts[1]["label"] == 0

    def test_insert_points_batch(self):
        import database
        database.init_db()
        sid = database.create_session(slice_id=1)
        batch = [
            {"il": 1.0, "xl": 2.0, "depth": 100.0, "px_x": 0, "px_y": 0, "label": 1},
            {"il": 3.0, "xl": 4.0, "depth": 200.0, "px_x": 0, "px_y": 0, "label": 0},
            {"il": 5.0, "xl": 6.0, "depth": 300.0, "px_x": 0, "px_y": 0, "label": 1},
        ]
        database.insert_points_batch(sid, batch)
        # insert_points_batch uses changes() after commit which may not reflect
        # all rows; verify by querying instead
        pts = database.get_points_by_session(sid)
        assert len(pts) == 3
        assert pts[0]["il"] == 1.0
        assert pts[2]["depth"] == 300.0

    def test_get_points_empty_session(self):
        import database
        database.init_db()
        sid = database.create_session(slice_id=1)
        pts = database.get_points_by_session(sid)
        assert pts == []

    # -- delete_last_point --

    def test_delete_last_point(self):
        import database
        database.init_db()
        sid = database.create_session(slice_id=1)
        database.insert_point(sid, il=1.0, xl=2.0, depth=100.0, label=1)
        database.insert_point(sid, il=3.0, xl=4.0, depth=200.0, label=0)

        deleted = database.delete_last_point(sid)
        assert deleted is True

        pts = database.get_points_by_session(sid)
        assert len(pts) == 1
        assert pts[0]["il"] == 1.0

    def test_delete_last_point_empty_returns_false(self):
        import database
        database.init_db()
        sid = database.create_session(slice_id=1)
        deleted = database.delete_last_point(sid)
        assert deleted is False

    # -- clear_points --

    def test_clear_points(self):
        import database
        database.init_db()
        sid = database.create_session(slice_id=1)
        database.insert_point(sid, il=1.0, xl=2.0, depth=100.0, label=1)
        database.insert_point(sid, il=3.0, xl=4.0, depth=200.0, label=0)

        database.clear_points(sid)
        pts = database.get_points_by_session(sid)
        assert len(pts) == 0

    def test_clear_points_empty_session(self):
        import database
        database.init_db()
        sid = database.create_session(slice_id=1)
        database.clear_points(sid)  # should not raise
        assert database.get_points_by_session(sid) == []

    # -- insert_sam_result / get_latest_sam_result --

    def test_insert_and_get_sam_result(self):
        import database
        database.init_db()
        sid = database.create_session(slice_id=1)
        rid = database.insert_sam_result(sid, mask_path="/masks/test.png",
                                          score=0.95, mask_shape=(256, 256))
        assert rid > 0

        result = database.get_latest_sam_result(sid)
        assert result is not None
        assert result["mask_path"] == "/masks/test.png"
        assert result["score"] == 0.95
        assert json.loads(result["mask_shape"]) == [256, 256]

    def test_get_latest_sam_result_returns_none_when_empty(self):
        import database
        database.init_db()
        sid = database.create_session(slice_id=1)
        assert database.get_latest_sam_result(sid) is None

    def test_get_latest_sam_result_returns_most_recent(self):
        import database
        database.init_db()
        sid = database.create_session(slice_id=1)
        database.insert_sam_result(sid, "/masks/first.png", 0.80, (128, 128))
        database.insert_sam_result(sid, "/masks/second.png", 0.92, (256, 256))

        result = database.get_latest_sam_result(sid)
        assert result is not None
        assert result["mask_path"] == "/masks/second.png"
        assert result["score"] == 0.92

    def test_insert_and_get_validation_run(self):
        import database
        import validation_service

        database.init_db()
        sid = database.create_session(slice_id=1)
        summary = validation_service.validate_segmentation(
            [[1, 1], [0, 0]],
            [[1, 0], [1, 0]],
            acceptance={"dice": 0.5, "iou": 0.3},
        )

        rid = database.insert_validation_run(sid, summary, metadata={"slice_key": "inline:150"})
        assert rid > 0

        result = database.get_latest_validation_run(sid)
        assert result is not None
        assert result["metrics"]["dice"] == pytest.approx(0.5)
        assert result["metrics"]["iou"] == pytest.approx(1 / 3)
        assert result["confusion"] == {
            "tp": 1,
            "fp": 1,
            "tn": 1,
            "fn": 1,
            "total": 4,
            "predicted_positive": 2,
            "ground_truth_positive": 2,
        }
        assert result["passed"] is True
        assert result["metadata"]["slice_key"] == "inline:150"

    def test_list_validation_runs_returns_newest_first(self):
        import database
        import validation_service

        database.init_db()
        sid = database.create_session(slice_id=1)
        summary1 = validation_service.validate_segmentation([[1]], [[1]])
        summary2 = validation_service.validate_segmentation([[0]], [[1]])

        first_id = database.insert_validation_run(sid, summary1, metadata={"name": "first"})
        second_id = database.insert_validation_run(sid, summary2, metadata={"name": "second"})

        runs = database.list_validation_runs(sid)
        assert [run["id"] for run in runs] == [second_id, first_id]
        assert runs[0]["metadata"]["name"] == "second"

    # -- insert_slice / get_slices_by_category --

    def test_insert_slice_and_get_by_category(self):
        import database
        database.init_db()
        info = {"il_min": 1, "il_max": 10, "xl_min": 1, "xl_max": 10,
                "n_inlines": 10, "n_crosslines": 10, "n_samples": 100, "dt_us": 4000}
        sgy_id = database.insert_sgy("test.sgy", "/data/test.sgy", info)

        database.insert_slice(sgy_id, "inline", 150, "/images/inline/150.png")
        database.insert_slice(sgy_id, "inline", 151, "/images/inline/151.png")
        database.insert_slice(sgy_id, "crossline", 200, "/images/crossline/200.png")

        inline_slices = database.get_slices_by_category("inline")
        assert len(inline_slices) == 2
        assert inline_slices[0]["index_value"] == 150

        xl_slices = database.get_slices_by_category("crossline")
        assert len(xl_slices) == 1


# ---------------------------------------------------------------------------
# npy_service.py tests
# ---------------------------------------------------------------------------

class TestNpyService:
    """Tests for src/npy_service.py using synthetic NumPy volumes."""

    @pytest.fixture(autouse=True)
    def _patch_paths(self, tmp_path, monkeypatch):
        """Redirect npy_service paths to a temporary directory."""
        import npy_service
        npy_dir = tmp_path / "npy"
        npy_dir.mkdir()
        monkeypatch.setattr(npy_service, "NPY_DIR", npy_dir)
        self.npy_dir = npy_dir

    def _create_test_volume(self, name="test_vol", shape=(5, 8, 10)):
        """Helper: create a synthetic numpy volume with metadata."""
        import npy_service
        vol_dir = self.npy_dir / name
        vol_dir.mkdir(parents=True, exist_ok=True)

        data = np.random.default_rng(42).standard_normal(shape).astype(np.float32)
        np.save(str(vol_dir / "amplitude.npy"), data)

        il_start, xl_start = 100, 200
        meta = {
            "source_file": f"{name}.sgy",
            "il_range": [il_start, il_start + shape[0] - 1],
            "xl_range": [xl_start, xl_start + shape[1] - 1],
            "ilines": list(range(il_start, il_start + shape[0])),
            "xlines": list(range(xl_start, xl_start + shape[1])),
            "samples": list(range(shape[2])),
            "n_inlines": shape[0],
            "n_crosslines": shape[1],
            "n_samples": shape[2],
            "dt_us": 4000,
            "shape": list(shape),
        }
        (vol_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        return vol_dir, data

    # -- read_inline --

    def test_read_inline_shape(self):
        import npy_service
        vol_dir, data = self._create_test_volume(shape=(5, 8, 10))
        result = npy_service.read_inline(str(vol_dir), il_index=0)
        # Should be (nSamples, nXL) = (10, 8)
        assert result.shape == (10, 8)

    def test_read_inline_values(self):
        import npy_service
        vol_dir, data = self._create_test_volume(shape=(3, 4, 6))
        result = npy_service.read_inline(str(vol_dir), il_index=1)
        # data[1] shape = (4, 6), transposed = (6, 4)
        expected = data[1].T.copy()
        np.testing.assert_array_equal(result, expected)

    def test_read_inline_out_of_bounds_raises(self):
        import npy_service
        vol_dir, _ = self._create_test_volume(shape=(5, 8, 10))
        with pytest.raises(IndexError, match="Inline 索引"):
            npy_service.read_inline(str(vol_dir), il_index=5)
        with pytest.raises(IndexError, match="Inline 索引"):
            npy_service.read_inline(str(vol_dir), il_index=-1)

    # -- read_crossline --

    def test_read_crossline_shape(self):
        import npy_service
        vol_dir, _ = self._create_test_volume(shape=(5, 8, 10))
        result = npy_service.read_crossline(str(vol_dir), xl_index=0)
        # Should be (nSamples, nIL) = (10, 5)
        assert result.shape == (10, 5)

    def test_read_crossline_values(self):
        import npy_service
        vol_dir, data = self._create_test_volume(shape=(3, 4, 6))
        result = npy_service.read_crossline(str(vol_dir), xl_index=2)
        expected = data[:, 2, :].T.copy()
        np.testing.assert_array_equal(result, expected)

    def test_read_crossline_out_of_bounds_raises(self):
        import npy_service
        vol_dir, _ = self._create_test_volume(shape=(5, 8, 10))
        with pytest.raises(IndexError, match="Crossline 索引"):
            npy_service.read_crossline(str(vol_dir), xl_index=8)
        with pytest.raises(IndexError, match="Crossline 索引"):
            npy_service.read_crossline(str(vol_dir), xl_index=-1)

    # -- read_timeslice --

    def test_read_timeslice_shape(self):
        import npy_service
        vol_dir, _ = self._create_test_volume(shape=(5, 8, 10))
        result = npy_service.read_timeslice(str(vol_dir), sample_index=0)
        # Should be (nIL, nXL) = (5, 8)
        assert result.shape == (5, 8)

    def test_read_timeslice_values(self):
        import npy_service
        vol_dir, data = self._create_test_volume(shape=(3, 4, 6))
        result = npy_service.read_timeslice(str(vol_dir), sample_index=3)
        expected = data[:, :, 3]
        np.testing.assert_array_equal(result, expected)

    def test_read_timeslice_out_of_bounds_raises(self):
        import npy_service
        vol_dir, _ = self._create_test_volume(shape=(5, 8, 10))
        with pytest.raises(IndexError, match="TimeSlice 索引"):
            npy_service.read_timeslice(str(vol_dir), sample_index=10)
        with pytest.raises(IndexError, match="TimeSlice 索引"):
            npy_service.read_timeslice(str(vol_dir), sample_index=-1)

    # -- get_metadata --

    def test_get_metadata_returns_expected_keys(self):
        import npy_service
        vol_dir, _ = self._create_test_volume()
        meta = npy_service.get_metadata(str(vol_dir))
        assert "il_range" in meta
        assert "xl_range" in meta
        assert "n_inlines" in meta
        assert "n_crosslines" in meta
        assert "n_samples" in meta
        assert "dt_us" in meta
        assert "shape" in meta

    def test_get_metadata_values(self):
        import npy_service
        vol_dir, _ = self._create_test_volume(shape=(5, 8, 10))
        meta = npy_service.get_metadata(str(vol_dir))
        assert meta["n_inlines"] == 5
        assert meta["n_crosslines"] == 8
        assert meta["n_samples"] == 10
        assert meta["shape"] == [5, 8, 10]
        assert meta["il_range"] == [100, 104]
        assert meta["xl_range"] == [200, 207]

    def test_get_metadata_missing_file_raises(self, tmp_path):
        import npy_service
        with pytest.raises(FileNotFoundError):
            npy_service.get_metadata(str(tmp_path / "nonexistent"))

    # -- list_volumes --

    def test_list_volumes(self):
        import npy_service
        self._create_test_volume(name="vol_a", shape=(3, 4, 5))
        self._create_test_volume(name="vol_b", shape=(6, 7, 8))

        volumes = npy_service.list_volumes()
        names = [v["name"] for v in volumes]
        assert "vol_a" in names
        assert "vol_b" in names

    def test_list_volumes_empty(self):
        import npy_service
        volumes = npy_service.list_volumes()
        assert volumes == []

    # -- find_for_sgy --

    def test_find_for_sgy_returns_path(self):
        import npy_service
        self._create_test_volume(name="myfile")
        result = npy_service.find_for_sgy("myfile.sgy")
        assert result is not None
        assert "myfile" in result

    def test_find_for_sgy_returns_none_for_missing(self):
        import npy_service
        assert npy_service.find_for_sgy("nonexistent.sgy") is None

    # -- missing volume raises FileNotFoundError --

    def test_read_inline_missing_volume_raises(self, tmp_path):
        import npy_service
        with pytest.raises(FileNotFoundError, match="NumPy 卷不存在"):
            npy_service.read_inline(str(tmp_path / "missing_vol"), il_index=0)


# ---------------------------------------------------------------------------
# zarr_service.py tests
# ---------------------------------------------------------------------------

class TestZarrService:
    """Tests for src/zarr_service.py using synthetic Zarr volumes."""

    @pytest.fixture(autouse=True)
    def _patch_paths(self, tmp_path, monkeypatch):
        """Redirect zarr_service paths to a temporary directory."""
        import zarr_service
        zarr_dir = tmp_path / "zarr"
        zarr_dir.mkdir()
        monkeypatch.setattr(zarr_service, "ZARR_DIR", zarr_dir)
        self.zarr_dir = zarr_dir

    def _create_test_zarr(self, name="test_vol.zarr", shape=(5, 8, 10)):
        """Helper: create a synthetic Zarr volume with dual storage."""
        import zarr
        import zarr.storage

        zarr_path = self.zarr_dir / name
        store = zarr.storage.LocalStore(str(zarr_path))
        root = zarr.open_group(store=store, mode="w")

        rng = np.random.default_rng(42)
        data = rng.standard_normal(shape).astype(np.float32)

        # amplitude: IL x XL x Samples
        amp = root.create_array(
            "amplitude",
            shape=shape,
            chunks=(1, shape[1], shape[2]),
            dtype="float32",
        )
        amp[:] = data

        # amplitude_xl: XL x IL x Samples (transposed view)
        amp_xl = root.create_array(
            "amplitude_xl",
            shape=(shape[1], shape[0], shape[2]),
            chunks=(1, shape[0], shape[2]),
            dtype="float32",
        )
        for i in range(shape[0]):
            amp_xl[:, i, :] = data[i]

        il_start, xl_start = 100, 200
        root.attrs["source_file"] = f"{name}.sgy"
        root.attrs["il_range"] = [il_start, il_start + shape[0] - 1]
        root.attrs["xl_range"] = [xl_start, xl_start + shape[1] - 1]
        root.attrs["ilines"] = list(range(il_start, il_start + shape[0]))
        root.attrs["xlines"] = list(range(xl_start, xl_start + shape[1]))
        root.attrs["samples"] = list(range(shape[2]))
        root.attrs["n_inlines"] = shape[0]
        root.attrs["n_crosslines"] = shape[1]
        root.attrs["n_samples"] = shape[2]
        root.attrs["dt_us"] = 4000

        return zarr_path, data

    # -- read_inline --

    def test_read_inline_shape(self):
        import zarr_service
        zarr_path, data = self._create_test_zarr(shape=(5, 8, 10))
        result = zarr_service.read_inline(str(zarr_path), il_index=0)
        assert result.shape == (8, 10)  # (nXL, nSamples)

    def test_read_inline_values(self):
        import zarr_service
        zarr_path, data = self._create_test_zarr(shape=(3, 4, 6))
        result = zarr_service.read_inline(str(zarr_path), il_index=2)
        np.testing.assert_array_equal(result, data[2])

    # -- read_crossline --

    def test_read_crossline_shape(self):
        import zarr_service
        zarr_path, data = self._create_test_zarr(shape=(5, 8, 10))
        result = zarr_service.read_crossline(str(zarr_path), xl_index=0)
        assert result.shape == (5, 10)  # (nIL, nSamples)

    def test_read_crossline_values(self):
        import zarr_service
        zarr_path, data = self._create_test_zarr(shape=(3, 4, 6))
        result = zarr_service.read_crossline(str(zarr_path), xl_index=2)
        expected = data[:, 2, :]
        np.testing.assert_array_equal(result, expected)

    # -- read_timeslice --

    def test_read_timeslice_shape(self):
        import zarr_service
        zarr_path, data = self._create_test_zarr(shape=(5, 8, 10))
        result = zarr_service.read_timeslice(str(zarr_path), sample_index=0)
        assert result.shape == (5, 8)  # (nIL, nXL)

    def test_read_timeslice_values(self):
        import zarr_service
        zarr_path, data = self._create_test_zarr(shape=(3, 4, 6))
        result = zarr_service.read_timeslice(str(zarr_path), sample_index=4)
        np.testing.assert_array_equal(result, data[:, :, 4])

    # -- get_zarr_metadata --

    def test_get_zarr_metadata_returns_expected_keys(self):
        import zarr_service
        zarr_path, _ = self._create_test_zarr()
        meta = zarr_service.get_zarr_metadata(str(zarr_path))
        assert "il_range" in meta
        assert "xl_range" in meta
        assert "n_inlines" in meta
        assert "n_crosslines" in meta
        assert "n_samples" in meta
        assert "dt_us" in meta

    def test_get_zarr_metadata_values(self):
        import zarr_service
        zarr_path, _ = self._create_test_zarr(shape=(5, 8, 10))
        meta = zarr_service.get_zarr_metadata(str(zarr_path))
        assert meta["n_inlines"] == 5
        assert meta["n_crosslines"] == 8
        assert meta["n_samples"] == 10
        assert meta["dt_us"] == 4000
        assert meta["il_range"] == [100, 104]
        assert meta["xl_range"] == [200, 207]

    # -- list_zarr_volumes --

    def test_list_zarr_volumes(self):
        import zarr_service
        self._create_test_zarr(name="vol_a.zarr", shape=(3, 4, 5))
        self._create_test_zarr(name="vol_b.zarr", shape=(6, 7, 8))

        volumes = zarr_service.list_zarr_volumes()
        names = [v["name"] for v in volumes]
        assert "vol_a.zarr" in names
        assert "vol_b.zarr" in names

    def test_list_zarr_volumes_empty(self):
        import zarr_service
        volumes = zarr_service.list_zarr_volumes()
        assert volumes == []

    # -- find_zarr_for_sgy --

    def test_find_zarr_for_sgy_returns_path(self):
        import zarr_service
        self._create_test_zarr(name="myfile.zarr")
        result = zarr_service.find_zarr_for_sgy("myfile.sgy")
        assert result is not None
        assert "myfile.zarr" in result

    def test_find_zarr_for_sgy_returns_none_for_missing(self):
        import zarr_service
        assert zarr_service.find_zarr_for_sgy("nonexistent.sgy") is None

    # -- out-of-bounds via zarr --

    def test_read_inline_out_of_bounds(self):
        import zarr_service
        zarr_path, _ = self._create_test_zarr(shape=(5, 8, 10))
        with pytest.raises(IndexError):
            zarr_service.read_inline(str(zarr_path), il_index=5)

    def test_read_crossline_out_of_bounds(self):
        import zarr_service
        zarr_path, _ = self._create_test_zarr(shape=(5, 8, 10))
        with pytest.raises(IndexError):
            zarr_service.read_crossline(str(zarr_path), xl_index=8)

    def test_read_timeslice_out_of_bounds(self):
        import zarr_service
        zarr_path, _ = self._create_test_zarr(shape=(5, 8, 10))
        with pytest.raises(IndexError):
            zarr_service.read_timeslice(str(zarr_path), sample_index=10)


# ---------------------------------------------------------------------------
# validation_service.py tests
# ---------------------------------------------------------------------------

class TestValidationService:
    """Tests for src/validation_service.py metric calculations."""

    def test_validate_segmentation_computes_expected_metrics(self):
        import validation_service

        result = validation_service.validate_segmentation(
            [[1, 1], [0, 0]],
            [[1, 0], [1, 0]],
            acceptance={"dice": 0.5, "recall": 0.6},
        )

        assert result["confusion"] == {
            "tp": 1,
            "fp": 1,
            "tn": 1,
            "fn": 1,
            "total": 4,
            "predicted_positive": 2,
            "ground_truth_positive": 2,
        }
        assert result["metrics"]["iou"] == pytest.approx(1 / 3)
        assert result["metrics"]["dice"] == pytest.approx(0.5)
        assert result["metrics"]["precision"] == pytest.approx(0.5)
        assert result["metrics"]["recall"] == pytest.approx(0.5)
        assert result["checks"] == {"dice": True, "recall": False}
        assert result["passed"] is False

    def test_validate_segmentation_rejects_shape_mismatch(self):
        import validation_service

        with pytest.raises(ValueError, match="same shape"):
            validation_service.validate_segmentation(
                [[1, 0], [0, 1]],
                [[1, 0, 1]],
            )

    def test_validate_segmentation_treats_empty_masks_as_perfect_match(self):
        import validation_service

        result = validation_service.validate_segmentation(
            [[0, 0]],
            [[0, 0]],
            acceptance={"iou": 1.0, "dice": 1.0},
        )
        assert result["metrics"]["iou"] == pytest.approx(1.0)
        assert result["metrics"]["dice"] == pytest.approx(1.0)
        assert result["passed"] is True


# ---------------------------------------------------------------------------
# sam_service.py tests
# ---------------------------------------------------------------------------

class TestSamService:
    """Focused tests for SAM prediction result edge cases."""

    def test_predict_mask_returns_empty_mask_when_model_returns_zero_masks(self, tmp_path, monkeypatch):
        import torch
        from PIL import Image
        import sam_service

        image_path = tmp_path / "slice.png"
        Image.new("RGB", (4, 3), color="white").save(image_path)

        class FakeMasks:
            data = torch.empty((0, 3, 4), dtype=torch.float32)

        class FakeResult:
            masks = FakeMasks()
            boxes = None

        class FakeModel:
            def predict(self, **kwargs):
                return [FakeResult()]

        monkeypatch.setattr(sam_service, "_model", FakeModel())
        monkeypatch.setattr(
            sam_service,
            "_embeddings",
            {"emb": {"path": str(image_path), "size": (4, 3)}},
        )

        result = sam_service.predict_mask("emb", [[1, 1]], [1])

        assert result["mask_shape"] == [3, 4]
        assert result["scores"] == [0.0]
        assert result["mask"] == [[0.0, 0.0, 0.0, 0.0]] * 3
