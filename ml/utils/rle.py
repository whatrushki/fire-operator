"""
Векторизованный RLE (Run-Length Encoding) кодек для масок сегментации.
Соответствует регламенту соревнований:
- 1-based индексация пикселей;
- Построчный обход (слева направо, сверху вниз, order='C');
- Пары "начальный_пиксель длина" через пробел в двойных кавычках;
- При отсутствии пикселей возвращается пустая строка в кавычках: '""'.
"""
import numpy as np


def rle_encode(mask: np.ndarray) -> str:
    """
    Кодирует 2D бинарную маску (bool или uint8) в RLE строку.
    
    Args:
        mask: 2D numpy array (0 или 1).
        
    Returns:
        Строка вида '"start_1 len_1 start_2 len_2"' или '""'.
    """
    if mask is None or not np.any(mask):
        return '""'
        
    pixels = mask.astype(bool).flatten(order='C')
    if not np.any(pixels):
        return '""'
        
    # Обрамляем нулями для надёжного нахождения фронтов (0->1 и 1->0)
    # Используем int8, чтобы diff давал корректный -1 при переходе 1 -> 0
    padded = np.pad(pixels.astype(np.int8), 1, mode='constant')
    diff = np.diff(padded)
    # Начала серий (фронт 0 -> 1): 1-based индекс совпадает с индексом в pixels
    starts = np.where(diff == 1)[0] + 1
    # Концы серий (фронт 1 -> 0)
    ends = np.where(diff == -1)[0] + 1
    lengths = ends - starts
    
    # Формируем чередующийся массив [start1, len1, start2, len2, ...]
    runs = np.empty(starts.size * 2, dtype=np.int64)
    runs[0::2] = starts
    runs[1::2] = lengths
    
    return f'"{ " ".join(map(str, runs)) }"'


def rle_decode(rle_str: str, shape: tuple[int, int]) -> np.ndarray:
    """
    Декодирует RLE строку обратно в 2D бинарную маску (uint8).
    
    Args:
        rle_str: Строка вида '"1 5 10 3"' или '""'.
        shape: (height, width) целевого растра.
        
    Returns:
        2D numpy array uint8 с 0 и 1.
    """
    mask = np.zeros(shape[0] * shape[1], dtype=np.uint8)
    if rle_str is None or not isinstance(rle_str, str):
        return mask.reshape(shape)
        
    clean_str = rle_str.strip().strip('"').strip("'")
    if not clean_str or clean_str.lower() in ('""', "''", 'nan', 'none'):
        return mask.reshape(shape)
        
    items = list(map(int, clean_str.split()))
    if len(items) % 2 != 0:
        raise ValueError(f"Нечётное число элементов в RLE: {len(items)}")
        
    starts = np.array(items[0::2], dtype=np.int64) - 1  # перевод в 0-based
    lengths = np.array(items[1::2], dtype=np.int64)
    ends = starts + lengths
    
    for s, e in zip(starts, ends):
        mask[s:e] = 1
        
    return mask.reshape(shape)
