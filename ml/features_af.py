"""
Экстракция физико-статистических признаков для задачи AF (Active Fire).
Каналы VIIRS:
  1: I1 (Red, 640 nm)
  2: I2 (NIR, 865 nm)
  3: I3 (SWIR, 1610 nm)
  4: I4 (MIR, 3740 nm, Brightness Temp, K)
  5: I5 (TIR, 11450 nm, Brightness Temp, K)
  6: solar_zenith (deg)
  7: sensor_zenith (deg)
  8: valid (1.0 = valid)
Каналы AUX:
  1: landcover (ESA WorldCover)
  2: dem (Copernicus DEM, m)
  3: t2m (ERA5-Land 2m temp, K)
  4: rh2m (ERA5-Land 2m relative humidity, %)
  5: wind_speed (ERA5-Land 10m wind speed, m/s)
"""
import numpy as np
from scipy.ndimage import uniform_filter


def extract_af_features(viirs_data: np.ndarray, aux_data: np.ndarray) -> np.ndarray:
    """
    Извлекает матрицу признаков размерности (H*W, N_features) для чипа AF.
    
    Args:
        viirs_data: array (8, 256, 256) float32
        aux_data: array (5, 256, 256) float32
        
    Returns:
        X: array (256*256, N_features) float32
    """
    # 1. Извлечение базовых каналов
    i1 = viirs_data[0]
    i2 = viirs_data[1]
    i3 = viirs_data[2]
    i4 = viirs_data[3]
    i5 = viirs_data[4]
    solar_zenith = viirs_data[5]
    sensor_zenith = viirs_data[6]
    valid = viirs_data[7]
    
    landcover = aux_data[0]
    dem = aux_data[1]
    t2m = aux_data[2]
    rh2m = aux_data[3]
    wind_speed = aux_data[4]
    
    # Обработка NaN в тепловых каналах (замена на медиану/минимум)
    i4_clean = np.nan_to_num(i4, nan=280.0)
    i5_clean = np.nan_to_num(i5, nan=275.0)
    
    # 2. Радиационный контраст (ключевой физический признак)
    delta_t = i4_clean - i5_clean
    delta_t_air = i4_clean - np.nan_to_num(t2m, nan=290.0)
    
    # 3. Контекстные статистики фона (окно 21x21) с исключением потенциально горящих пикселей
    # Горящий пиксель НЕ должен искажать среднее и дисперсию фона вокруг себя
    bg_mask = (i4_clean < 318.0) & (delta_t < 9.0) & (valid > 0.5)
    bg_weight = bg_mask.astype(np.float32)
    weight_sum = uniform_filter(bg_weight, size=21, mode='reflect') + 1e-4
    
    mean_i4 = uniform_filter(i4_clean * bg_weight, size=21, mode='reflect') / weight_sum
    mean_i4_sq = uniform_filter((i4_clean**2) * bg_weight, size=21, mode='reflect') / weight_sum
    std_i4 = np.sqrt(np.maximum(mean_i4_sq - mean_i4**2, 1.0))
    z_i4 = (i4_clean - mean_i4) / (std_i4 + 1.0)
    
    mean_dt = uniform_filter(delta_t * bg_weight, size=21, mode='reflect') / weight_sum
    mean_dt_sq = uniform_filter((delta_t**2) * bg_weight, size=21, mode='reflect') / weight_sum
    std_dt = np.sqrt(np.maximum(mean_dt_sq - mean_dt**2, 1.0))
    z_dt = (delta_t - mean_dt) / (std_dt + 1.0)
    
    # 4. Локальный контраст малых окон 5x5 и 9x9
    mean_i4_small = uniform_filter(i4_clean, size=5, mode='reflect')
    diff_small = i4_clean - mean_i4_small
    mean_i4_mid = uniform_filter(i4_clean, size=9, mode='reflect')
    diff_mid = i4_clean - mean_i4_mid
    
    # 5. Дневной / ночной режим и фильтр бликов
    is_day = (solar_zenith < 85.0).astype(np.float32)
    
    # В ночных сценах i1, i2, i3 содержат NaN - заменяем на 0
    i1_safe = np.nan_to_num(i1, nan=0.0)
    i2_safe = np.nan_to_num(i2, nan=0.0)
    i3_safe = np.nan_to_num(i3, nan=0.0)
    
    # Солнечный блик (высокий i3 днем)
    glint_proxy = i3_safe * np.maximum(0.0, np.cos(np.radians(solar_zenith))) * is_day
    
    # NDVI в видимом диапазоне (днем)
    ndvi = np.where(is_day > 0.5, (i2_safe - i1_safe) / (i2_safe + i1_safe + 1e-4), 0.0)
    
    # Соотношение MIR / TIR
    mir_tir_ratio = (i4_clean - 250.0) / (i5_clean - 250.0 + 1e-3)
    
    # 6. Тип покрова (индикаторы)
    is_forest = (landcover == 10).astype(np.float32)
    is_grass = (landcover == 30).astype(np.float32)
    is_crop = (landcover == 40).astype(np.float32)
    is_urban = (landcover == 50).astype(np.float32)
    is_water = (landcover == 80).astype(np.float32)
    is_wetland = (landcover == 90).astype(np.float32)
    
    # 7. Сборка признакового пространства
    features = [
        i4_clean.ravel(),
        i5_clean.ravel(),
        delta_t.ravel(),
        delta_t_air.ravel(),
        z_i4.ravel(),
        z_dt.ravel(),
        diff_small.ravel(),
        diff_mid.ravel(),
        mir_tir_ratio.ravel(),
        glint_proxy.ravel(),
        ndvi.ravel(),
        is_day.ravel(),
        solar_zenith.ravel(),
        sensor_zenith.ravel(),
        valid.ravel(),
        is_forest.ravel(),
        is_grass.ravel(),
        is_crop.ravel(),
        is_urban.ravel(),
        is_water.ravel(),
        is_wetland.ravel(),
        dem.ravel(),
        rh2m.ravel(),
        wind_speed.ravel()
    ]
    
    X = np.column_stack(features).astype(np.float32)
    return np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
