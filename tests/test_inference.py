import os
import sys
import shutil
import tempfile
import time
import subprocess
import pandas as pd
import numpy as np
import rasterio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from ml.utils.rle import rle_decode

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
train_dir = os.environ.get("TRAIN_DIR", os.path.join(PROJECT_ROOT, "data", "train"))


def create_dummy_raster(path: str, count: int, height: int, width: int, dtype: str, value_range: tuple):
    profile = {
        "driver": "GTiff",
        "count": count,
        "height": height,
        "width": width,
        "dtype": dtype
    }
    with rasterio.open(path, "w", **profile) as dst:
        for i in range(1, count + 1):
            if dtype == "float32":
                arr = np.random.uniform(value_range[0], value_range[1], (height, width)).astype(np.float32)
            elif dtype == "uint16":
                arr = np.random.randint(value_range[0], value_range[1], (height, width), dtype=np.uint16)
            else:
                arr = np.random.randint(value_range[0], value_range[1], (height, width), dtype=np.int16)
            dst.write(arr, i)


def test_inference_pipeline():
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_data_dir = os.path.join(tmp_dir, "test_chips")
        os.makedirs(test_data_dir, exist_ok=True)
        
        af_train = os.path.join(train_dir, "af")
        bs_train = os.path.join(train_dir, "bs")
        
        has_real_data = os.path.exists(af_train) and os.path.exists(bs_train)
        
        if has_real_data:
            # Копируем 2 AF чипа
            for chip in ["AF_tr_000001", "AF_tr_000004"]:
                v_src = os.path.join(af_train, "viirs", f"{chip}_VIIRS_I1-I5.tif")
                a_src = os.path.join(af_train, "aux", f"{chip}_AUX.tif")
                if os.path.exists(v_src) and os.path.exists(a_src):
                    shutil.copy(v_src, os.path.join(test_data_dir, f"{chip}_VIIRS_I1-I5.tif"))
                    shutil.copy(a_src, os.path.join(test_data_dir, f"{chip}_AUX.tif"))

            # Копируем 2 BS чипа
            for chip in ["BS_tr_000001", "BS_tr_000002"]:
                for key, sub in [("Sentinel-2_pre", "sentinel2_pre"), ("Sentinel-2_post", "sentinel2_post"),
                                 ("Sentinel-1_pre", "sentinel1_pre"), ("Sentinel-1_post", "sentinel1_post"),
                                 ("AUX", "aux")]:
                    p_src = os.path.join(bs_train, sub, f"{chip}_{key}.tif")
                    if os.path.exists(p_src):
                        shutil.copy(p_src, os.path.join(test_data_dir, f"{chip}_{key}.tif"))
        else:
            # Создаем валидные синтетические GeoTIFF чипы для автономного теста
            np.random.seed(42)
            # AF_te_000001
            create_dummy_raster(os.path.join(test_data_dir, "AF_te_000001_VIIRS.tif"), 8, 256, 256, "float32", (250.0, 340.0))
            create_dummy_raster(os.path.join(test_data_dir, "AF_te_000001_AUX.tif"), 5, 256, 256, "float32", (0.0, 100.0))
            
            # BS_te_000001
            create_dummy_raster(os.path.join(test_data_dir, "BS_te_000001_Sentinel-2_pre.tif"), 10, 512, 512, "uint16", (100, 4000))
            create_dummy_raster(os.path.join(test_data_dir, "BS_te_000001_Sentinel-2_post.tif"), 10, 512, 512, "uint16", (100, 4000))
            create_dummy_raster(os.path.join(test_data_dir, "BS_te_000001_Sentinel-1_pre.tif"), 2, 512, 512, "int16", (-2000, 0))
            create_dummy_raster(os.path.join(test_data_dir, "BS_te_000001_Sentinel-1_post.tif"), 2, 512, 512, "int16", (-2000, 0))
            create_dummy_raster(os.path.join(test_data_dir, "BS_te_000001_AUX.tif"), 3, 512, 512, "int16", (0, 50))

        out_csv = os.path.join(tmp_dir, "submission.csv")
        inference_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "inference.py"))

        cmd = [sys.executable, inference_script, "--data-dir", test_data_dir, "--output", out_csv]
        t0 = time.perf_counter()
        res = subprocess.run(cmd, capture_output=True, text=True)
        t_total = time.perf_counter() - t0

        print(res.stdout)
        if res.stderr:
            print("STDERR:", res.stderr)

        assert res.returncode == 0, f"Inference failed with code {res.returncode}"
        assert os.path.exists(out_csv), "submission.csv was not created!"

        df = pd.read_csv(out_csv, keep_default_na=False)
        print("Submission DataFrame shape:", df.shape)
        assert list(df.columns) == ["chip_id", "class_id", "rle"], f"Invalid columns: {df.columns}"

        # Проверка отсутствия пустых ячеек (все должны быть строками)
        assert all(isinstance(x, str) for x in df["rle"]), "rle values must all be strings!"

        # Проверка декодирования RLE
        for _, row in df.iterrows():
            cid = str(row["chip_id"])
            rle_str = str(row["rle"])
            shape = (256, 256) if cid.startswith("AF_") else (512, 512)
            mask = rle_decode(rle_str, shape)
            assert mask.shape == shape, f"Invalid mask shape for {cid}"

        print(f"TEST INFERENCE PASSED! Total execution time: {t_total:.2f} s")


if __name__ == "__main__":
    test_inference_pipeline()
