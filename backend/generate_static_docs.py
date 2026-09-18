"""
Скрипт генерации статической документации OpenAPI / Swagger:
1. Сохраняет актуальный backend/docs/openapi.json
2. Генерирует автономный файл backend/docs/swagger.html (открывается в любом браузере)
3. Генерирует автономный файл backend/docs/redoc.html
"""
import os
import sys
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.main import app

docs_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "docs"))
os.makedirs(docs_dir, exist_ok=True)

# 1. Получаем полную спецификацию OpenAPI
openapi_schema = app.openapi()
openapi_path = os.path.join(docs_dir, "openapi.json")

with open(openapi_path, "w", encoding="utf-8") as f:
    json.dump(openapi_schema, f, ensure_ascii=False, indent=2)

print(f"[OK] Сгенерирован файл OpenAPI схемы: {openapi_path}")

# 2. Генерируем автономную страницу Swagger UI
swagger_html_content = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <title>Fire-Operator API — Swagger UI</title>
  <link rel="stylesheet" type="text/css" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css" />
  <link rel="icon" type="image/png" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/favicon-32x32.png" sizes="32x32" />
  <style>
    body {{
      margin: 0;
      padding: 0;
      background: #fafafa;
    }}
    .topbar {{
      display: none;
    }}
    .custom-header {{
      background: #111827;
      color: #fff;
      padding: 16px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }}
    .custom-header h1 {{
      margin: 0;
      font-size: 20px;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .custom-header .badge {{
      background: #ef4444;
      color: white;
      font-size: 12px;
      padding: 3px 8px;
      border-radius: 9999px;
      font-weight: 500;
    }}
    .custom-header a {{
      color: #93c5fd;
      text-decoration: none;
      font-size: 14px;
    }}
  </style>
</head>
<body>
  <div class="custom-header">
    <h1>🛰️ Fire-Operator API <span class="badge">КосмоХакатон 2026</span></h1>
    <div>
      <a href="redoc.html" style="margin-right: 16px;">Открыть ReDoc</a>
      <a href="openapi.json" download>Скачать openapi.json</a>
    </div>
  </div>
  <div id="swagger-ui"></div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-standalone-preset.js"></script>
  <script>
    window.onload = function() {{
      const spec = {json.dumps(openapi_schema, ensure_ascii=False)};
      window.ui = SwaggerUIBundle({{
        spec: spec,
        dom_id: '#swagger-ui',
        deepLinking: true,
        presets: [
          SwaggerUIBundle.presets.apis,
          SwaggerUIStandalonePreset
        ],
        layout: "BaseLayout",
        docExpansion: "list",
        defaultModelsExpandDepth: 2,
        syntaxHighlight: {{
          theme: "monokai"
        }}
      }});
    }};
  </script>
</body>
</html>
"""

swagger_html_path = os.path.join(docs_dir, "swagger.html")
with open(swagger_html_path, "w", encoding="utf-8") as f:
    f.write(swagger_html_content)

print(f"[OK] Сгенерирован автономный Swagger UI: {swagger_html_path}")

# 3. Генерируем автономную страницу ReDoc
redoc_html_content = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <title>Fire-Operator API — ReDoc</title>
  <link rel="icon" type="image/png" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/favicon-32x32.png" sizes="32x32" />
  <link href="https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700" rel="stylesheet">
  <style>
    body {{
      margin: 0;
      padding: 0;
    }}
  </style>
</head>
<body>
  <div id="redoc-container"></div>
  <script src="https://cdn.jsdelivr.net/npm/redoc@2.1.5/bundles/redoc.standalone.js"></script>
  <script>
    const spec = {json.dumps(openapi_schema, ensure_ascii=False)};
    Redoc.init(spec, {{
      scrollYOffset: 50,
      hideDownloadButton: false,
      theme: {{
        colors: {{
          primary: {{
            main: '#dc2626'
          }}
        }}
      }}
    }}, document.getElementById('redoc-container'));
  </script>
</body>
</html>
"""

redoc_html_path = os.path.join(docs_dir, "redoc.html")
with open(redoc_html_path, "w", encoding="utf-8") as f:
    f.write(redoc_html_content)

print(f"[OK] Сгенерирован автономный ReDoc: {redoc_html_path}")
print("Генерация статической документации успешно завершена!")
