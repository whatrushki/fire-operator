"""
Метрики соревнований «КосмоХакатон 2026: Мониторинг природных пожаров»:
- F1_af: F1-score для задачи AF (Active Fire), микро-усреднение;
- IoU_burn: IoU для задачи BS (бинарный контур гари: 1 U 2 U 3 против 0), микро-усреднение;
- mIoU_sev: Средний IoU по 3 классам степени поражения (1, 2, 3), микро-усреднение;
- Score = 0.35 * F1_af + 0.35 * IoU_burn + 0.30 * mIoU_sev.
"""
import numpy as np


class CompetitionMetricAccumulator:
    """
    Аккумулятор пиксельных статистик TP, FP, FN для строгого микро-усреднения
    в соответствии с регламентом соревнований.
    """
    def __init__(self):
        # AF статистика (бинарная)
        self.af_tp = 0
        self.af_fp = 0
        self.af_fn = 0
        
        # BS бинарная статистика (гарь: классы 1, 2, 3)
        self.burn_tp = 0
        self.burn_fp = 0
        self.burn_fn = 0
        
        # BS поклассовая статистика (степени 1, 2, 3)
        self.sev_tp = {1: 0, 2: 0, 3: 0}
        self.sev_fp = {1: 0, 2: 0, 3: 0}
        self.sev_fn = {1: 0, 2: 0, 3: 0}

    def update_af(self, pred_mask: np.ndarray, gt_mask: np.ndarray):
        """Обновляет статистику по чипу AF."""
        p = (pred_mask > 0).astype(bool)
        g = (gt_mask > 0).astype(bool)
        
        self.af_tp += int(np.logical_and(p, g).sum())
        self.af_fp += int(np.logical_and(p, ~g).sum())
        self.af_fn += int(np.logical_and(~p, g).sum())

    def update_bs(self, pred_mask: np.ndarray, gt_mask: np.ndarray):
        """Обновляет статистику по чипу BS (маски со значениями 0, 1, 2, 3)."""
        # 1. Бинарный контур гари
        p_burn = (pred_mask > 0)
        g_burn = (gt_mask > 0)
        
        self.burn_tp += int(np.logical_and(p_burn, g_burn).sum())
        self.burn_fp += int(np.logical_and(p_burn, ~g_burn).sum())
        self.burn_fn += int(np.logical_and(~p_burn, g_burn).sum())
        
        # 2. Поклассово для степеней 1, 2, 3
        for k in (1, 2, 3):
            pk = (pred_mask == k)
            gk = (gt_mask == k)
            self.sev_tp[k] += int(np.logical_and(pk, gk).sum())
            self.sev_fp[k] += int(np.logical_and(pk, ~gk).sum())
            self.sev_fn[k] += int(np.logical_and(~pk, gk).sum())

    @staticmethod
    def _compute_f1(tp: int, fp: int, fn: int) -> float:
        if tp == 0 and fp == 0 and fn == 0:
            return 1.0
        if tp == 0:
            return 0.0
        precision = tp / (tp + fp)
        recall = tp / (tp + fn)
        if precision + recall == 0:
            return 0.0
        return 2 * precision * recall / (precision + recall)

    @staticmethod
    def _compute_iou(tp: int, fp: int, fn: int) -> float:
        denom = tp + fp + fn
        if denom == 0:
            return 1.0
        if tp == 0:
            return 0.0
        return tp / denom

    def compute(self) -> dict[str, float]:
        """Вычисляет итоговые метрики и общий Score."""
        f1_af = self._compute_f1(self.af_tp, self.af_fp, self.af_fn)
        iou_burn = self._compute_iou(self.burn_tp, self.burn_fp, self.burn_fn)
        
        iou_sev1 = self._compute_iou(self.sev_tp[1], self.sev_fp[1], self.sev_fn[1])
        iou_sev2 = self._compute_iou(self.sev_tp[2], self.sev_fp[2], self.sev_fn[2])
        iou_sev3 = self._compute_iou(self.sev_tp[3], self.sev_fp[3], self.sev_fn[3])
        miou_sev = (iou_sev1 + iou_sev2 + iou_sev3) / 3.0
        
        score = 0.35 * f1_af + 0.35 * iou_burn + 0.30 * miou_sev
        
        return {
            "F1_af": f1_af,
            "IoU_burn": iou_burn,
            "IoU_sev1": iou_sev1,
            "IoU_sev2": iou_sev2,
            "IoU_sev3": iou_sev3,
            "mIoU_sev": miou_sev,
            "Score": score
        }
