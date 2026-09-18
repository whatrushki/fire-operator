import os
import sys
import shutil
import tempfile
import time
import subprocess
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from ml.utils.rle import rle_decode

train_dir = r"C:\Users\vladg\Desktop\Кейс\fire-train-renamed\train"

def test_inference_pipeline():
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_data_dir = os.path.join(tmp_dir, "test_chips")
        os.makedirs(test_data_dir, exist_ok=True)
        
        # Копируем 2 AF чипа
        af_train = os.path.join(train_dir, "af")
        for chip in ["AF_tr_000001", "AF_tr_000004"]:
            shutil.copy(os.path.join(af_train, "viirs", f"{chip}_VIIRS_I1-I5.tif"), os.path.join(test_data_dir, f"{chip}_VIIRS_I1-I5.tif"))
            shutil.copy(os.path.join(af_train, "aux", f"{chip}_AUX.tif"), os.path.join(test_data_dir, f"{chip}_AUX.tif"))

        # Копируем 2 BS чипа
        bs_train = os.path.join(train_dir, "bs")
        for chip in ["BS_tr_000001", "BS_tr_000002"]:
            shutil.copy(os.path.join(bs_train, "sentinel2_pre", f"{chip}_Sentinel-2_pre.tif"), os.path.join(test_data_dir, f"{chip}_Sentinel-2_pre.tif"))
            shutil.copy(os.path.join(bs_train, "sentinel2_post", f"{chip}_Sentinel-2_post.tif"), os.path.join(test_data_dir, f"{chip}_Sentinel-2_post.tif"))
            shutil.copy(os.path.join(bs_train, "sentinel1_pre", f"{chip}_Sentinel-1_pre.tif"), os.path.join(test_data_dir, f"{chip}_Sentinel-1_pre.tif"))
            shutil.copy(os.path.join(bs_train, "sentinel1_post", f"{chip}_Sentinel-1_post.tif"), os.path.join(test_data_dir, f"{chip}_Sentinel-1_post.tif"))
            shutil.copy(os.path.join(bs_train, "aux", f"{chip}_AUX.tif"), os.path.join(test_data_dir, f"{chip}_AUX.tif"))

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

        # Проверка структуры файла (keep_default_na=False, чтобы пустая строка "" не превращалась в NaN)
        df = pd.read_csv(out_csv, keep_default_na=False)
        print("Submission DataFrame shape:", df.shape)
        assert list(df.columns) == ["chip_id", "class_id", "rle"], f"Invalid columns: {df.columns}"

        # 2 AF чипа (по 1 строке) + 2 BS чипа (по 3 строки) = 8 строк
        assert len(df) == 8, f"Expected 8 rows, got {len(df)}"

        # Проверка отсутствия пустых ячеек (все должны быть строками)
        assert all(isinstance(x, str) for x in df["rle"]), "rle values must all be strings!"

        # Проверка декодирования RLE
        for _, row in df.iterrows():
            cid = row["chip_id"]
            cls = int(row["class_id"])
            rle_str = str(row["rle"])
            shape = (256, 256) if cid.startswith("AF_") else (512, 512)
            mask = rle_decode(rle_str, shape)
            assert mask.shape == shape, f"Invalid mask shape for {cid}"

        print(f"TEST INFERENCE PASSED! Total execution time: {t_total:.2f} s")

if __name__ == "__main__":
    test_inference_pipeline()
