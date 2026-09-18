@echo off
chcp 65001 > nul
echo ============================================================
echo   Запуск информационно-аналитического сервиса Fire-Operator
echo   КосмоХакатон 2026: Мониторинг природных пожаров по ДЗЗ
echo ============================================================
echo.
echo Swagger UI документация: http://localhost:8000/docs
echo ReDoc документация:      http://localhost:8000/redoc
echo Автономная документация: http://localhost:8000/static-docs/swagger.html
echo.

start "" "http://localhost:8000/docs"
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
