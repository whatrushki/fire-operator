import sys

modules = [
    "numpy",
    "pandas",
    "scipy",
    "sklearn",
    "lightgbm",
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

def test_dependencies():
    for m in modules:
        mod = __import__(m, fromlist=["*"])
        assert mod is not None, f"Failed to import {m}"
    print("\nALL PROJECT DEPENDENCIES IMPORTED SUCCESSFULLY!")

if __name__ == "__main__":
    test_dependencies()
