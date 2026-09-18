import sys
import os
import time
import rasterio
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ml.features_af import extract_af_features
from ml.features_bs import extract_bs_features

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
train_dir = os.environ.get("TRAIN_DIR", os.path.join(PROJECT_ROOT, "data", "train"))


def test_af():
    af_dir = os.path.join(train_dir, "af")
    chip_id = "AF_tr_000001"
    viirs_p = os.path.join(af_dir, "viirs", f"{chip_id}_VIIRS_I1-I5.tif")
    aux_p = os.path.join(af_dir, "aux", f"{chip_id}_AUX.tif")
    
    if os.path.exists(viirs_p) and os.path.exists(aux_p):
        with rasterio.open(viirs_p) as src:
            viirs = src.read()
        with rasterio.open(aux_p) as src:
            aux = src.read()
    else:
        # Автономный синтетический чип AF (8 каналов VIIRS, 5 каналов AUX)
        np.random.seed(42)
        viirs = np.ones((8, 256, 256), dtype=np.float32)
        viirs[3] = 310.0  # I4
        viirs[4] = 295.0  # I5
        viirs[5] = 45.0   # solar_zenith
        viirs[6] = 10.0   # sensor_zenith
        viirs[7] = 1.0    # valid
        aux = np.ones((5, 256, 256), dtype=np.float32)
        aux[0] = 30.0     # grass
        aux[1] = 120.0    # dem
        aux[2] = 298.0    # t2m
        aux[3] = 40.0     # rh
        aux[4] = 3.5      # wind
        
    t0 = time.perf_counter()
    X = extract_af_features(viirs, aux)
    t_feat = (time.perf_counter() - t0) * 1000
    
    print(f"AF Feature extraction: shape={X.shape}, time={t_feat:.2f} ms, nan_count={np.isnan(X).sum()}")
    assert not np.isnan(X).any(), "AF features contain NaN!"
    assert X.shape == (256 * 256, 22), f"Unexpected AF shape: {X.shape}"


def test_bs():
    bs_dir = os.path.join(train_dir, "bs")
    chip_id = "BS_tr_000001"
    s2_pre_p = os.path.join(bs_dir, "sentinel2_pre", f"{chip_id}_Sentinel-2_pre.tif")
    s2_post_p = os.path.join(bs_dir, "sentinel2_post", f"{chip_id}_Sentinel-2_post.tif")
    s1_pre_p = os.path.join(bs_dir, "sentinel1_pre", f"{chip_id}_Sentinel-1_pre.tif")
    s1_post_p = os.path.join(bs_dir, "sentinel1_post", f"{chip_id}_Sentinel-1_post.tif")
    aux_p = os.path.join(bs_dir, "aux", f"{chip_id}_AUX.tif")
    
    if all(os.path.exists(p) for p in [s2_pre_p, s2_post_p, s1_pre_p, s1_post_p, aux_p]):
        with rasterio.open(s2_pre_p) as s: s2_pre = s.read()
        with rasterio.open(s2_post_p) as s: s2_post = s.read()
        with rasterio.open(s1_pre_p) as s: s1_pre = s.read()
        with rasterio.open(s1_post_p) as s: s1_post = s.read()
        with rasterio.open(aux_p) as s: aux = s.read()
    else:
        # Автономный синтетический чип BS
        np.random.seed(42)
        s2_pre = (np.random.rand(10, 512, 512) * 5000).astype(np.uint16)
        s2_post = (np.random.rand(10, 512, 512) * 5000).astype(np.uint16)
        s1_pre = (np.random.randn(2, 512, 512) * 500).astype(np.int16)
        s1_post = (np.random.randn(2, 512, 512) * 500).astype(np.int16)
        aux = np.ones((3, 512, 512), dtype=np.int16)
        aux[2] = 30  # grass
        
    t0 = time.perf_counter()
    X, cloud_mask = extract_bs_features(s2_pre, s2_post, s1_pre, s1_post, aux)
    t_feat = (time.perf_counter() - t0) * 1000
    
    print(f"BS Feature extraction: shape={X.shape}, time={t_feat:.2f} ms, nan_count={np.isnan(X).sum()}, cloud_mask_shape={cloud_mask.shape}")
    assert not np.isnan(X).any(), "BS features contain NaN!"
    assert X.shape == (512 * 512, 22), f"Unexpected BS shape: {X.shape}"
    assert cloud_mask.shape == (512, 512), f"Unexpected cloud_mask shape: {cloud_mask.shape}"


if __name__ == "__main__":
    test_af()
    test_bs()
    print("ALL FEATURE EXTRACTION TESTS PASSED!")
