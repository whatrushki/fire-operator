"""
Скрипт обучения и строгой валидации моделей Fire-Operator на полном реальном датасете.
Использует градиентный бустинг LightGBM:
- AF: Бинарная классификация с физической фильтрацией и майнингом сложных негативов (блики, нагретая почва);
- BS: Многоклассовая классификация (степени 0, 1, 2, 3) со сбалансированным весом классов и текстурными признаками;
- Строгая валидация на отложенных чипах без пространственных утечек (Group-Split по fire_event_id);
- Сохранение весов в weights/af_model.joblib и weights/bs_model.joblib.
"""
import os
import sys
import time
import argparse
import joblib
import rasterio
import numpy as np
import pandas as pd
from scipy.ndimage import median_filter
from lightgbm import LGBMClassifier

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ml.features_af import extract_af_features
from ml.features_bs import extract_bs_features
from ml.utils.metrics import CompetitionMetricAccumulator

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WEIGHTS_DIR = os.path.join(PROJECT_ROOT, "weights")
DEFAULT_TRAIN_DIR = os.environ.get("TRAIN_DIR", os.path.join(PROJECT_ROOT, "data", "train"))


def parse_args():
    parser = argparse.ArgumentParser(description="Обучение моделей Fire-Operator")
    parser.add_argument(
        "--train-dir",
        type=str,
        default=DEFAULT_TRAIN_DIR,
        help="Путь к обучающим данным (папки af/ и bs/)"
    )
    parser.add_argument(
        "--weights-dir",
        type=str,
        default=WEIGHTS_DIR,
        help="Директория сохранения весов моделей"
    )
    return parser.parse_args()


def get_splits(train_dir: str):
    """
    Изолированное разделение датасета на train и val с группировкой по пожарам (fire_event_id)
    для предотвращения пространственной утечки данных.
    """
    meta_af_p = os.path.join(train_dir, "af", "meta.csv")
    meta_bs_p = os.path.join(train_dir, "bs", "meta.csv")
    
    if not os.path.exists(meta_af_p) or not os.path.exists(meta_bs_p):
        raise FileNotFoundError(f"Файлы meta.csv не найдены в {train_dir}/af или {train_dir}/bs")

    meta_af = pd.read_csv(meta_af_p)
    meta_bs = pd.read_csv(meta_bs_p)

    np.random.seed(42)

    # 1. AF сплит
    if "fire_event_id" in meta_af.columns and meta_af["fire_event_id"].dropna().nunique() > 1:
        events = meta_af["fire_event_id"].dropna().unique()
        np.random.shuffle(events)
        split_idx = int(len(events) * 0.8)
        train_events = set(events[:split_idx])
        train_af = meta_af[meta_af["fire_event_id"].isin(train_events)]["chip_id"].tolist()
        val_af = meta_af[~meta_af["fire_event_id"].isin(train_events)]["chip_id"].tolist()
    else:
        pos_af = meta_af[meta_af["n_fire_px"] > 0]["chip_id"].tolist()
        neg_af = meta_af[meta_af["n_fire_px"] == 0]["chip_id"].tolist()
        np.random.shuffle(pos_af)
        np.random.shuffle(neg_af)
        n_pos_tr = int(len(pos_af) * 0.8)
        n_neg_tr = int(len(neg_af) * 0.8)
        train_af = pos_af[:n_pos_tr] + neg_af[:n_neg_tr]
        val_af = pos_af[n_pos_tr:] + neg_af[n_neg_tr:]

    # 2. BS сплит с группировкой по пожарам
    if "fire_event_id" in meta_bs.columns and meta_bs["fire_event_id"].dropna().nunique() > 1:
        events_bs = meta_bs["fire_event_id"].dropna().unique()
        np.random.shuffle(events_bs)
        split_idx_bs = int(len(events_bs) * 0.75)
        train_events_bs = set(events_bs[:split_idx_bs])
        train_bs = meta_bs[meta_bs["fire_event_id"].isin(train_events_bs)]["chip_id"].tolist()
        val_bs = meta_bs[~meta_bs["fire_event_id"].isin(train_events_bs)]["chip_id"].tolist()
    else:
        all_bs = meta_bs["chip_id"].tolist()
        np.random.shuffle(all_bs)
        n_bs_train = int(len(all_bs) * 0.75)
        train_bs = all_bs[:n_bs_train]
        val_bs = all_bs[n_bs_train:]

    assert len(set(train_af).intersection(set(val_af))) == 0, "AF train and val overlap!"
    assert len(set(train_bs).intersection(set(val_bs))) == 0, "BS train and val overlap!"
    
    return train_af, val_af, train_bs, val_bs


