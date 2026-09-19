import os
import sys
import numpy as np
import joblib

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def test_models_load_and_predict():
    af_path = os.path.join(PROJECT_ROOT, "weights", "af_model.joblib")
    bs_path = os.path.join(PROJECT_ROOT, "weights", "bs_model.joblib")
    
    assert os.path.exists(af_path), f"Missing {af_path}"
    assert os.path.exists(bs_path), f"Missing {bs_path}"
    
    af_model = joblib.load(af_path)
    bs_model = joblib.load(bs_path)
    
    # AF model takes 24 features
    X_af_dummy = np.zeros((10, 24), dtype=np.float32)
    p_af = af_model.predict_proba(X_af_dummy)
    assert p_af.shape == (10, 2), f"Unexpected AF shape: {p_af.shape}"
    
    # BS model takes 26 features
    X_bs_dummy = np.zeros((10, 26), dtype=np.float32)
    p_bs = bs_model.predict(X_bs_dummy)
    assert p_bs.shape == (10,), f"Unexpected BS shape: {p_bs.shape}"
    print("Trained LightGBM models loaded and verified successfully!")

if __name__ == "__main__":
    test_models_load_and_predict()
