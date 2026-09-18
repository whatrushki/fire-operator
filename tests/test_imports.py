import sys

modules = [
    "numpy",
    "pandas",
    "scipy",
    "sklearn",
    "sklearn.linear_model",
    "sklearn.neural_network",
    "sklearn.preprocessing",
    "rasterio",
    "shapely",
    "geopandas",
    "pyproj",
    "pyogrio",
    "joblib",
    "fastapi",
    "uvicorn",
    "pydantic"
]

all_ok = True
for m in modules:
    try:
        mod = __import__(m, fromlist=["*"])
        print(f"{m:25s}: OK")
    except Exception as e:
        print(f"{m:25s}: FAILED ({type(e).__name__}: {e})")
        all_ok = False

if not all_ok:
    sys.exit(1)
print("\nALL PROJECT DEPENDENCIES IMPORTED SUCCESSFULLY!")
