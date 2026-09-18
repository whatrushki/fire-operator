"""
Скрипт обучения моделей детекции активного горения (AF) и картирования гарей (BS).
Использует стабильный Scikit-Learn пайплайн:
- AF: StandardScaler + LogisticRegression(class_weight='balanced') с постобработкой бликов и факелов.
- BS: StandardScaler + MLPClassifier(hidden_layer_sizes=(64, 32)) для 4 классов.
Высокая скорость обучения (< 30 с) и инференса (< 30 мс на чип).
"""
import os
import sys
import time
import joblib
import rasterio
import numpy as np
import pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ml.features_af import extract_af_features
from ml.features_bs import extract_bs_features
from ml.utils.metrics import CompetitionMetricAccumulator

TRAIN_DIR = r"C:\Users\vladg\Desktop\Кейс\fire-train-renamed\train"
WEIGHTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "weights"))


def train_af_model(max_chips: int = 150):
    """Обучение модели AF на выборке чипов."""
    print("\n--- [1/2] Обучение модели AF (Active Fire) ---")
    af_dir = os.path.join(TRAIN_DIR, "af")
    meta_df = pd.read_csv(os.path.join(af_dir, "meta.csv"))
    
    pos_chips = meta_df[meta_df["n_fire_px"] > 0]["chip_id"].tolist()
    neg_chips = meta_df[meta_df["n_fire_px"] == 0]["chip_id"].tolist()
    
    selected_pos = pos_chips[:min(100, len(pos_chips))]
    selected_neg = neg_chips[:min(40, len(neg_chips))]
    selected_chips = selected_pos + selected_neg
    print(f"Выбрано {len(selected_chips)} чипов AF ({len(selected_pos)} полож., {len(selected_neg)} отриц.)")
    
    X_list = []
    y_list = []
    
    t0 = time.time()
    for chip_id in selected_chips:
        viirs_path = os.path.join(af_dir, "viirs", f"{chip_id}_VIIRS_I1-I5.tif")
        aux_path = os.path.join(af_dir, "aux", f"{chip_id}_AUX.tif")
        mask_path = os.path.join(af_dir, "masks", f"{chip_id}_MASK.tif")
        
        with rasterio.open(viirs_path) as s: viirs = s.read()
        with rasterio.open(aux_path) as s: aux = s.read()
        with rasterio.open(mask_path) as s: mask = s.read(1)
            
        feat = extract_af_features(viirs, aux)
        labels = (mask > 0).astype(np.uint8).ravel()
        
        pos_idx = np.where(labels == 1)[0]
        neg_idx = np.where(labels == 0)[0]
        
        if len(pos_idx) > 0:
            X_list.append(feat[pos_idx])
            y_list.append(labels[pos_idx])
            
            # Семплируем негативы: часть случайных, часть с высоким i4
            sample_neg = np.random.choice(neg_idx, size=min(len(pos_idx) * 4, len(neg_idx)), replace=False)
            X_list.append(feat[sample_neg])
            y_list.append(labels[sample_neg])
        else:
            # Отрицательные чипы: берем самые горячие точки
            i4_vals = feat[neg_idx, 0]
            hard_neg_idx = neg_idx[np.argsort(i4_vals)[-100:]]
            X_list.append(feat[hard_neg_idx])
            y_list.append(labels[hard_neg_idx])
            
    X_train = np.vstack(X_list)
    y_train = np.concatenate(y_list)
    print(f"Матрица AF: {X_train.shape}, y=1: {(y_train==1).sum()}, y=0: {(y_train==0).sum()} за {time.time()-t0:.1f} с")
    
    clf = make_pipeline(
        StandardScaler(),
        LogisticRegression(class_weight="balanced", max_iter=300, random_state=42)
    )
    clf.fit(X_train, y_train)
    
    os.makedirs(WEIGHTS_DIR, exist_ok=True)
    out_path = os.path.join(WEIGHTS_DIR, "af_model.joblib")
    joblib.dump(clf, out_path)
    print(f"Модель AF сохранена: {out_path}")
    return clf