def train_af_model(train_chips: list[str], train_dir: str, weights_dir: str):
    print(f"\n--- [1/2] Сбор признаков и обучение LightGBM AF на {len(train_chips)} чипах ---")
    af_dir = os.path.join(train_dir, "af")
    
    X_list = []
    y_list = []
    np.random.seed(42)
    t0 = time.time()
    
    for chip_id in train_chips:
        viirs_path = os.path.join(af_dir, "viirs", f"{chip_id}_VIIRS_I1-I5.tif")
        aux_path = os.path.join(af_dir, "aux", f"{chip_id}_AUX.tif")
        mask_path = os.path.join(af_dir, "masks", f"{chip_id}_MASK.tif")
        
        if not (os.path.exists(viirs_path) and os.path.exists(aux_path) and os.path.exists(mask_path)):
            continue
            
        with rasterio.open(viirs_path) as s: viirs = s.read()
        with rasterio.open(aux_path) as s: aux = s.read()
        with rasterio.open(mask_path) as s: mask = s.read(1)
            
        feat = extract_af_features(viirs, aux)
        labels = (mask > 0).astype(np.uint8).ravel()
        
        pos_idx = np.where(labels == 1)[0]
        neg_idx = np.where(labels == 0)[0]
        
        if len(pos_idx) > 0:
            # Берём все горящие пиксели
            X_list.append(feat[pos_idx])
            y_list.append(labels[pos_idx])
            
            # Сэмплируем сложные негативы из горящего чипа (пиксели рядом с пожаром и самые горячие точки фона)
            sample_neg_count = min(len(pos_idx) * 4, len(neg_idx))
            sample_neg = np.random.choice(neg_idx, size=sample_neg_count, replace=False)
            X_list.append(feat[sample_neg])
            y_list.append(labels[sample_neg])
        else:
            # Чип без пожара: отбираем самые горячие точки (блики, прогретая почва, вода)
            i4_vals = feat[neg_idx, 0]
            dt_vals = feat[neg_idx, 2]
            hard_score = i4_vals + dt_vals * 2.0
            hard_neg_idx = neg_idx[np.argsort(hard_score)[-120:]]
            X_list.append(feat[hard_neg_idx])
            y_list.append(labels[hard_neg_idx])
            
    if not X_list:
        raise RuntimeError("Не найдено данных для обучения AF!")

    X_train = np.vstack(X_list)
    y_train = np.concatenate(y_list)
    print(f"Матрица AF: {X_train.shape}, y=1: {(y_train==1).sum()}, y=0: {(y_train==0).sum()} за {time.time()-t0:.1f} с")
    
    # Обучаем LightGBM
    clf = LGBMClassifier(
        n_estimators=180,
        learning_rate=0.06,
        num_leaves=31,
        max_depth=6,
        subsample=0.8,
        colsample_bytree=0.8,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
        verbosity=-1
    )
    clf.fit(X_train, y_train)
    
    os.makedirs(weights_dir, exist_ok=True)
    out_path = os.path.join(weights_dir, "af_model.joblib")
    joblib.dump(clf, out_path)
    print(f"Модель AF успешно сохранена: {out_path}")
    return clf


