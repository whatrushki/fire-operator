import { useState, useEffect, useMemo, useCallback } from 'react';
import {
  fireApi,
  type GeoJSONFeatureCollection,
  type BurnContourFeature,
  type ThermalPointFeature,
  type BackendAnalyticalReport,
} from './api/fireApi';
import { Header } from './components/common/Header';
import { CosmoMap25D } from './components/map/CosmoMap25D';
import {
  LeftAnalyticsDock,
  BACKEND_PRESETS,
  type ZonePreset,
} from './components/common/LeftAnalyticsDock';
import { RightContoursDock } from './components/common/RightContoursDock';
import { SideSheet } from './components/common/SideSheet';
import { ExecutiveReportModal } from './components/common/ExecutiveReportModal';
import { FireTimelineGraph, type FirePhase } from './components/common/FireTimelineGraph';

// Geodesic Shoelace calculation for user drawn polygon preview
function calculatePolygonArea(coords: [number, number][]): number {
  if (coords.length < 3) return 0;
  const R = 6378137;
  const lat0 = (coords[0][1] * Math.PI) / 180;
  const cosLat0 = Math.cos(lat0);

  const pts = coords.map(([lng, lat]) => [
    (lng - coords[0][0]) * (Math.PI / 180) * R * cosLat0,
    (lat - coords[0][1]) * (Math.PI / 180) * R,
  ]);

  let area = 0;
  for (let i = 0; i < pts.length; i++) {
    const j = (i + 1) % pts.length;
    area += pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1];
  }

  const sqMeters = Math.abs(area) / 2;
  return +(sqMeters / 10000).toFixed(1);
}

