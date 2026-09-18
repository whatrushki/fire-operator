"""
Кроссплатформенный запуск сервиса Fire-Operator с автоматическим открытием Swagger UI в браузере.
"""
import sys
import os
import webbrowser
import threading
import time
import uvicorn

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "backend")))

def open_browser():
    time.sleep(1.2)
    print("\nОткрываем интерактивную документацию Swagger UI в браузере...")
    webbrowser.open("http://localhost:8000/docs")

if __name__ == "__main__":
    print("=" * 60)
    print("  Запуск геоинформационного сервиса Fire-Operator")
    print("  Swagger UI: http://localhost:8000/docs")
    print("  ReDoc:      http://localhost:8000/redoc")
    print("=" * 60)
    
    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