def train_bs_model(train_chips: list[str], train_dir: str, weights_dir: str):
    print(f"\n--- [2/2] Сбор признаков и обучение LightGBM BS на {len(train_chips)} чипах ---")
    bs_dir = os.path.join(train_dir, "bs")
    
    X_list = []
    y_list = []
    np.random.seed(42)
    t0 = time.time()
    
    for chip_id in train_chips:
        s2_pre_p = os.path.join(bs_dir, "sentinel2_pre", f"{chip_id}_Sentinel-2_pre.tif")
        s2_post_p = os.path.join(bs_dir, "sentinel2_post", f"{chip_id}_Sentinel-2_post.tif")
        s1_pre_p = os.path.join(bs_dir, "sentinel1_pre", f"{chip_id}_Sentinel-1_pre.tif")
        s1_post_p = os.path.join(bs_dir, "sentinel1_post", f"{chip_id}_Sentinel-1_post.tif")
        aux_p = os.path.join(bs_dir, "aux", f"{chip_id}_AUX.tif")
        mask_p = os.path.join(bs_dir, "masks", f"{chip_id}_MASK.tif")
        
        if not all(os.path.exists(p) for p in [s2_pre_p, s2_post_p, s1_pre_p, s1_post_p, aux_p, mask_p]):
            continue
            
        with rasterio.open(s2_pre_p) as s: s2_pre = s.read()
        with rasterio.open(s2_post_p) as s: s2_post = s.read()
        with rasterio.open(s1_pre_p) as s: s1_pre = s.read()
        with rasterio.open(s1_post_p) as s: s1_post = s.read()
        with rasterio.open(aux_p) as s: aux = s.read()
        with rasterio.open(mask_p) as s: mask = s.read(1)
        
        feat, cloud_mask = extract_bs_features(s2_pre, s2_post, s1_pre, s1_post, aux)
        labels = mask.ravel()
        valid_flat = cloud_mask.ravel()
        
        # Для классов гари (1, 2, 3) берём ВСЕ доступные валидные пиксели (или до 1500 каждого)
        for cls in (1, 2, 3):
            cls_idx = np.where((labels == cls) & valid_flat)[0]
            if len(cls_idx) > 0:
                n_sample = min(1500, len(cls_idx))
                sample_idx = np.random.choice(cls_idx, size=n_sample, replace=False)
                X_list.append(feat[sample_idx])
                y_list.append(labels[sample_idx])
                
        # Для класса 0 (фон): отбираем сбалансированное количество (до 2000 пикселей с чипа)
        cls0_idx = np.where((labels == 0) & valid_flat)[0]
        if len(cls0_idx) > 0:
            sample_cls0 = np.random.choice(cls0_idx, size=min(2000, len(cls0_idx)), replace=False)
            X_list.append(feat[sample_cls0])
            y_list.append(labels[sample_cls0])
                
    if not X_list:
        raise RuntimeError("Не найдено данных для обучения BS!")

    X_train = np.vstack(X_list)
    y_train = np.concatenate(y_list)
    print(f"Матрица BS: {X_train.shape}, распределение классов: {np.bincount(y_train)} за {time.time()-t0:.1f} с")
    
    # Обучаем многоклассовый LightGBM
    clf = LGBMClassifier(
        objective="multiclass",
        num_class=4,
        n_estimators=180,
        learning_rate=0.07,
        num_leaves=35,
        max_depth=6,
        subsample=0.8,
        colsample_bytree=0.8,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
        verbosity=-1
    )
    clf.fit(X_train, y_train)
    
    os.makedirs(weights_dir, exist_ok=True)
    out_path = os.path.join(weights_dir, "bs_model.joblib")
    joblib.dump(clf, out_path)
    print(f"Модель BS успешно сохранена: {out_path}")
    return clf


