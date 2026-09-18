import sys

modules = [
    "sklearn.linear_model",
    "sklearn.naive_bayes",
    "sklearn.preprocessing",
    "sklearn.metrics",
    "scipy.optimize",
    "scipy.spatial",
    "torch",
    "xgboost",
    "lightgbm",
    "catboost"
]

for m in modules:
    try:
        mod = __import__(m, fromlist=["*"])
        print(f"{m}: OK")
    except Exception as e:
        print(f"{m}: FAILED ({type(e).__name__}: {e})")
