"""OOF-калибровка параметров боевого инференса.

Скрипт намеренно не перезаписывает weights/*.joblib и не изменяет inference.py.
Он обучает модели на train-fold'ах, получает прогнозы на полностью невиданных
fire_event_id и сравнивает именно те правила, которые применяет inference.py.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from scipy.ndimage import label, median_filter
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

# Позволяет запускать файл напрямую: python ml/calibrate.py ...
if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.features_af import extract_af_features
from ml.features_bs import extract_bs_features
from ml.utils.metrics import CompetitionMetricAccumulator


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class BsConfig:
    burn_threshold: float
    median_size: int
    min_component_px: int

    @property
    def key(self) -> str:
        return f"p={self.burn_threshold:.2f}, median={self.median_size}, min_px={self.min_component_px}"


def remove_small_components(binary_mask: np.ndarray, min_size: int) -> np.ndarray:
    """Точная копия постобработки inference.py, но без изменения production-кода."""
    if min_size <= 1:
        return binary_mask
    labels, count = label(binary_mask)
    if count == 0:
        return binary_mask
    sizes = np.bincount(labels.ravel())
    keep = sizes >= min_size
    keep[0] = False
    return keep[labels]


def read_meta(train_dir: Path, kind: str):
    import pandas as pd

    path = train_dir / kind / "meta.csv"
    if not path.exists():
        raise FileNotFoundError(f"Не найден {path}")
    meta = pd.read_csv(path)
    if "chip_id" not in meta.columns:
        raise ValueError(f"В {path} отсутствует колонка 'chip_id'")
    
    # В официальном датасете fire_event_id в af/meta.csv пустой (NaN)
    if "fire_event_id" not in meta.columns or meta["fire_event_id"].isna().all():
        if "acq_datetime" in meta.columns:
            # Группировка по дате съемки для предотвращения temporal/spatial data leakage
            meta["fire_event_id"] = meta["acq_datetime"].astype(str).str[:10]
        else:
            meta["fire_event_id"] = meta["chip_id"]
    elif meta["fire_event_id"].isna().any():
        fallback = meta["acq_datetime"].astype(str).str[:10] if "acq_datetime" in meta.columns else meta["chip_id"]
        meta["fire_event_id"] = meta["fire_event_id"].fillna(fallback)
    return meta


def af_paths(train_dir: Path, chip_id: str) -> tuple[Path, Path, Path]:
    root = train_dir / "af"
    return (
        root / "viirs" / f"{chip_id}_VIIRS_I1-I5.tif",
        root / "aux" / f"{chip_id}_AUX.tif",
        root / "masks" / f"{chip_id}_MASK.tif",
    )


def bs_paths(train_dir: Path, chip_id: str) -> tuple[Path, Path, Path, Path, Path, Path]:
    root = train_dir / "bs"
    return (
        root / "sentinel2_pre" / f"{chip_id}_Sentinel-2_pre.tif",
        root / "sentinel2_post" / f"{chip_id}_Sentinel-2_post.tif",
        root / "sentinel1_pre" / f"{chip_id}_Sentinel-1_pre.tif",
        root / "sentinel1_post" / f"{chip_id}_Sentinel-1_post.tif",
        root / "aux" / f"{chip_id}_AUX.tif",
        root / "masks" / f"{chip_id}_MASK.tif",
    )


def read_af(train_dir: Path, chip_id: str) -> tuple[np.ndarray, np.ndarray]:
    viirs_p, aux_p, mask_p = af_paths(train_dir, chip_id)
    if not all(p.exists() for p in (viirs_p, aux_p, mask_p)):
        raise FileNotFoundError(f"Неполный набор AF-файлов для {chip_id}")
    with rasterio.open(viirs_p) as src:
        viirs = src.read()
    with rasterio.open(aux_p) as src:
        aux = src.read()
    with rasterio.open(mask_p) as src:
        target = src.read(1)
    return extract_af_features(viirs, aux), target


def read_bs(train_dir: Path, chip_id: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    paths = bs_paths(train_dir, chip_id)
    if not all(p.exists() for p in paths):
        raise FileNotFoundError(f"Неполный набор BS-файлов для {chip_id}")
    with rasterio.open(paths[0]) as src:
        s2_pre = src.read()
    with rasterio.open(paths[1]) as src:
        s2_post = src.read()
    with rasterio.open(paths[2]) as src:
        s1_pre = src.read()
    with rasterio.open(paths[3]) as src:
        s1_post = src.read()
    with rasterio.open(paths[4]) as src:
        aux = src.read()
    with rasterio.open(paths[5]) as src:
        target = src.read(1)
    features, cloud_mask = extract_bs_features(s2_pre, s2_post, s1_pre, s1_post, aux)
    return features, cloud_mask, target


def fit_af(train_dir: Path, chip_ids: list[str], seed: int):
    rng = np.random.default_rng(seed)
    features, labels = [], []
    for chip_id in chip_ids:
        x, target = read_af(train_dir, chip_id)
        y = (target > 0).astype(np.uint8).ravel()
        pos = np.flatnonzero(y == 1)
        neg = np.flatnonzero(y == 0)
        if pos.size:
            features.extend((x[pos], x[rng.choice(neg, size=min(pos.size * 3, neg.size), replace=False)]))
            labels.extend((y[pos], y[rng.choice(neg, size=min(pos.size * 3, neg.size), replace=False)]))
        elif neg.size:
            hard = neg[np.argsort(x[neg, 0])[-min(80, neg.size):]]
            features.append(x[hard])
            labels.append(y[hard])
    model = make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=300, random_state=seed))
    model.fit(np.vstack(features), np.concatenate(labels))
    return model


def fit_bs(train_dir: Path, chip_ids: list[str], seed: int):
    rng = np.random.default_rng(seed)
    features, labels = [], []
    for chip_id in chip_ids:
        x, valid, target = read_bs(train_dir, chip_id)
        y = target.ravel()
        valid_flat = valid.ravel()
        for cls in (0, 1, 2, 3):
            idx = np.flatnonzero((y == cls) & valid_flat)
            if idx.size:
                sample = rng.choice(idx, size=min(600, idx.size), replace=False)
                features.append(x[sample])
                labels.append(y[sample])
    model = make_pipeline(StandardScaler(), MLPClassifier(hidden_layer_sizes=(96, 48), max_iter=200, random_state=seed))
    model.fit(np.vstack(features), np.concatenate(labels))
    return model


def metric_dict(acc: CompetitionMetricAccumulator) -> dict[str, float]:
    return {key: round(float(value), 6) for key, value in acc.compute().items()}


def calibrate(train_dir: Path, folds: int, seed: int, af_thresholds: list[float], bs_configs: list[BsConfig]):
    af_meta = read_meta(train_dir, "af")
    bs_meta = read_meta(train_dir, "bs")
    if af_meta.fire_event_id.nunique() < folds or bs_meta.fire_event_id.nunique() < folds:
        raise ValueError("Число folds больше числа уникальных fire_event_id")

    af_acc = {threshold: CompetitionMetricAccumulator() for threshold in af_thresholds}
    bs_acc = {config: CompetitionMetricAccumulator() for config in bs_configs}

    for kind, meta in (("AF", af_meta), ("BS", bs_meta)):
        splitter = GroupKFold(n_splits=folds)
        chip_ids = meta.chip_id.astype(str).to_numpy()
        groups = meta.fire_event_id.astype(str).to_numpy()
        for fold, (train_idx, val_idx) in enumerate(splitter.split(chip_ids, groups=groups), start=1):
            train_ids, val_ids = chip_ids[train_idx].tolist(), chip_ids[val_idx].tolist()
            print(f"{kind}: fold {fold}/{folds}; train={len(train_ids)}, val={len(val_ids)}", flush=True)
            model = fit_af(train_dir, train_ids, seed + fold) if kind == "AF" else fit_bs(train_dir, train_ids, seed + fold)
            for chip_id in val_ids:
                if kind == "AF":
                    x, target = read_af(train_dir, chip_id)
                    prob = model.predict_proba(x)[:, 1]
                    # Все условия совпадают с inference.py; меняется только probability threshold.
                    for threshold, acc in af_acc.items():
                        pred = (((prob > threshold) & (x[:, 0] > 305.0) & (x[:, 2] > 4.0)) | (x[:, 0] >= 366.5))
                        acc.update_af(pred.reshape(target.shape), target)
                else:
                    x, cloud, target = read_bs(train_dir, chip_id)
                    prob = model.predict_proba(x)
                    p_burn = 1.0 - prob[:, 0]
                    severity = np.argmax(prob[:, 1:4], axis=1) + 1
                    for config, acc in bs_acc.items():
                        pred = np.where(p_burn > config.burn_threshold, severity, 0).reshape(target.shape).astype(np.uint8)
                        pred[~cloud] = 0
                        if config.median_size > 1:
                            pred = median_filter(pred, size=config.median_size)
                        keep = remove_small_components(pred > 0, config.min_component_px)
                        pred[~keep] = 0
                        acc.update_bs(pred, target)

    af_results = {f"p={threshold:.2f}": metric_dict(acc) for threshold, acc in af_acc.items()}
    bs_results = {config.key: metric_dict(acc) for config, acc in bs_acc.items()}
    best_af_key, best_af = max(af_results.items(), key=lambda item: item[1]["F1_af"])
    best_bs_key, best_bs = max(
        bs_results.items(),
        key=lambda item: 0.35 * item[1]["IoU_burn"] + 0.30 * item[1]["mIoU_sev"],
    )
    baseline_af = af_results.get("p=0.85", next(iter(af_results.values())))
    baseline_bs = bs_results.get("p=0.88, median=3, min_px=25", next(iter(bs_results.values())))
    baseline_score = 0.35 * baseline_af["F1_af"] + 0.35 * baseline_bs["IoU_burn"] + 0.30 * baseline_bs["mIoU_sev"]
    best_score = 0.35 * best_af["F1_af"] + 0.35 * best_bs["IoU_burn"] + 0.30 * best_bs["mIoU_sev"]
    return {
        "method": "Grouped out-of-fold CV by fire_event_id; no test data used",
        "folds": folds,
        "seed": seed,
        "production_baseline": {
            "af": "p=0.85",
            "bs": "p=0.88, median=3, min_px=25",
            "score": round(baseline_score, 6),
        },
        "best_candidate": {
            "af": best_af_key,
            "bs": best_bs_key,
            "score": round(best_score, 6),
            "delta_vs_baseline": round(best_score - baseline_score, 6),
        },
        "af_candidates": af_results,
        "bs_candidates": bs_results,
        "note": "Переносить параметры в inference.py следует только при положительном delta_vs_baseline и после замера скорости.",
    }


def parse_args():
    parser = argparse.ArgumentParser(description="OOF-калибровка параметров Fire-Operator без перезаписи весов")
    parser.add_argument("--train-dir", required=True, type=Path, help="Каталог train с папками af/ и bs/")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "artifacts" / "calibration.json")
    parser.add_argument("--folds", type=int, default=4)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main():
    args = parse_args()
    af_thresholds = [0.75, 0.80, 0.85, 0.90, 0.95]
    bs_configs = [
        BsConfig(threshold, median, min_px)
        for threshold in (0.78, 0.83, 0.88, 0.93)
        for median in (1, 3)
        for min_px in (0, 9, 25)
    ]
    result = calibrate(args.train_dir, args.folds, args.seed, af_thresholds, bs_configs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["production_baseline"], ensure_ascii=False))
    print(json.dumps(result["best_candidate"], ensure_ascii=False))
    print(f"Результат сохранён: {args.output}")


if __name__ == "__main__":
    main()
