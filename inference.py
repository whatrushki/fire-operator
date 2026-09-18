"""
Официальный скрипт инференса соревнований «КосмоХакатон 2026: Мониторинг природных пожаров».
Соответствует регламенту:
- CLI вызов: python inference.py --data-dir <path_to_test> --output <path_to_submission.csv>
- Полная обработка AF и BS чипов
- Формирование валидного submission.csv (447 строк, RLE с кавычками, взаимное исключение классов)
- Высокая скорость работы (< 30 секунд на полный тестовый набор)
"""
import os
import sys
import argparse
import time
import joblib
import rasterio
import numpy as np
import pandas as pd

# Добавляем корень проекта в путь поиска модулей
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from ml.features_af import extract_af_features
from ml.features_bs import extract_bs_features
from ml.utils.rle import rle_encode

WEIGHTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "weights"))


def parse_args():
    parser = argparse.ArgumentParser(description="Инференс моделей мониторинга природных пожаров")
    parser.add_argument("--data-dir", type=str, required=True, help="Путь к каталогу с тестовыми данными")
    parser.add_argument("--output", type=str, required=True, help="Путь к результирующему submission.csv")
    return parser.parse_args()


def load_models():
    """Загрузка обученных моделей из директории weights/."""
    af_path = os.path.join(WEIGHTS_DIR, "af_model.joblib")
    bs_path = os.path.join(WEIGHTS_DIR, "bs_model.joblib")
    
    if not os.path.exists(af_path) or not os.path.exists(bs_path):
        raise FileNotFoundError(f"Файлы весов не найдены в {WEIGHTS_DIR}. Запустите сначала обучение: python ml/train.py")
        
    af_model = joblib.load(af_path)
    bs_model = joblib.load(bs_path)
    return af_model, bs_model


def find_chip_files(data_dir: str):
    """
    Поиск входных файлов чипов в каталоге данных (поддерживает как плоскую, так и иерархическую структуру).
    """
    af_chips = {}
    bs_chips = {}

    # Поиск по всему поддереву
    for root, dirs, files in os.walk(data_dir):
        for f in files:
            if not f.endswith(".tif"):
                continue
            fpath = os.path.join(root, f)
            
            # AF чипы
            if f.startswith("AF_") and "VIIRS" in f:
                chip_id = f.split("_VIIRS")[0]
                af_chips.setdefault(chip_id, {})["viirs"] = fpath
            elif f.startswith("AF_") and "AUX" in f:
                chip_id = f.split("_AUX")[0]
                af_chips.setdefault(chip_id, {})["aux"] = fpath
                
            # BS чипы
            elif f.startswith("BS_") and "Sentinel-2_pre" in f:
                chip_id = f.split("_Sentinel-2_pre")[0]
                bs_chips.setdefault(chip_id, {})["s2_pre"] = fpath
            elif f.startswith("BS_") and "Sentinel-2_post" in f:
                chip_id = f.split("_Sentinel-2_post")[0]
                bs_chips.setdefault(chip_id, {})["s2_post"] = fpath
            elif f.startswith("BS_") and "Sentinel-1_pre" in f:
                chip_id = f.split("_Sentinel-1_pre")[0]
                bs_chips.setdefault(chip_id, {})["s1_pre"] = fpath
            elif f.startswith("BS_") and "Sentinel-1_post" in f:
                chip_id = f.split("_Sentinel-1_post")[0]
                bs_chips.setdefault(chip_id, {})["s1_post"] = fpath
            elif f.startswith("BS_") and "AUX" in f:
                chip_id = f.split("_AUX")[0]
                bs_chips.setdefault(chip_id, {})["aux"] = fpath

    return af_chips, bs_chips


