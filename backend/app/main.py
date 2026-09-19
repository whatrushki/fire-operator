"""
Главная точка входа FastAPI приложения Fire-Operator.
Спроектирована для полного соответствия критериям Раздела 4 («Информационно-аналитический сервис»).
Включает интерактивный Web GIS картографический интерфейс, Swagger UI и ReDoc.
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse

from app.core.config import settings
from app.api.v1.router import api_router

tags_metadata = [
    {
        "name": "Картографический веб-интерфейс (GIS UI)",
        "description": "Интерактивная карта с визуализацией термоточек AF и контуров гарей BS на подложке OpenStreetMap/CartoDB."
    },
    {
        "name": "Мониторинг пожаров (Monitoring)",
        "description": "Прием пространственно-временных запросов (BBox или полигон) и опрос статуса конвейера ДЗЗ."
    },
    {
        "name": "Аналитическая отчётность (Reports)",
        "description": "Формирование сводной справки: суммарная площадь в га, распределение по 3 степеням и число термоточек."
    },
    {
        "name": "Картографический экспорт (Export)",
        "description": "Выгрузка полигональных контуров гарей в GeoJSON и ESRI Shapefile ZIP, выгрузка термоточек."
    },
    {
        "name": "Диагностика системы (Health)",
        "description": "Проверка доступности весов ML-моделей и дискового хранилища."
    },
]

DESCRIPTION = r"""
### 🛰️ Геоинформационный комплекс двухэтапного космического мониторинга природных пожаров (КосмоХакатон 2026)

Комплекс решает задачу оперативного обнаружения очагов горения и оценки площадей пройденных огнём территорий по спутниковым данным:

---

#### 1. Модуль Active Fire (VIIRS I1–I5, 375 м/пикс)
* **Детекция открытого пламени:** Физико-контекстный алгоритм радиационного контраста $\Delta T = I_4 - I_5$ со скользящим окном $21 \times 21$.
* **Фильтрация помех:** Отсечение солнечных зайчиков по каналу $I_3$ и углам Солнца.

#### 2. Модуль Burn Severity (Sentinel-2 L2A + Sentinel-1 SAR, 20 м/пикс)
* **Выделение контуров гарей:** Разностные нормализованные спектральные индексы ($dNBR, RdNBR, dNDVI$).
* **Защита от ложной пашни:** Спектральная динамика красного канала ($dRed$) — гарь темнеет ($dRed < 0$), убранная стерня светлеет ($dRed > 0$).
* **Радиолокационная верификация:** Sentinel-1 C-SAR ($\Delta VH, \Delta VV$) сквозь плотный задымлённый полог.
* **Классификация степени поражения:** 3 категории (1 — слабая, 2 — средняя, 3 — сильная).

#### 3. Геодезический модуль и экспорт
* Точный расчёт площадей в проекциях **UTM 37N / 38N** ($S_{\text{pixel}} = 0.04\text{ га}$).
* Экспорт в форматы **GeoJSON (RFC 7946)** и **ESRI Shapefile ZIP** (с кодовой страницей UTF-8).
* Интерактивная веб-карта на подложке CartoDB / OSM по адресу `/` или `/map`.

---
"""

app = FastAPI(
    title="Fire-Operator API — Мониторинг природных пожаров по данным ДЗЗ",
    summary="REST API аналитической геосистемы мониторинга и оценки ущерба от пожаров",
    version=settings.VERSION,
    description=DESCRIPTION,
    openapi_tags=tags_metadata,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    swagger_ui_parameters={
        "defaultModelsExpandDepth": 2,
        "docExpansion": "list",
        "displayRequestDuration": True,
        "filter": True,
        "syntaxHighlight.theme": "monokai"
    },
    contact={
        "name": "Команда разработки Fire-Operator (КосмоХакатон 2026)",
        "url": "https://космохакатон.рф",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    }
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.staticfiles import StaticFiles

app.include_router(api_router, prefix=settings.API_V1_STR)

frontend_dist = os.path.abspath(os.path.join(settings.PROJECT_ROOT, "frontend", "dist"))
assets_dir = os.path.join(frontend_dist, "assets")
if os.path.exists(assets_dir):
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

map_html_path = os.path.join(settings.TEMPLATES_DIR, "map.html")


@app.get(
    "/",
    response_class=HTMLResponse,
    tags=["Картографический веб-интерфейс (GIS UI)"],
    summary="Интерактивная карта мониторинга пожаров (Web GIS)"
)
def root_map():
    """Открывает полноэкранный картографический интерфейс с визуализацией термоточек и контуров гарей."""
    if os.path.exists(map_html_path):
        with open(map_html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    index_html = os.path.join(frontend_dist, "index.html")
    if os.path.exists(index_html):
        with open(index_html, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Fire-Operator GIS Service</h1><p><a href='/docs'>Swagger API</a></p>")


@app.get(
    "/map",
    response_class=HTMLResponse,
    tags=["Картографический веб-интерфейс (GIS UI)"],
    summary="Интерактивная карта мониторинга пожаров (Web GIS)"
)
def get_map():
    """Прямая ссылка на картографический интерфейс."""
    return root_map()


@app.get(
    "/react",
    response_class=HTMLResponse,
    tags=["Картографический веб-интерфейс (GIS UI)"],
    summary="Экспериментальный React Deck.GL интерфейс"
)
def get_react_app():
    """Прямая ссылка на React/Deck.GL интерфейс."""
    index_html = os.path.join(frontend_dist, "index.html")
    if os.path.exists(index_html):
        with open(index_html, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>React frontend build not found</h1>", status_code=404)


@app.get("/favicon.svg", include_in_schema=False)
def get_favicon():
    fav = os.path.join(frontend_dist, "favicon.svg")
    if os.path.exists(fav):
        return FileResponse(fav, media_type="image/svg+xml")
    return HTMLResponse(status_code=404)