def validate_strictly_unseen(af_model, bs_model, val_af: list[str], val_bs: list[str], train_dir: str):
    """Строгая проверка на отложенных чипах с синхронизированными боевыми порогами."""
    print(f"\n--- СТРОГАЯ ВАЛИДАЦИЯ НА {len(val_af)} AF И {len(val_bs)} BS НЕВИДАННЫХ ЧИПАХ ---")
    acc = CompetitionMetricAccumulator()
    af_dir = os.path.join(train_dir, "af")
    bs_dir = os.path.join(train_dir, "bs")
    
    # 1. AF чипы
    t_val_af = time.time()
    for chip_id in val_af:
        viirs_p = os.path.join(af_dir, "viirs", f"{chip_id}_VIIRS_I1-I5.tif")
        aux_p = os.path.join(af_dir, "aux", f"{chip_id}_AUX.tif")
        mask_p = os.path.join(af_dir, "masks", f"{chip_id}_MASK.tif")
        if not (os.path.exists(viirs_p) and os.path.exists(aux_p) and os.path.exists(mask_p)):
            continue
            
        with rasterio.open(viirs_p) as s: viirs = s.read()
        with rasterio.open(aux_p) as s: aux = s.read()
        with rasterio.open(mask_p) as s: gt_mask = s.read(1)
        
        X = extract_af_features(viirs, aux)
        probs = af_model.predict_proba(X)[:, 1]
        
        # Физическая фильтрация с защитой от насыщения
        i4 = X[:, 0]
        dt = X[:, 2]
        pred_bin = ((probs > 0.55) & (i4 > 305.0) & (dt > 4.0)) | (i4 >= 366.5)
        pred_mask = pred_bin.astype(np.uint8).reshape((256, 256))
        acc.update_af(pred_mask, gt_mask)
        
    print(f"Валидация AF завершена за {time.time()-t_val_af:.1f} с")

    # 2. BS чипы
    t_val_bs = time.time()
    for chip_id in val_bs:
        s2_pre_p = os.path.join(bs_dir, "sentinel2_pre", f"{chip_id}_Sentinel-2_pre.tif")
        s2_post_p = os.path.join(bs_dir, "sentinel2_post", f"{chip_id}_Sentinel-2_post.tif")
        s1_pre_p = os.path.join(bs_dir, "sentinel1_pre", f"{chip_id}_Sentinel-1_pre.tif")
        s1_post_p = os.path.join(bs_dir, "sentinel1_post", f"{chip_id}_Sentinel-1_post.tif")
        aux_p = os.path.join(bs_dir, "aux", f"{chip_id}_AUX.tif")
        mask_p = os.path.join(bs_dir, "masks", f"{chip_id}_MASK.tif")
        if not all(os.path.exists(p) for p in [s2_pre_p, s2_post_p, s1_pre_p, s1_post_p, aux_p, mask_p]):
            continue
            
        with rasterio.open(s2_pre_p) as s: s2_pre = s.read()
        with rasterio.open(s2_post_p) as s: s2_post = s.read()
        with rasterio.open(s1_pre_p) as s: s1_pre = s.read()
        with rasterio.open(s1_post_p) as s: s1_post = s.read()
        with rasterio.open(aux_p) as s: aux = s.read()
        with rasterio.open(mask_p) as s: gt_mask = s.read(1)
        
        # Строгая попиксельная синхронизация с inference.py
        X, cloud_mask = extract_bs_features(s2_pre, s2_post, s1_pre, s1_post, aux)
        probs = bs_model.predict_proba(X)
        p_burn = 1.0 - probs[:, 0]
        sev_class = np.argmax(probs[:, 1:4], axis=1) + 1
        
        pred_mask = np.where(p_burn > 0.88, sev_class, 0).reshape((512, 512)).astype(np.uint8)
        pred_mask[~cloud_mask] = 0
        pred_mask = median_filter(pred_mask, size=3)
        
        burn_binary = pred_mask > 0
        cleaned_binary = _remove_small(burn_binary, min_size=25)
        pred_mask[~cleaned_binary] = 0
        acc.update_bs(pred_mask, gt_mask)
        
    print(f"Валидация BS завершена за {time.time()-t_val_bs:.1f} с")

    metrics = acc.compute()
    print("\n" + "=" * 55)
    print("ИТОГОВЫЕ МЕТРИКИ НА НЕВИДАННЫХ ДАННЫХ (LIGHTGBM):")
    for k, v in metrics.items():
        print(f"  {k:10s}: {v:.4f}")
    print("=" * 55)
    return metrics


if __name__ == "__main__":
    args = parse_args()
    t_start = time.time()
    print(f"Папка с обучающими данными: {args.train_dir}")
    print(f"Папка для сохранения весов: {args.weights_dir}")

    train_af, val_af, train_bs, val_bs = get_splits(args.train_dir)
    print(f"Сплит: AF={len(train_af)} train / {len(val_af)} val; BS={len(train_bs)} train / {len(val_bs)} val")
    
    af_model = train_af_model(train_af, args.train_dir, args.weights_dir)
    bs_model = train_bs_model(train_bs, args.train_dir, args.weights_dir)
    validate_strictly_unseen(af_model, bs_model, val_af, val_bs, args.train_dir)
    print(f"\nПолный цикл переобучения и валидации завершен за {time.time()-t_start:.1f} с.")
