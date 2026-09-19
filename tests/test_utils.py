import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
import time
from ml.utils.rle import rle_encode, rle_decode
from ml.utils.metrics import CompetitionMetricAccumulator

def test_rle():
    empty_mask = np.zeros((256, 256), dtype=np.uint8)
    assert rle_encode(empty_mask) == '""', "Empty mask encoding failed"
    assert np.array_equal(rle_decode('""', (256, 256)), empty_mask), "Empty decode failed"
    assert np.array_equal(rle_decode(None, (256, 256)), empty_mask), "None decode failed"
    assert np.array_equal(rle_decode(float('nan'), (256, 256)), empty_mask), "NaN float decode failed"
    assert np.array_equal(rle_decode('nan', (256, 256)), empty_mask), "NaN str decode failed"

    # Random sparse mask
    np.random.seed(42)
    mask = (np.random.rand(512, 512) > 0.95).astype(np.uint8)
    t0 = time.perf_counter()
    encoded = rle_encode(mask)
    t_enc = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    decoded = rle_decode(encoded, (512, 512))
    t_dec = (time.perf_counter() - t0) * 1000

    assert np.array_equal(mask, decoded), "Roundtrip failed!"
    print(f"RLE Test PASS: 512x512 encode in {t_enc:.2f} ms, decode in {t_dec:.2f} ms")

def test_metrics():
    acc = CompetitionMetricAccumulator()
    gt_af = np.zeros((256, 256), dtype=np.uint8)
    gt_af[50:60, 50:60] = 1
    pred_af = gt_af.copy()
    acc.update_af(pred_af, gt_af)

    gt_bs = np.zeros((512, 512), dtype=np.uint8)
    gt_bs[100:150, 100:150] = 1
    gt_bs[200:250, 200:250] = 2
    gt_bs[300:350, 300:350] = 3
    pred_bs = gt_bs.copy()
    acc.update_bs(pred_bs, gt_bs)

    res = acc.compute()
    print("Metrics Test Perfect Match:", res)
    assert np.isclose(res['Score'], 1.0), "Perfect score must be 1.0"
    print("ALL UNIT TESTS PASSED!")

if __name__ == "__main__":
    test_rle()
    test_metrics()