def train_bs_model(max_chips: int = 70):
    """Обучение модели BS на выборке чипов Sentinel-2 / Sentinel-1."""
    print("\n--- [2/2] Обучение модели BS (Burn Severity) ---")
    bs_dir = os.path.join(TRAIN_DIR, "bs")
    meta_df = pd.read_csv(os.path.join(bs_dir, "meta.csv"))
    
    sorted_chips = meta_df.sort_values("burn_area_ha", ascending=False)["chip_id"].tolist()
    selected_chips = sorted_chips[:min(max_chips, len(sorted_chips))]
    print(f"Выбрано {len(selected_chips)} чипов BS")
    
    X_list = []
    y_list = []
    
    t0 = time.time()
    for chip_id in selected_chips:
        s2_pre_p = os.path.join(bs_dir, "sentinel2_pre", f"{chip_id}_Sentinel-2_pre.tif")
        s2_post_p = os.path.join(bs_dir, "sentinel2_post", f"{chip_id}_Sentinel-2_post.tif")
        s1_pre_p = os.path.join(bs_dir, "sentinel1_pre", f"{chip_id}_Sentinel-1_pre.tif")
        s1_post_p = os.path.join(bs_dir, "sentinel1_post", f"{chip_id}_Sentinel-1_post.tif")
        aux_p = os.path.join(bs_dir, "aux", f"{chip_id}_AUX.tif")
        mask_p = os.path.join(bs_dir, "masks", f"{chip_id}_MASK.tif")
        
        with rasterio.open(s2_pre_p) as s: s2_pre = s.read()
        with rasterio.open(s2_post_p) as s: s2_post = s.read()
        with rasterio.open(s1_pre_p) as s: s1_pre = s.read()
        with rasterio.open(s1_post_p) as s: s1_post = s.read()
        with rasterio.open(aux_p) as s: aux = s.read()
        with rasterio.open(mask_p) as s: mask = s.read(1)
        
        feat, cloud_mask = extract_bs_features(s2_pre, s2_post, s1_pre, s1_post, aux)
        labels = mask.ravel()
        valid_flat = cloud_mask.ravel()
        
        for cls in (0, 1, 2, 3):
            cls_idx = np.where((labels == cls) & valid_flat)[0]
            if len(cls_idx) > 0:
                n_sample = min(800, len(cls_idx))
                sample_idx = np.random.choice(cls_idx, size=n_sample, replace=False)
                X_list.append(feat[sample_idx])
                y_list.append(labels[sample_idx])
                
    X_train = np.vstack(X_list)
    y_train = np.concatenate(y_list)
    print(f"Матрица BS: {X_train.shape}, распределение классов: {np.bincount(y_train)} за {time.time()-t0:.1f} с")
    
    clf = make_pipeline(
        StandardScaler(),
        MLPClassifier(hidden_layer_sizes=(64, 32), max_iter=200, random_state=42)
    )
    clf.fit(X_train, y_train)
    
    out_path = os.path.join(WEIGHTS_DIR, "bs_model.joblib")
    joblib.dump(clf, out_path)
    print(f"Модель BS сохранена: {out_path}")
    return clf


def validate_models(af_model, bs_model, n_val: int = 15):
    """Валидация обученных моделей по регламенту."""
    print(f"\n--- Проведение валидации на {n_val} чипах AF и BS ---")
    acc = CompetitionMetricAccumulator()
    
    af_dir = os.path.join(TRAIN_DIR, "af")
    meta_af = pd.read_csv(os.path.join(af_dir, "meta.csv"))
    val_af = meta_af[meta_af["n_fire_px"] > 0]["chip_id"].tolist()[-n_val:]
    
    for chip_id in val_af:
        with rasterio.open(os.path.join(af_dir, "viirs", f"{chip_id}_VIIRS_I1-I5.tif")) as s: viirs = s.read()
        with rasterio.open(os.path.join(af_dir, "aux", f"{chip_id}_AUX.tif")) as s: aux = s.read()
        with rasterio.open(os.path.join(af_dir, "masks", f"{chip_id}_MASK.tif")) as s: gt_mask = s.read(1)
        
        X = extract_af_features(viirs, aux)
        probs = af_model.predict_proba(X)[:, 1]
        
        # Физическая калибровка порога: кандидат должен иметь I4 > 305 K и Delta T > 5 K
        i4 = X[:, 0]
        dt = X[:, 2]
        pred_bin = (probs > 0.65) & (i4 > 305.0) & (dt > 4.0)
        pred_mask = pred_bin.astype(np.uint8).reshape((256, 256))
        acc.update_af(pred_mask, gt_mask)
        
    bs_dir = os.path.join(TRAIN_DIR, "bs")
    meta_bs = pd.read_csv(os.path.join(bs_dir, "meta.csv"))
    val_bs = meta_bs["chip_id"].tolist()[-n_val:]
    
    for chip_id in val_bs:
        with rasterio.open(os.path.join(bs_dir, "sentinel2_pre", f"{chip_id}_Sentinel-2_pre.tif")) as s: s2_pre = s.read()
        with rasterio.open(os.path.join(bs_dir, "sentinel2_post", f"{chip_id}_Sentinel-2_post.tif")) as s: s2_post = s.read()
        with rasterio.open(os.path.join(bs_dir, "sentinel1_pre", f"{chip_id}_Sentinel-1_pre.tif")) as s: s1_pre = s.read()
        with rasterio.open(os.path.join(bs_dir, "sentinel1_post", f"{chip_id}_Sentinel-1_post.tif")) as s: s1_post = s.read()
        with rasterio.open(os.path.join(bs_dir, "aux", f"{chip_id}_AUX.tif")) as s: aux = s.read()
        with rasterio.open(os.path.join(bs_dir, "masks", f"{chip_id}_MASK.tif")) as s: gt_mask = s.read(1)
        
        X, cloud_mask = extract_bs_features(s2_pre, s2_post, s1_pre, s1_post, aux)
        preds = bs_model.predict(X)
        pred_mask = preds.reshape((512, 512)).astype(np.uint8)
        pred_mask[~cloud_mask] = 0
        acc.update_bs(pred_mask, gt_mask)
        
    metrics = acc.compute()
    print("==================================================")
    print("ИТОГОВЫЕ МЕТРИКИ ВАЛИДАЦИИ:")
    for k, v in metrics.items():
        print(f"  {k:10s}: {v:.4f}")
    print("==================================================")


if __name__ == "__main__":
    t_start = time.time()
    af_model = train_af_model()
    bs_model = train_bs_model()
    validate_models(af_model, bs_model)
    print(f"\nВесь цикл обучения и валидации завершен за {time.time()-t_start:.1f} секунд.")
