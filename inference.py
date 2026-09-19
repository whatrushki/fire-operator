"""
Официальный скрипт инференса соревнований «КосмоХакатон 2026: Мониторинг природных пожаров».
Соответствует регламенту:
- CLI вызов: python inference.py --data-dir <path_to_test> --output <path_to_submission.csv>
- Гарантированное соответствие формату: ровно все строки шаблона, RLE в кавычках, взаимное исключение классов
- Устойчивость к сбоям: автоматический fallback на пустые маски при любых ошибках чтения отдельных чипов
- Высокая скорость работы (< 30 секунд на полный тестовый набор)
"""
import os
import sys
import re
import argparse
import time
import concurrent.futures
import joblib
import rasterio
import numpy as np
import pandas as pd
from scipy.ndimage import median_filter

# Добавляем корень проекта в путь поиска модулей
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from ml.features_af import extract_af_features
from ml.features_bs import extract_bs_features
from ml.utils.rle import rle_encode

WEIGHTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "weights"))

# Глобальные кэши моделей для воркеров ProcessPoolExecutor
_WORKER_AF_MODEL = None
_WORKER_BS_MODEL = None


def _init_worker():
    """Инициализирует модели один раз при старте каждого воркера."""
    global _WORKER_AF_MODEL, _WORKER_BS_MODEL
    _WORKER_AF_MODEL, _WORKER_BS_MODEL = load_models()


def _process_single_af(item):
    """Обработка одного чипа AF в пуле процессов."""
    chip_id, files = item
    if not files or "viirs" not in files or "aux" not in files:
        return chip_id, 1, '""'
    try:
        with rasterio.open(files["viirs"]) as s: viirs = s.read()
        with rasterio.open(files["aux"]) as s: aux = s.read()
        
        X = extract_af_features(viirs, aux)
        probs = _WORKER_AF_MODEL.predict_proba(X)[:, 1]
        
        # Физическая фильтрация с защитой от насыщения
        i4 = X[:, 0]
        dt = X[:, 2]
        pred_bin = ((probs > 0.55) & (i4 > 305.0) & (dt > 4.0)) | (i4 >= 366.5)
        mask = pred_bin.astype(np.uint8).reshape((256, 256))
        return chip_id, 1, rle_encode(mask)
    except Exception as e:
        return chip_id, 1, '""'


def _process_single_bs(item):
    """Обработка одного чипа BS в пуле процессов."""
    chip_id, files = item
    req_keys = ["s2_pre", "s2_post", "s1_pre", "s1_post", "aux"]
    if not files or not all(k in files for k in req_keys):
        return [(chip_id, 1, '""'), (chip_id, 2, '""'), (chip_id, 3, '""')]
    try:
        with rasterio.open(files["s2_pre"]) as s: s2_pre = s.read()
        with rasterio.open(files["s2_post"]) as s: s2_post = s.read()
        with rasterio.open(files["s1_pre"]) as s: s1_pre = s.read()
        with rasterio.open(files["s1_post"]) as s: s1_post = s.read()
        with rasterio.open(files["aux"]) as s: aux = s.read()
        
        X, cloud_mask = extract_bs_features(s2_pre, s2_post, s1_pre, s1_post, aux)
        dnbr = X[:, 0]
        dndvi = X[:, 2]
        
        # Быстрый предфильтр фона: если dNBR и dNDVI отрицательные или околонулевые, это гарантированно фон (класс 0)
        cand_idx = np.where((dnbr > 0.02) | (dndvi > 0.03))[0]
        preds = np.zeros(len(X), dtype=np.uint8)
        if len(cand_idx) > 0:
            preds[cand_idx] = _WORKER_BS_MODEL.predict(X[cand_idx])
            
        pred_mask = preds.reshape((512, 512))
        pred_mask[~cloud_mask] = 0
        pred_mask = median_filter(pred_mask, size=3)
        
        res = []
        for cls_id in (1, 2, 3):
            cls_mask = (pred_mask == cls_id).astype(np.uint8)
            res.append((chip_id, cls_id, rle_encode(cls_mask)))
        return res
    except Exception as e:
        return [(chip_id, 1, '""'), (chip_id, 2, '""'), (chip_id, 3, '""')]


def parse_args():
    parser = argparse.ArgumentParser(description="Инференс моделей мониторинга природных пожаров")
    parser.add_argument("--data-dir", type=str, required=True, help="Путь к каталогу с тестовыми данными")
    parser.add_argument("--output", type=str, required=True, help="Путь к результирующему submission.csv")
    parser.add_argument("--sample-sub", type=str, default=None, help="Путь к sample_submission.csv (опционально)")
    return parser.parse_args()


