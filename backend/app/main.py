"""
Главная точка входа FastAPI приложения Fire-Operator.
Спроектирована для соответствия критериям раздела 4 («Информационно-аналитический сервис»).
Включает расширенную Swagger UI и ReDoc документацию.
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.core.config import settings
from app.api.v1.router import api_router

# Метаданные тегов для группировки в Swagger UI
tags_metadata = [
    {
        "name": "Мониторинг пожаров (Monitoring)",
        "description": (
            "**Оперативный и ретроспективный мониторинг.** "
            "Прием пространственно-временных запросов (BBox или полигон GeoJSON), "
            "асинхронная постановка в очередь и опрос статуса выполнения конвейера ДЗЗ."
        ),
    },
    {
        "name": "Аналитическая отчётность (Reports)",
        "description": (
            "**Официальная статистика и расчет ущерба.** "
            "Формирование сводной справки: суммарная площадь гари в гектарах, "
            "распределение по 3 степеням поражения (слабая, средняя, сильная) "
            "и число зарегистрированных термоточек активного горения."
        ),
    },
    {
        "name": "Картографический экспорт (Export)",
        "description": (
            "**Интеграция с внешними ГИС (QGIS, ArcGIS, Региональные системы).** "
            "Выгрузка полигональных контуров гарей в форматах **GeoJSON (WGS84, RFC 7946)** "
            "и **ESRI Shapefile ZIP** (.shp, .shx, .dbf, .prj, .cpg) со всеми атрибутами степеней и площадей."
        ),
    },
    {
        "name": "Диагностика системы (Health)",
        "description": (
            "**Мониторинг состояния сервиса.** "
            "Проверка доступности весов ML-моделей (AF и BS) и файлового хранилища."
        ),
    },
]

DESCRIPTION = r"""
### 🛰️ Геоинформационный программный комплекс двухэтапного мониторинга природных пожаров (КосмоХакатон 2026)

Комплекс решает задачу оперативного обнаружения очагов горения и объективной оценки площадей пройденных огнём территорий по спутниковым данным:

---

#### 1. Модуль Active Fire (VIIRS, 375 м/пикс)
* **Детекция открытого пламени:** Физико-контекстный алгоритм на основе радиационного контраста $\Delta T = I_4 - I_5$ с оценкой локального фона в скользящем окне $21 \times 21$.
* **Фильтрация помех:** Отсечение солнечных зайчиков от водных поверхностей и кровель по коротковолновому ИК-каналу ($I_3$), разделение природных пожаров и стационарных техногенных факелов на месторождениях.

#### 2. Модуль Burn Severity (Sentinel-2 L2A + Sentinel-1 SAR, 20 м/пикс)
* **Выделение контуров гарей:** Разностные нормализованные спектральные индексы ($dNBR, RdNBR, dNDVI$).
* **Защита от ложной пашни:** Анализ динамики красного спектра ($dRed$) — гарь и зола темнеют ($dRed < 0$), убранные зерновые и стерня светлеют ($dRed > 0$).
* **Радиолокационная верификация:** Sentinel-1 C-SAR ($\Delta VH, \Delta VV$) обеспечивает устойчивость к задымлению и подтверждает утрату лесного полога.
* **Классификация степени поражения:** Разделение на 3 категории (1 — слабая, 2 — средняя, 3 — сильная) с адаптивной калибровкой по типам покрова `ESA WorldCover`.

#### 3. Геодезический модуль и экспорт
* Автоматическое приведение координат к локальным проекциям **UTM 37N / 38N**.
* Точный расчёт площадей с разрешением 20 м ($S_{\\text{pixel}} = 0.04\\text{ га}$).
* Экспорт в стандарты **GeoJSON** и **ESRI Shapefile ZIP** с кодовой страницей UTF-8.

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

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)

# Монтирование директории со статической документацией
docs_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docs"))
if os.path.exists(docs_dir):
    from fastapi.staticfiles import StaticFiles
    app.mount("/static-docs", StaticFiles(directory=docs_dir, html=True), name="static-docs")


@app.get("/", tags=["Диагностика системы (Health)"], summary="Корневой эндпоинт и навигация")
def root():
    """Возвращает информацию о сервисе и быстрые ссылки на Swagger UI и ReDoc."""
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "swagger_ui": "/docs",
        "redoc": "/redoc",
        "openapi_json": f"{settings.API_V1_STR}/openapi.json",
        "api_v1": settings.API_V1_STR
    }
