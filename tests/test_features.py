import sys
import os
import time
import rasterio
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ml.features_af import extract_af_features
from ml.features_bs import extract_bs_features

train_dir = r"C:\Users\vladg\Desktop\Кейс\fire-train-renamed\train"

def test_af():
    af_dir = os.path.join(train_dir, "af")
    chip_id = "AF_tr_000001"
    viirs_p = os.path.join(af_dir, "viirs", f"{chip_id}_VIIRS_I1-I5.tif")
    aux_p = os.path.join(af_dir, "aux", f"{chip_id}_AUX.tif")
    
    with rasterio.open(viirs_p) as src:
        viirs = src.read()
    with rasterio.open(aux_p) as src:
        aux = src.read()
        
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
    
    with rasterio.open(s2_pre_p) as s:
        s2_pre = s.read()
    with rasterio.open(s2_post_p) as s:
        s2_post = s.read()
    with rasterio.open(s1_pre_p) as s:
        s1_pre = s.read()
    with rasterio.open(s1_post_p) as s:
        s1_post = s.read()
    with rasterio.open(aux_p) as s:
        aux = s.read()
        
    t0 = time.perf_counter()
    X, cloud_mask = extract_bs_features(s2_pre, s2_post, s1_pre, s1_post, aux)
    t_feat = (time.perf_counter() - t0) * 1000
    
    print(f"BS Feature extraction: shape={X.shape}, time={t_feat:.2f} ms, nan_count={np.isnan(X).sum()}, cloud_mask_shape={cloud_mask.shape}")
    assert not np.isnan(X).any(), "BS features contain NaN!"
    assert X.shape == (512 * 512, 16), f"Unexpected BS shape: {X.shape}"

if __name__ == "__main__":
    test_af()
    test_bs()
    print("ALL FEATURE EXTRACTION TESTS PASSED!")