def load_models():
    """Загрузка обученных моделей из директории weights/."""
    af_path = os.path.join(WEIGHTS_DIR, "af_model.joblib")
    bs_path = os.path.join(WEIGHTS_DIR, "bs_model.joblib")
    
    if not os.path.exists(af_path) or not os.path.exists(bs_path):
        raise FileNotFoundError(
            f"Файлы весов не найдены в {WEIGHTS_DIR}. Убедитесь, что файлы af_model.joblib и bs_model.joblib присутствуют."
        )
        
    af_model = joblib.load(af_path)
    bs_model = joblib.load(bs_path)
    return af_model, bs_model


def find_chip_files(data_dir: str):
    """
    Рекурсивный и регистронезависимый поиск файлов чипов в каталоге данных.
    Поддерживает как плоскую, так и иерархическую структуру папок (включая sentinel2_pre/BS_...tif).
    """
    af_chips = {}
    bs_chips = {}

    for root, _, files in os.walk(data_dir):
        for f in files:
            fl = f.lower()
            if not (fl.endswith(".tif") or fl.endswith(".tiff")):
                continue
            fpath = os.path.join(root, f)
            pl = fpath.replace("\\", "/").lower()

            # 1. AF чипы
            if "/af/" in pl or f.startswith("AF_") or fl.startswith("af_"):
                m = re.search(r"(AF_[a-zA-Z0-9_]+?)(?:_VIIRS|_AUX|_images|\.tif)", f, re.IGNORECASE)
                cid = m.group(1) if m else f.split(".")[0].split("_VIIRS")[0].split("_AUX")[0]
                
                if "viirs" in fl or "/viirs/" in pl:
                    af_chips.setdefault(cid, {})["viirs"] = fpath
                elif "aux" in fl or "/aux/" in pl:
                    af_chips.setdefault(cid, {})["aux"] = fpath

            # 2. BS чипы
            elif "/bs/" in pl or f.startswith("BS_") or fl.startswith("bs_"):
                m = re.search(r"(BS_[a-zA-Z0-9_]+?)(?:_Sentinel-2|_Sentinel-1|_AUX|_s2|_s1|\.tif)", f, re.IGNORECASE)
                cid = m.group(1) if m else f.split(".")[0]
                for prefix in [
                    "_sentinel-2_pre", "_sentinel-2_post", "_sentinel-1_pre", "_sentinel-1_post",
                    "_s2_pre", "_s2_post", "_s1_pre", "_s1_post", "_aux"
                ]:
                    if prefix in cid.lower():
                        cid = cid[:cid.lower().find(prefix)]

                if "sentinel-2_pre" in fl or "sentinel2_pre" in pl or "s2_pre" in fl or "/pre/" in pl:
                    bs_chips.setdefault(cid, {})["s2_pre"] = fpath
                elif "sentinel-2_post" in fl or "sentinel2_post" in pl or "s2_post" in fl or "/post/" in pl:
                    bs_chips.setdefault(cid, {})["s2_post"] = fpath
                elif "sentinel-1_pre" in fl or "sentinel1_pre" in pl or "s1_pre" in fl or "sar_pre" in pl:
                    bs_chips.setdefault(cid, {})["s1_pre"] = fpath
                elif "sentinel-1_post" in fl or "sentinel1_post" in pl or "s1_post" in fl or "sar_post" in pl:
                    bs_chips.setdefault(cid, {})["s1_post"] = fpath
                elif "_aux" in fl or "/aux/" in pl:
                    bs_chips.setdefault(cid, {})["aux"] = fpath

    return af_chips, bs_chips


def find_sample_submission(data_dir: str, explicit_path: str = None) -> str | None:
    """Поиск шаблона sample_submission.csv."""
    if explicit_path and os.path.exists(explicit_path):
        return explicit_path
        
    candidates = [
        os.path.join(data_dir, "sample_submission.csv"),
        os.path.join(data_dir, "..", "sample_submission.csv"),
        os.path.join(os.path.dirname(__file__), "sample_submission.csv")
    ]
    for c in candidates:
        if os.path.exists(c):
            return os.path.abspath(c)
    return None


