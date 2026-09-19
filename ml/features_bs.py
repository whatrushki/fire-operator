"""
Экстракция физико-спектральных и пространственно-контекстных признаков для задачи BS (Burn Severity).
Каналы Sentinel-2 (L2A, uint16, масштаб 0-10000):
  1..3: B2 (Blue), B3 (Green), B4 (Red)
  4..6: B5, B6, B7 (Red Edge)
  7: B8A (Narrow NIR, 865 nm)
  8..9: B11 (SWIR-1, 1610 nm), B12 (SWIR-2, 2190 nm)
  10: SCL (Scene Classification Layer)
Каналы Sentinel-1 (C-band SAR, int16, sigma0 x 100 dB):
  1: VV, 2: VH
Каналы AUX (int16):
  1: dem, 2: slope, 3: landcover
"""
import numpy as np
from scipy.ndimage import uniform_filter


def extract_bs_features(
    s2_pre: np.ndarray,
    s2_post: np.ndarray,
    s1_pre: np.ndarray,
    s1_post: np.ndarray,
    aux: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """
    Извлекает спектральные, радарные и пространственно-контекстные признаки для чипа BS (512x512).
    
    Returns:
        X: array (512*512, N_features) float32
        cloud_mask: array (512, 512) bool (True = валидный, False = облако/тень)
    """
    # Преобразуем Sentinel-2 в float32 (диапазон 0.0 - 1.0)
    pre_b4 = s2_pre[2].astype(np.float32) / 10000.0
    pre_b8a = s2_pre[6].astype(np.float32) / 10000.0
    pre_b12 = s2_pre[8].astype(np.float32) / 10000.0
    pre_scl = s2_pre[9]
    
    post_b2 = s2_post[0].astype(np.float32) / 10000.0
    post_b3 = s2_post[1].astype(np.float32) / 10000.0
    post_b4 = s2_post[2].astype(np.float32) / 10000.0
    post_b8a = s2_post[6].astype(np.float32) / 10000.0
    post_b11 = s2_post[7].astype(np.float32) / 10000.0
    post_b12 = s2_post[8].astype(np.float32) / 10000.0
    post_scl = s2_post[9]
    
    # 1. Спектральные индексы гари
    nbr_pre = (pre_b8a - pre_b12) / (pre_b8a + pre_b12 + 1e-5)
    nbr_post = (post_b8a - post_b12) / (post_b8a + post_b12 + 1e-5)
    dnbr = nbr_pre - nbr_post
    
    # Относительный dNBR (RdNBR)
    rdnbr = dnbr / np.sqrt(np.maximum(np.abs(nbr_pre), 1e-4))
    
    # 2. Индексы вегетации (NDVI)
    ndvi_pre = (pre_b8a - pre_b4) / (pre_b8a + pre_b4 + 1e-5)
    ndvi_post = (post_b8a - post_b4) / (post_b8a + post_b4 + 1e-5)
    dndvi = ndvi_pre - ndvi_post
    
    # 3. Дельта видимого красного и SWIR:
    # Гарь темнеет в красном (d_red < 0), а убранная пашня светлеет (d_red > 0)
    d_red = post_b4 - pre_b4
    d_swir = post_b12 - pre_b12
    
    # 4. Радар Sentinel-1: дельта кросс-поляризации VH и со-поляризации VV (дБ)
    vh_pre = s1_pre[1].astype(np.float32) / 100.0
    vh_post = s1_post[1].astype(np.float32) / 100.0
    d_vh = vh_post - vh_pre
    
    vv_pre = s1_pre[0].astype(np.float32) / 100.0
    vv_post = s1_post[0].astype(np.float32) / 100.0
    d_vv = vv_post - vv_pre
    diff_vh_vv = d_vh - d_vv
    
    # Дополнительные спектральные каналы:
    post_b5 = s2_post[3].astype(np.float32) / 10000.0  # Red Edge 1
    pre_b3 = s2_pre[1].astype(np.float32) / 10000.0    # Green
    pre_b2 = s2_pre[0].astype(np.float32) / 10000.0    # Blue
    
    # Спектральные дельты
    d_green = post_b3 - pre_b3
    d_blue = post_b2 - pre_b2
    ndre_post = (post_b8a - post_b5) / (post_b8a + post_b5 + 1e-5)
    
    # 5. Пространственно-контекстные признаки (скользящие окна 3x3 и 5x5)
    # Позволяют классификатору учитывать связность контура гари и устраняют шум одиночных пикселей
    dnbr_mean3 = uniform_filter(dnbr, size=3, mode='reflect')
    dnbr_mean5 = uniform_filter(dnbr, size=5, mode='reflect')
    dnbr_sq3 = uniform_filter(dnbr**2, size=3, mode='reflect')
    dnbr_std3 = np.sqrt(np.maximum(dnbr_sq3 - dnbr_mean3**2, 1e-5))
    
    dndvi_mean3 = uniform_filter(dndvi, size=3, mode='reflect')
    dred_mean3 = uniform_filter(d_red, size=3, mode='reflect')
    dvh_mean3 = uniform_filter(d_vh, size=3, mode='reflect')
    
    # 6. Вспомогательные данные (AUX)
    dem = aux[0].astype(np.float32)
    slope = aux[1].astype(np.float32)
    landcover = aux[2]
    
    # Категориальные признаки покрова
    is_forest = (landcover == 10).astype(np.float32)
    is_grass = (landcover == 30).astype(np.float32)
    is_crop = (landcover == 40).astype(np.float32)
    is_water = (landcover == 80).astype(np.float32)
    is_wetland = (landcover == 90).astype(np.float32)
    
    # 7. Маска облачности и теней по SCL: 3=тень, 8,9,10=облака
    # Защита светлых почв: облако маркируется, только если синий канал post_b2 > 0.15
    cloud_pre = np.isin(pre_scl, [3, 8, 9, 10])
    cloud_post = np.isin(post_scl, [3, 8, 9, 10]) & (post_b2 > 0.15)
    cloud_mask = ~(cloud_pre | cloud_post)
    
    # 8. Формирование матрицы признаков (26 признаков)
    features = [
        dnbr.ravel(),
        rdnbr.ravel(),
        dndvi.ravel(),
        d_red.ravel(),
        d_swir.ravel(),
        d_green.ravel(),
        d_blue.ravel(),
        ndre_post.ravel(),
        nbr_post.ravel(),
        post_b8a.ravel(),
        post_b12.ravel(),
        d_vh.ravel(),
        d_vv.ravel(),
        diff_vh_vv.ravel(),
        dnbr_mean3.ravel(),
        dnbr_mean5.ravel(),
        dnbr_std3.ravel(),
        dndvi_mean3.ravel(),
        dred_mean3.ravel(),
        dvh_mean3.ravel(),
        dem.ravel(),
        slope.ravel(),
        is_forest.ravel(),
        is_grass.ravel(),
        is_crop.ravel(),
        is_water.ravel()
    ]
    
    X = np.column_stack(features).astype(np.float32)
    return np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0), cloud_mask