export function App() {
  // Primary default: Rostov region (Lower Don)
  const [selectedZone, setSelectedZone] = useState<ZonePreset | null>(BACKEND_PRESETS[0]);
  const [dateFrom, setDateFrom] = useState<string>(BACKEND_PRESETS[0].dateFrom);
  const [dateTo, setDateTo] = useState<string>(BACKEND_PRESETS[0].dateTo);
  const [includeRadar, setIncludeRadar] = useState<boolean>(true);

  const [activeTaskId, setActiveTaskId] = useState<string>('');
  const [currentReport, setCurrentReport] = useState<BackendAnalyticalReport | null>(null);
  const [burnGeoJson, setBurnGeoJson] = useState<GeoJSONFeatureCollection<BurnContourFeature> | null>(null);
  const [thermalGeoJson, setThermalGeoJson] = useState<GeoJSONFeatureCollection<ThermalPointFeature> | null>(null);
  const [selectedFeature, setSelectedFeature] = useState<any | null>(null);

  // Free drawing polygon state
  const [isDrawing, setIsDrawing] = useState(false);
  const [drawnPoints, setDrawnPoints] = useState<[number, number][]>([]);

  // Split comparison view
  const [isSplitView, setIsSplitView] = useState(false);
  const [currentPhase, setCurrentPhase] = useState<FirePhase>('burn');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisProgress, setAnalysisProgress] = useState(0);
  const [isBackendHealthy, setIsBackendHealthy] = useState(true);

  // Modals & Panels
  const [isSideSheetOpen, setIsSideSheetOpen] = useState(false);
  const [isExecutiveReportOpen, setIsExecutiveReportOpen] = useState(false);

  // Calculated area of drawn polygon in hectares
  const calculatedAreaHa = useMemo(() => {
    return calculatePolygonArea(drawnPoints);
  }, [drawnPoints]);

  // Drawing Handlers
  const handleAddPoint = useCallback((pt: [number, number]) => {
    setDrawnPoints((prev) => [...prev, pt]);
  }, []);

  const handleFinishDrawing = useCallback(() => {
    setIsDrawing(false);
  }, []);

  const handleClearDrawing = useCallback(() => {
    setDrawnPoints([]);
    setIsDrawing(false);
  }, []);

  // Run Analysis through real backend REST API
  const handleRunAnalysis = async (zoneOverride?: ZonePreset) => {
    const targetZone = zoneOverride !== undefined ? zoneOverride : selectedZone;
    setIsAnalyzing(true);
    setAnalysisProgress(10);
    setIsDrawing(false);

    try {
      let requestBbox = targetZone?.bbox || null;
      let requestPolygon = undefined;
      let requestRegion = targetZone?.id && targetZone.id !== 'custom' ? targetZone.id : null;

      const isCustomDrawn = drawnPoints.length >= 3 && !zoneOverride;

      if (isCustomDrawn) {
        const lngs = drawnPoints.map((p) => p[0]);
        const lats = drawnPoints.map((p) => p[1]);
        requestBbox = [
          Math.min(...lngs),
          Math.min(...lats),
          Math.max(...lngs),
          Math.max(...lats),
        ];
        const closedPoints =
          drawnPoints[0][0] === drawnPoints[drawnPoints.length - 1][0] &&
          drawnPoints[0][1] === drawnPoints[drawnPoints.length - 1][1]
            ? drawnPoints
            : [...drawnPoints, drawnPoints[0]];

        requestPolygon = {
          type: 'Polygon',
          coordinates: [closedPoints],
        };
        requestRegion = null;
      }

      // 1. POST /api/v1/analyze
      const initResp = await fireApi.startAnalysis({
        bbox: requestBbox,
        polygon: requestPolygon,
        region: requestRegion,
        date_from: dateFrom,
        date_to: dateTo,
        include_radar: includeRadar,
      });

      setActiveTaskId(initResp.task_id);

      // 2. Poll until task status is completed
      await fireApi.pollTask(initResp.task_id, 90, 1000, (prog) => {
        setAnalysisProgress(prog);
      });

      // 3. Fetch real satellite data layers from backend
      const [reportData, burnData, thermalData] = await Promise.all([
        fireApi.getReport(initResp.task_id),
        fireApi.getBurnGeoJSON(initResp.task_id),
        fireApi.getThermalPoints(initResp.task_id),
      ]);

      setCurrentReport(reportData);
      setBurnGeoJson(burnData);
      setThermalGeoJson(thermalData);
      setIsBackendHealthy(true);
    } catch (err: any) {
      console.error('Run analysis error:', err);
      setIsBackendHealthy(false);
    } finally {
      setIsAnalyzing(false);
      setAnalysisProgress(100);
    }
  };

  // Preset Zone Selection
  const handleSelectZone = (zone: ZonePreset) => {
    setSelectedZone(zone);
    setDateFrom(zone.dateFrom);
    setDateTo(zone.dateTo);
    handleClearDrawing();
    handleRunAnalysis(zone);
  };

  // Initial load: check health and run initial Rostov analysis
  useEffect(() => {
    fireApi.getHealth().then(() => setIsBackendHealthy(true)).catch(() => setIsBackendHealthy(false));
    handleRunAnalysis(BACKEND_PRESETS[0]);
  }, []);

  // Export GeoJSON (Burn contours)
  const handleExportGeoJSON = () => {
    if (burnGeoJson && activeTaskId) {
      const blob = new Blob([JSON.stringify(burnGeoJson, null, 2)], {
        type: 'application/geo+json;charset=utf-8',
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `burn_contours_${activeTaskId}.geojson`;
      a.click();
      URL.revokeObjectURL(url);
    } else if (activeTaskId) {
      window.open(fireApi.getGeoJSONDownloadUrl(activeTaskId), '_blank');
    }
  };

  // Export Shapefile ZIP
  const handleExportShapefile = () => {
    if (activeTaskId) {
      window.open(fireApi.getShapefileDownloadUrl(activeTaskId), '_blank');
    }
  };

  // Export JSON Report
  const handleExportJsonReport = () => {
    if (currentReport) {
      const blob = new Blob([JSON.stringify(currentReport, null, 2)], {
        type: 'application/json;charset=utf-8',
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `analytical_report_${currentReport.task_id}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } else if (activeTaskId) {
      window.open(fireApi.getReportDownloadUrl(activeTaskId), '_blank');
    }
  };

  // Export CSV Report (Criterion 4)
  const handleExportCsvReport = () => {
    if (!currentReport) return;
    const b1 = currentReport.breakdown?.find((b) => b.class_id === 1) || { area_ha: 0, percentage: 0 };
    const b2 = currentReport.breakdown?.find((b) => b.class_id === 2) || { area_ha: 0, percentage: 0 };
    const b3 = currentReport.breakdown?.find((b) => b.class_id === 3) || { area_ha: 0, percentage: 0 };

    const csvRows = [
      ['Параметр', 'Значение'],
      ['ID Задачи', currentReport.task_id],
      ['Регион / Территория', currentReport.region || selectedZone?.name || 'Пользовательская область'],
      ['Временной интервал', currentReport.period],
      ['Суммарная площадь гари (га)', currentReport.total_burned_area_ha.toString()],
      ['Класс 1 — Слабая степень (га)', b1.area_ha.toString()],
      ['Класс 1 — Доля (%)', b1.percentage.toString()],
      ['Класс 2 — Средняя степень (га)', b2.area_ha.toString()],
      ['Класс 2 — Доля (%)', b2.percentage.toString()],
      ['Класс 3 — Сильная степень (га)', b3.area_ha.toString()],
      ['Класс 3 — Доля (%)', b3.percentage.toString()],
      ['Подтверждённые очаги горения (VIIRS AF)', currentReport.active_thermal_anomalies_count.toString()],
      ['Картографическая проекция', currentReport.utm_zone],
      ['Пространственное разрешение', `${currentReport.spatial_resolution_m} м/пикс (0.04 га)`],
      ['Методика расчёта площадей', currentReport.calculation_method],
      ['Модель детекции AF (375м)', currentReport.model_af || 'VIIRS Physics + SaturationGuard'],
      ['Модель классификации BS (20м)', currentReport.model_bs || 'Sentinel-2/1 Multi-spectral Context MLP'],
    ];

    const csvContent =
      '\uFEFF' +
      csvRows
        .map((row) => row.map((cell) => `"${cell.replace(/"/g, '""')}"`).join(';'))
        .join('\r\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `Analytical_Report_${currentReport.task_id}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const currentZoneTitle =
    drawnPoints.length >= 3
      ? `Пользовательский полигон (${calculatedAreaHa.toFixed(1)} га)`
      : selectedZone?.name || 'Территория интереса';

  return (
    <div className="relative w-screen h-screen overflow-hidden bg-[#07080A] text-white font-sans antialiased">
      {/* 1. SATELLITE MAP WITH REAL DATA LAYERS & SPLIT VIEW */}
      <CosmoMap25D
        burnGeoJson={burnGeoJson}
        thermalGeoJson={thermalGeoJson}
        selectedZone={selectedZone}
        isSplitView={isSplitView}
        selectedFeature={selectedFeature}
        onSelectFeature={(feature) => {
          setSelectedFeature(feature);
          setIsSideSheetOpen(true);
        }}
        isDrawing={isDrawing}
        drawnPoints={drawnPoints}
        onAddPoint={handleAddPoint}
        onFinishDrawing={handleFinishDrawing}
        onClearDrawing={handleClearDrawing}
        calculatedAreaHa={calculatedAreaHa}
        onRunAnalysis={() => handleRunAnalysis()}
        dateBefore={dateFrom}
        dateAfter={dateTo}
        currentPhase={currentPhase}
      />

      {/* 2. TOP GLASS HEADER */}
      <Header
        isSplitView={isSplitView}
        onToggleSplitView={() => setIsSplitView((prev) => !prev)}
        selectedEntityTitle={currentZoneTitle}
        subTitle={currentReport?.utm_zone || selectedZone?.region}
        isBackendHealthy={isBackendHealthy}
      />

      {/* 3. LEFT ANALYTICS CONTROLS & EXPORTS DOCK */}
      <LeftAnalyticsDock
        report={currentReport}
        selectedZone={selectedZone}
        onSelectZone={handleSelectZone}
        dateFrom={dateFrom}
        setDateFrom={setDateFrom}
        dateTo={dateTo}
        setDateTo={setDateTo}
        includeRadar={includeRadar}
        setIncludeRadar={setIncludeRadar}
        isDrawing={isDrawing}
        onToggleDrawing={() => setIsDrawing((prev) => !prev)}
        drawnPointsCount={drawnPoints.length}
        calculatedAreaHa={calculatedAreaHa}
        onFinishDrawing={handleFinishDrawing}
        onClearDrawing={handleClearDrawing}
        onRunAnalysis={() => handleRunAnalysis()}
        isAnalyzing={isAnalyzing}
        analysisProgress={analysisProgress}
        onGeneratePdf={() => setIsExecutiveReportOpen(true)}
        onExportGeoJSON={handleExportGeoJSON}
        onExportShapefile={handleExportShapefile}
        onExportJsonReport={handleExportJsonReport}
        onExportCsvReport={handleExportCsvReport}
      />

      {/* 4. RIGHT CONTOURS & THERMAL POINTS DOCK */}
      <RightContoursDock
        burnGeoJson={burnGeoJson}
        thermalGeoJson={thermalGeoJson}
        selectedFeature={selectedFeature}
        onSelectFeature={(feature) => {
          setSelectedFeature(feature);
          setIsSideSheetOpen(true);
        }}
      />

      {/* 5. SIDE SHEET INSPECTION DRAWER */}
      <SideSheet
        isOpen={isSideSheetOpen}
        onClose={() => setIsSideSheetOpen(false)}
        feature={selectedFeature}
        zoneName={currentZoneTitle}
      />

      {/* 6. EXECUTIVE PDF REPORT MODAL */}
      <ExecutiveReportModal
        isOpen={isExecutiveReportOpen}
        onClose={() => setIsExecutiveReportOpen(false)}
        report={currentReport}
        zoneName={currentZoneTitle}
        calculatedAreaHa={calculatedAreaHa}
      />

      {/* 7. FIRE EVOLUTION DYNAMICS TIMELINE GRAPH (ДО -> ПИК -> ГАРЬ -> ВОССТАНОВЛЕНИЕ) */}
      <FireTimelineGraph
        currentPhase={currentPhase}
        onPhaseChange={setCurrentPhase}
        dateBefore={dateFrom}
        dateAfter={dateTo}
        totalAreaHa={currentReport?.total_burned_area_ha ?? calculatedAreaHa}
        hotspotsCount={currentReport?.active_thermal_anomalies_count ?? (thermalGeoJson?.features?.length ?? 0)}
        isSplitView={isSplitView}
        onToggleSplitView={() => setIsSplitView((prev) => !prev)}
        report={currentReport}
      />
    </div>
  );
}

export default App;
