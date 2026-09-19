# -*- coding: utf-8 -*-
import os
import sys
import time
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_invalid_date_format():
    r = client.post('/api/v1/analyze', json={
        'date_from': 'not-a-date',
        'date_to': '2024-06-01',
        'bbox': [44.0, 48.0, 45.0, 49.0]
    })
    assert r.status_code == 400
    assert "Некорректный формат даты" in r.json()["detail"]

def test_inverted_date_range():
    r = client.post('/api/v1/analyze', json={
        'date_from': '2024-08-01',
        'date_to': '2024-05-01',
        'bbox': [44.0, 48.0, 45.0, 49.0]
    })
    assert r.status_code == 400
    assert "не может быть позже" in r.json()["detail"]

def test_invalid_bbox_bounds():
    r = client.post('/api/v1/analyze', json={
        'date_from': '2024-05-01',
        'date_to': '2024-08-01',
        'bbox': [300.0, 48.0, 45.0, 49.0]
    })
    assert r.status_code == 400
    assert "выходят за пределы WGS84" in r.json()["detail"]

def test_malformed_task_id():
    r = client.get('/api/v1/tasks/tsk_bad_format!@#')
    assert r.status_code == 400
    assert "Некорректный идентификатор" in r.json()["detail"]

def test_nonexistent_task_id():
    r = client.get('/api/v1/tasks/tsk_00000000')
    assert r.status_code == 404
    assert "не найдена" in r.json()["detail"]

def test_out_of_coverage_query():
    r = client.post('/api/v1/analyze', json={
        'date_from': '2024-06-01',
        'date_to': '2024-08-01',
        'bbox': [37.5, 55.7, 37.7, 55.8] # Москва (вне покрытия спутниковых сцен)
    })
    assert r.status_code == 202
    task_id = r.json()['task_id']
    
    for _ in range(15):
        st = client.get(f'/api/v1/tasks/{task_id}').json()
        if st['status'] == 'completed':
            break
        time.sleep(0.4)

    rep_resp = client.get(f'/api/v1/report/{task_id}')
    assert rep_resp.status_code == 200
    rep = rep_resp.json()
    assert rep['total_burned_area_ha'] == 0.0
    assert rep['active_thermal_anomalies_count'] == 0
    assert "за пределами зоны покрытия" in rep['summary_message']
    assert "0 га" in rep['summary_message']

def test_winter_season_query():
    r = client.post('/api/v1/analyze', json={
        'date_from': '2024-01-01',
        'date_to': '2024-02-01',
        'bbox': [43.6, 47.7, 44.7, 48.5]
    })
    assert r.status_code == 202
    task_id = r.json()['task_id']
    
    for _ in range(15):
        st = client.get(f'/api/v1/tasks/{task_id}').json()
        if st['status'] == 'completed':
            break
        time.sleep(0.4)

    rep_resp = client.get(f'/api/v1/report/{task_id}')
    assert rep_resp.status_code == 200
    rep = rep_resp.json()
    assert rep['total_burned_area_ha'] == 0.0
    assert "зимний сезон" in rep['summary_message']

def test_real_fire_query():
    r = client.post('/api/v1/analyze', json={
        'date_from': '2024-05-01',
        'date_to': '2024-08-01',
        'bbox': [43.6, 47.7, 44.7, 48.5],
        'region': 'volgograd'
    })
    assert r.status_code == 202
    task_id = r.json()['task_id']
    
    for _ in range(15):
        st = client.get(f'/api/v1/tasks/{task_id}').json()
        if st['status'] == 'completed':
            break
        time.sleep(0.4)

    rep_resp = client.get(f'/api/v1/report/{task_id}')
    assert rep_resp.status_code == 200
    rep = rep_resp.json()
    assert rep['total_burned_area_ha'] > 0.0
    assert rep['active_thermal_anomalies_count'] > 0
    assert "выявлено" in rep['summary_message']

def test_strict_date_no_fire():
    r = client.post('/api/v1/analyze', json={
        'date_from': '2021-05-01',
        'date_to': '2021-05-15',
        'bbox': [46.12, 49.50, 46.34, 49.68],
        'region': 'custom'
    })
    assert r.status_code == 202
    task_id = r.json()['task_id']
    
    for _ in range(15):
        st = client.get(f'/api/v1/tasks/{task_id}').json()
        if st['status'] == 'completed':
            break
        time.sleep(0.4)

    rep_resp = client.get(f'/api/v1/report/{task_id}')
    assert rep_resp.status_code == 200
    rep = rep_resp.json()
    assert rep['total_burned_area_ha'] == 0.0
    assert rep['active_thermal_anomalies_count'] == 0
    assert "не зафиксировано" in rep['summary_message']

def test_synchronized_preset_fire():
    r = client.post('/api/v1/analyze', json={
        'date_from': '2022-08-10',
        'date_to': '2022-08-28',
        'bbox': [46.12, 49.50, 46.34, 49.68]
    })
    assert r.status_code == 202
    task_id = r.json()['task_id']
    
    for _ in range(15):
        st = client.get(f'/api/v1/tasks/{task_id}').json()
        if st['status'] == 'completed':
            break
        time.sleep(0.4)

    rep_resp = client.get(f'/api/v1/report/{task_id}')
    assert rep_resp.status_code == 200
    rep = rep_resp.json()
    assert rep['total_burned_area_ha'] > 0.0
    assert rep['active_thermal_anomalies_count'] > 0

