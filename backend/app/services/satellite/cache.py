"""
Файловый кэш для спутниковых данных и сцен (SceneCache).
Предотвращает повторные скачивания снимков Sentinel и запросов к FIRMS,
обеспечивая TTL-валидацию и контроль дискового пространства.
"""

import os
import json
import time
import hashlib
import threading
import logging
from pathlib import Path
from typing import Any, Optional, Dict

logger = logging.getLogger(__name__)


class SceneCache:
    """
    Потокобезопасный дисковый кэш спутниковых запросов и сцен.
    Поддерживает сохранение JSON-метаданных, растровых файлов и бинарных данных.
    """

    def __init__(
        self,
        cache_dir: str,
        ttl_hours: int = 24,
        max_size_gb: float = 2.0
    ):
        self.cache_dir = Path(cache_dir)
        self.ttl_seconds = int(ttl_hours * 3600)
        self.max_size_bytes = int(max_size_gb * 1024 * 1024 * 1024)
        self._lock = threading.Lock()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def generate_key(prefix: str, *args, **kwargs) -> str:
        """Формирует детерминированный ключ кэша на основе параметров."""
        content = f"{prefix}:" + ":".join(str(a) for a in args)
        if kwargs:
            content += ":" + ":".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:24]

    def _get_entry_dir(self, key: str) -> Path:
        return self.cache_dir / key

    def get_json(self, key: str) -> Optional[Any]:
        """Получить кэшированный JSON-объект, если срок жизни не истек."""
        with self._lock:
            entry_dir = self._get_entry_dir(key)
            meta_path = entry_dir / "meta.json"
            data_path = entry_dir / "data.json"

            if not meta_path.exists() or not data_path.exists():
                return None

            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)

                if time.time() - meta.get("timestamp", 0) > self.ttl_seconds:
                    return None

                with open(data_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Ошибка чтения кэша %s: %s", key, e)
                return None

    def put_json(self, key: str, data: Any, extra_meta: Optional[Dict[str, Any]] = None) -> bool:
        """Сохранить JSON-объект в кэш."""
        with self._lock:
            try:
                entry_dir = self._get_entry_dir(key)
                entry_dir.mkdir(parents=True, exist_ok=True)

                meta = {
                    "key": key,
                    "timestamp": time.time(),
                    "extra": extra_meta or {},
                }
                with open(entry_dir / "meta.json", "w", encoding="utf-8") as f:
                    json.dump(meta, f, ensure_ascii=False, indent=2)

                with open(entry_dir / "data.json", "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)

                self._enforce_size_limit()
                return True
            except Exception as e:
                logger.error("Ошибка записи JSON в кэш %s: %s", key, e)
                return False

    def get_file_path(self, key: str, filename: str) -> Optional[Path]:
        """Возвращает путь к кэшированному файлу, если запись актуальна."""
        with self._lock:
            entry_dir = self._get_entry_dir(key)
            meta_path = entry_dir / "meta.json"
            file_path = entry_dir / filename

            if not meta_path.exists() or not file_path.exists():
                return None

            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)

                if time.time() - meta.get("timestamp", 0) > self.ttl_seconds:
                    return None

                return file_path
            except Exception:
                return None

    def put_file(
        self,
        key: str,
        filename: str,
        data_bytes: bytes,
        extra_meta: Optional[Dict[str, Any]] = None
    ) -> Optional[Path]:
        """Сохраняет бинарный файл в запись кэша."""
        with self._lock:
            try:
                entry_dir = self._get_entry_dir(key)
                entry_dir.mkdir(parents=True, exist_ok=True)

                target_file = entry_dir / filename
                with open(target_file, "wb") as f:
                    f.write(data_bytes)

                meta = {
                    "key": key,
                    "filename": filename,
                    "size_bytes": len(data_bytes),
                    "timestamp": time.time(),
                    "extra": extra_meta or {},
                }
                with open(entry_dir / "meta.json", "w", encoding="utf-8") as f:
                    json.dump(meta, f, ensure_ascii=False, indent=2)

                self._enforce_size_limit()
                return target_file
            except Exception as e:
                logger.error("Ошибка сохранения файла %s в кэш %s: %s", filename, key, e)
                return None

    def _enforce_size_limit(self):
        """Проверяет суммарный объем кэша и удаляет самые старые записи (LRU) при превышении."""
        try:
            entries = []
            total_size = 0

            for entry in self.cache_dir.iterdir():
                if entry.is_dir():
                    meta_file = entry / "meta.json"
                    entry_size = sum(f.stat().st_size for f in entry.glob("**/*") if f.is_file())
                    total_size += entry_size
                    mtime = meta_file.stat().st_mtime if meta_file.exists() else entry.stat().st_mtime
                    entries.append((mtime, entry_size, entry))

            if total_size <= self.max_size_bytes:
                return

            # Сортируем от самых старых к новым
            entries.sort(key=lambda x: x[0])

            for _, size, entry_path in entries:
                if total_size <= self.max_size_bytes:
                    break
                try:
                    for f in entry_path.iterdir():
                        f.unlink()
                    entry_path.rmdir()
                    total_size -= size
                    logger.info("Удалена устаревшая запись кэша: %s", entry_path.name)
                except Exception as del_err:
                    logger.warning("Не удалось удалить запись кэша %s: %s", entry_path, del_err)
        except Exception as e:
            logger.warning("Ошибка очистки лимита кэша: %s", e)

    def clear(self):
        """Полная очистка кэша."""
        with self._lock:
            for item in self.cache_dir.iterdir():
                try:
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        for f in item.iterdir():
                            f.unlink()
                        item.rmdir()
                except Exception as e:
                    logger.warning("Ошибка удаления %s: %s", item, e)