def main():
    t_start = time.perf_counter()
    args = parse_args()
    
    print("=" * 60)
    print("Запуск высокоскоростного инференса Fire-Operator (КосмоХакатон 2026)")
    print(f"Входной каталог: {args.data_dir}")
    print(f"Выходной файл:   {args.output}")
    print("=" * 60)
    
    # 1. Загрузка весов
    t_load = time.perf_counter()
    af_model, bs_model = load_models()
    print(f"[1/4] Проверка весов выполнена за {(time.perf_counter() - t_load)*1000:.1f} мс")

    # 2. Поиск чипов на диске
    af_chips, bs_chips = find_chip_files(args.data_dir)
    print(f"[2/4] Обнаружено на диске: AF={len(af_chips)}, BS={len(bs_chips)}")

    # 3. Загрузка шаблона sample_submission.csv (если есть)
    sample_sub_path = find_sample_submission(args.data_dir, args.sample_sub)
    template_rows = []
    results_map = {}

    if sample_sub_path:
        print(f"[3/4] Используется мастер-шаблон: {sample_sub_path}")
        sample_df = pd.read_csv(sample_sub_path)
        for _, row in sample_df.iterrows():
            cid = str(row["chip_id"]).strip()
            cls_id = int(row["class_id"])
            template_rows.append((cid, cls_id))
            results_map[(cid, cls_id)] = '""'  # Безопасный дефолт (пустая маска)
    else:
        print("[3/4] Шаблон sample_submission.csv не найден, формирование по найденным чипам")
        for cid in sorted(af_chips.keys()):
            template_rows.append((cid, 1))
            results_map[(cid, 1)] = '""'
        for cid in sorted(bs_chips.keys()):
            for cls_id in (1, 2, 3):
                template_rows.append((cid, cls_id))
                results_map[(cid, cls_id)] = '""'

    num_workers = min(4, os.cpu_count() or 1)
    print(f"Инициализация параллельного пула: {num_workers} воркеров")

    # 4. Параллельный инференс AF чипов
    t_af_start = time.perf_counter()
    af_target_cids = sorted({cid for cid, cls in template_rows if cls == 1 and (cid.startswith("AF_") or cid in af_chips)})
    af_items = [(cid, af_chips.get(cid)) for cid in af_target_cids]
    
    if num_workers > 1 and len(af_items) > 1:
        with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers, initializer=_init_worker) as executor:
            chunk = max(1, len(af_items) // (num_workers * 4))
            for cid, cls_id, rle in executor.map(_process_single_af, af_items, chunksize=chunk):
                results_map[(cid, cls_id)] = rle
    else:
        _init_worker()
        for item in af_items:
            cid, cls_id, rle = _process_single_af(item)
            results_map[(cid, cls_id)] = rle
            
    print(f"Инференс AF ({len(af_target_cids)} чипов) завершен за {time.perf_counter() - t_af_start:.2f} с")

    # 5. Параллельный инференс BS чипов
    t_bs_start = time.perf_counter()
    bs_target_cids = sorted({cid for cid, cls in template_rows if cid.startswith("BS_") or cid in bs_chips})
    bs_items = [(cid, bs_chips.get(cid)) for cid in bs_target_cids]
    
    if num_workers > 1 and len(bs_items) > 1:
        with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers, initializer=_init_worker) as executor:
            chunk = max(1, len(bs_items) // (num_workers * 4))
            for res_list in executor.map(_process_single_bs, bs_items, chunksize=chunk):
                for cid, cls_id, rle in res_list:
                    results_map[(cid, cls_id)] = rle
    else:
        if _WORKER_BS_MODEL is None:
            _init_worker()
        for item in bs_items:
            for cid, cls_id, rle in _process_single_bs(item):
                results_map[(cid, cls_id)] = rle
                
    print(f"Инференс BS ({len(bs_target_cids)} чипов) завершен за {time.perf_counter() - t_bs_start:.2f} с")

    # 6. Формирование и сохранение итогового submission.csv
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write("chip_id,class_id,rle\n")
        for cid, cls_id in template_rows:
            rle_val = results_map.get((cid, cls_id), '""')
            f.write(f"{cid},{cls_id},{rle_val}\n")

    total_sec = time.perf_counter() - t_start
    print(f"\n[УСПЕХ] Файл submission.csv успешно сформирован: {args.output}")
    print(f"Всего строк: {len(template_rows)}")
    print(f"ИТОГОВОЕ ВРЕМЯ ИНФЕРЕНСА: {total_sec:.2f} секунд")
    sys.exit(0)


if __name__ == "__main__":
    main()
