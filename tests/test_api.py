import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_map_page():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Fire-Operator" in resp.text
    assert "Leaflet" in resp.text or "map" in resp.text
    print("Map UI test PASS")


def test_health():
    response = client.get("/api/v1/health")
    assert response.status_code == 200, f"Health check failed: {response.text}"
    data = response.json()
    assert data["status"] == "healthy"
    print("Health check PASS:", data)


def test_analyze_and_report_cycle():
    # 1. POST /analyze
    payload = {
        "bbox": [43.0, 47.0, 45.5, 48.5],
        "date_from": "2024-05-01",
        "date_to": "2024-09-30",
        "include_radar": True
    }
    resp = client.post("/api/v1/analyze", json=payload)
    assert resp.status_code == 202, f"Analyze failed: {resp.text}"
    init_data = resp.json()
    task_id = init_data["task_id"]
    print(f"Task initiated: task_id={task_id}")

    # Небольшая пауза для выполнения фоновой задачи
    time.sleep(1.0)

    # 2. GET /tasks/{task_id}
    resp = client.get(f"/api/v1/tasks/{task_id}")
    assert resp.status_code == 200
    task_data = resp.json()
    assert task_data["status"] == "completed", f"Task not completed: {task_data}"
    print("Task status PASS:", task_data)

    # 3. GET /report/{task_id}
    resp = client.get(f"/api/v1/report/{task_id}")
    assert resp.status_code == 200
    report_data = resp.json()
    assert "total_burned_area_ha" in report_data
    assert len(report_data["breakdown"]) == 3
    assert report_data["active_thermal_anomalies_count"] > 0
    print("Analytical Report PASS: Total burned area =", report_data["total_burned_area_ha"], "ha")

    # 4. GET /export/geojson/{task_id}
    resp = client.get(f"/api/v1/export/geojson/{task_id}")
    assert resp.status_code == 200
    geojson_data = resp.json()
    assert geojson_data["type"] == "FeatureCollection"
    print(f"GeoJSON export PASS: {len(geojson_data['features'])} features")

    # 5. GET /export/thermal-points/{task_id}
    resp = client.get(f"/api/v1/export/thermal-points/{task_id}")
    assert resp.status_code == 200
    th_data = resp.json()
    assert th_data["type"] == "FeatureCollection"
    print(f"Thermal points export PASS: {len(th_data['features'])} points")

    # 6. GET /export/shapefile/{task_id}
    resp = client.get(f"/api/v1/export/shapefile/{task_id}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    print(f"Shapefile ZIP export PASS: {len(resp.content)} bytes")

    # 7. GET /export/report/{task_id} (Machine-readable JSON export)
    resp = client.get(f"/api/v1/export/report/{task_id}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/json"
    rep_export = resp.json()
    assert "total_burned_area_ha" in rep_export
    print("Machine-readable JSON report export PASS!")


if __name__ == "__main__":
    test_map_page()
    test_health()
    test_analyze_and_report_cycle()
    print("\nALL BACKEND API TESTS PASSED!")