def main():
    t_start = time.perf_counter()
    args = parse_args()
    
    print("=" * 60)
    print(f"Запуск инференса Fire-Operator")
    print(f"Входной каталог: {args.data_dir}")
    print(f"Выходной файл:   {args.output}")
    print("=" * 60)
    
    # 1. Загрузка весов
    t_load = time.perf_counter()
    af_model, bs_model = load_models()
    print(f"Модели загружены за {(time.perf_counter() - t_load)*1000:.1f} мс")

    # 2. Поиск чипов
    af_chips, bs_chips = find_chip_files(args.data_dir)
    print(f"Обнаружено чипов: AF={len(af_chips)}, BS={len(bs_chips)}")

    # Проверка наличия sample_submission.csv для строгого порядка
    sample_sub_path = os.path.join(args.data_dir, "sample_submission.csv")
    order_dict = {}
    if os.path.exists(sample_sub_path):
        sample_df = pd.read_csv(sample_sub_path)
        for idx, row in sample_df.iterrows():
            order_dict[(row["chip_id"], int(row["class_id"]))] = idx

    results = []

    # 3. Инференс AF чипов
    t_af_start = time.perf_counter()
    for chip_id, files in af_chips.items():
        if "viirs" not in files or "aux" not in files:
            continue
            
        with rasterio.open(files["viirs"]) as s: viirs = s.read()
        with rasterio.open(files["aux"]) as s: aux = s.read()
        
        X = extract_af_features(viirs, aux)
        probs = af_model.predict_proba(X)[:, 1]
        
        # Физическая фильтрация: очаг должен быть теплее фона и выше абсолютного порога
        i4 = X[:, 0]
        dt = X[:, 2]
        pred_bin = (probs > 0.65) & (i4 > 305.0) & (dt > 4.0)
        mask = pred_bin.astype(np.uint8).reshape((256, 256))
        
        rle = rle_encode(mask)
        results.append({
            "chip_id": chip_id,
            "class_id": 1,
            "rle": rle
        })
    print(f"Инференс AF ({len(af_chips)} чипов) завершен за {time.perf_counter() - t_af_start:.2f} с")

    # 4. Инференс BS чипов
    t_bs_start = time.perf_counter()
    for chip_id, files in bs_chips.items():
        req_keys = ["s2_pre", "s2_post", "s1_pre", "s1_post", "aux"]
        if not all(k in files for k in req_keys):
            continue
            
        with rasterio.open(files["s2_pre"]) as s: s2_pre = s.read()
        with rasterio.open(files["s2_post"]) as s: s2_post = s.read()
        with rasterio.open(files["s1_pre"]) as s: s1_pre = s.read()
        with rasterio.open(files["s1_post"]) as s: s1_post = s.read()
        with rasterio.open(files["aux"]) as s: aux = s.read()
        
        X, cloud_mask = extract_bs_features(s2_pre, s2_post, s1_pre, s1_post, aux)
        preds = bs_model.predict(X)
        pred_mask = preds.reshape((512, 512)).astype(np.uint8)
        pred_mask[~cloud_mask] = 0  # очистка от облаков
        
        # Кодируем 3 класса строго без пересечений
        for cls_id in (1, 2, 3):
            cls_mask = (pred_mask == cls_id).astype(np.uint8)
            rle = rle_encode(cls_mask)
            results.append({
                "chip_id": chip_id,
                "class_id": cls_id,
                "rle": rle
            })
    print(f"Инференс BS ({len(bs_chips)} чипов) завершен за {time.perf_counter() - t_bs_start:.2f} с")

    # 5. Сортировка и сохранение в submission.csv
    out_df = pd.DataFrame(results)
    if order_dict:
        out_df["sort_key"] = out_df.apply(lambda r: order_dict.get((r["chip_id"], r["class_id"]), 999999), axis=1)
        out_df = out_df.sort_values("sort_key").drop(columns=["sort_key"])
        
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    
    # Запись строго в формате: chip_id,class_id,rle (значения rle уже в кавычках)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write("chip_id,class_id,rle\n")
        for _, row in out_df.iterrows():
            f.write(f"{row['chip_id']},{row['class_id']},{row['rle']}\n")
            
    total_sec = time.perf_counter() - t_start
    print(f"\n[УСПЕХ] Файл submission.csv успешно сформирован: {args.output}")
    print(f"Всего строк: {len(out_df)}")
    print(f"ИТОГОВОЕ ВРЕМЯ ИНФЕРЕНСА: {total_sec:.2f} секунд (норматив 8 баллов: < 30 секунд)")
    sys.exit(0)


if __name__ == "__main__":
    main()
