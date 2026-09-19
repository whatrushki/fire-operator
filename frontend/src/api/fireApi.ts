// Centralized API Client for Fire-Operator REST backend
// Local backend endpoint: http://localhost:8000

export const REMOTE_API_ORIGIN = 'http://localhost:8000';
export const API_BASE_URL = '';

export interface BackendHealth {
  status: string;
  version: string;
  models_loaded: {
    af_model: boolean;
    bs_model: boolean;
  };
  storage_accessible: boolean;
}

export interface GeoPolygon {
  type: string;
  coordinates: number[][][];
}

export interface SpatialTemporalRequest {
  polygon?: GeoPolygon | null;
  bbox?: [number, number, number, number] | null;
  date_from: string;
  date_to: string;
  include_radar?: boolean;
  region?: string | null;
}

export interface TaskInitResponse {
  task_id: string;
  status: string;
  estimated_time_sec: number;
  message: string;
}

export interface TaskStatusResponse {
  task_id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number;
  created_at: string;
  completed_at: string | null;
}

export interface BackendSeverityBreakdown {
  class_id: number;
  name: string;
  area_ha: number;
  percentage: number;
}

export interface BackendAnalyticalReport {
  task_id: string;
  region?: string;
  period: string;
  total_burned_area_ha: number;
  breakdown: BackendSeverityBreakdown[];
  active_thermal_anomalies_count: number;
  utm_zone: string;
  spatial_resolution_m: number;
  calculation_method: string;
  model_af?: string;
  model_bs?: string;
}

export interface BurnContourFeature {
  type: 'Feature';
  id?: string;
  geometry: {
    type: 'Polygon' | 'MultiPolygon';
    coordinates: any;
  };
  properties: {
    contour_id: string;
    severity_class: number;
    severity_ru?: string;
    severity_en?: string;
    area_ha: number;
    utm_zone?: string;
    dnbr_mean?: number;
  };
}

export interface ThermalPointFeature {
  type: 'Feature';
  id?: string;
  geometry: {
    type: 'Point';
    coordinates: [number, number]; // [lng, lat]
  };
  properties: {
    point_id: string;
    satellite: string;
    brightness_temp_i4_k: number;
    brightness_temp_i5_k: number;
    delta_t_k: number;
    confidence: string;
    acq_date?: string;
  };
}

export interface GeoJSONFeatureCollection<T = any> {
  type: 'FeatureCollection';
  features: T[];
}

export const fireApi = {
  // 1. Health check
  async getHealth(): Promise<BackendHealth> {
    const res = await fetch(`${API_BASE_URL}/api/v1/health`);
    if (!res.ok) {
      throw new Error(`Health check failed with status ${res.status}`);
    }
    return await res.json();
  },

  // 2. Start analysis
  async startAnalysis(params: SpatialTemporalRequest): Promise<TaskInitResponse> {
    const res = await fetch(`${API_BASE_URL}/api/v1/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(err.detail || `Analysis request failed with status ${res.status}`);
    }

    return await res.json();
  },

  // 3. Poll task status
  async getTaskStatus(taskId: string): Promise<TaskStatusResponse> {
    const res = await fetch(`${API_BASE_URL}/api/v1/tasks/${taskId}`);
    if (!res.ok) {
      throw new Error(`Failed to get task status for ${taskId}`);
    }
    return await res.json();
  },

  // 4. Poll task until completed
  async pollTask(
    taskId: string,
    maxAttempts = 40,
    delayMs = 600,
    onProgress?: (progress: number) => void
  ): Promise<TaskStatusResponse> {
    for (let i = 0; i < maxAttempts; i++) {
      const status = await this.getTaskStatus(taskId);
      if (onProgress) {
        onProgress(status.progress);
      }
      if (status.status === 'completed' || status.status === 'failed') {
        return status;
      }
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
    throw new Error('Timeout waiting for task analysis to complete');
  },

  // 5. Get analytical report
  async getReport(taskId: string): Promise<BackendAnalyticalReport> {
    const res = await fetch(`${API_BASE_URL}/api/v1/report/${taskId}`);
    if (!res.ok) {
      throw new Error(`Failed to load analytical report for ${taskId}`);
    }
    return await res.json();
  },

  // 6. Get vector GeoJSON burn contours
  async getBurnGeoJSON(taskId: string): Promise<GeoJSONFeatureCollection<BurnContourFeature>> {
    const res = await fetch(`${API_BASE_URL}/api/v1/export/geojson/${taskId}`);
    if (!res.ok) {
      throw new Error(`Failed to load burn contours GeoJSON for ${taskId}`);
    }
    return await res.json();
  },

  // Alias for getBurnGeoJSON
  async getGeoJSON(taskId: string): Promise<GeoJSONFeatureCollection<BurnContourFeature>> {
    return this.getBurnGeoJSON(taskId);
  },

  // 7. Get VIIRS thermal points GeoJSON
  async getThermalPoints(taskId: string): Promise<GeoJSONFeatureCollection<ThermalPointFeature>> {
    const res = await fetch(`${API_BASE_URL}/api/v1/export/thermal-points/${taskId}`);
    if (!res.ok) {
      throw new Error(`Failed to load thermal points GeoJSON for ${taskId}`);
    }
    return await res.json();
  },

  // 8. Download URLs
  getShapefileDownloadUrl(taskId: string): string {
    return `${REMOTE_API_ORIGIN}/api/v1/export/shapefile/${taskId}`;
  },

  getReportDownloadUrl(taskId: string): string {
    return `${REMOTE_API_ORIGIN}/api/v1/export/report/${taskId}`;
  },

  getGeoJSONDownloadUrl(taskId: string): string {
    return `${REMOTE_API_ORIGIN}/api/v1/export/geojson/${taskId}`;
  },

  getThermalPointsDownloadUrl(taskId: string): string {
    return `${REMOTE_API_ORIGIN}/api/v1/export/thermal-points/${taskId}`;
  },
};
