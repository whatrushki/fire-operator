import React from 'react';
import type { BackendAnalyticalReport } from '../../api/fireApi';
import {
  Flame,
  Play,
  FileText,
  Download,
  PenTool,
  RotateCcw,
  Sparkles,
  ChevronDown,
  Radar,
  Calendar,
  FileSpreadsheet,
  FileCode,
} from 'lucide-react';

export const getDefaultDateTo = () => new Date().toISOString().split('T')[0];
export const getDefaultDateFrom = () => {
  const d = new Date();
  d.setDate(d.getDate() - 90);
  return d.toISOString().split('T')[0];
};

export interface ZonePreset {
  id: string;
  name: string;
  region: string;
  bbox: [number, number, number, number];
  center: [number, number];
  dateFrom: string;
  dateTo: string;
  description: string;
}

export const BACKEND_PRESETS: ZonePreset[] = [
  {
    id: 'volgograd',
    name: 'Волгоградская область (Цимлянск)',
    region: 'Волгоградская обл. (UTM 38N)',
    bbox: [44.8849, 48.5370, 45.0239, 48.6292],
    center: [44.9544, 48.5831],
    dateFrom: getDefaultDateFrom(),
    dateTo: getDefaultDateTo(),
    description: 'Прибрежная полоса Цимлянского водохранилища и сухостойные степи (UTM 38N)',
  },
  {
    id: 'rostov_aksay',
    name: 'Ростов-на-Дону (Аксай / Щепкинский лес)',
    region: 'Ростов-на-Дону (UTM 37N)',
    bbox: [39.8336, 47.1510, 39.9704, 47.2442],
    center: [39.9020, 47.1976],
    dateFrom: '2024-09-01',
    dateTo: '2024-09-30',
    description: 'Пригородная лесопарковая зона и пойма Дона (Sentinel-2 BS_tr_000191, 688 га)',
  },
  {
    id: 'rostov',
    name: 'Ростовская область (Орловский/Маныч)',
    region: 'Ростовская обл. (UTM 38N)',
    bbox: [44.7547, 46.6941, 44.8891, 46.7865],
    center: [44.8219, 46.7403],
    dateFrom: getDefaultDateFrom(),
    dateTo: getDefaultDateTo(),
    description: 'Степные массивы и пастбища долины Маныча (UTM 38N, 559 контуров)',
  },
  {
    id: 'kalmykia',
    name: 'Республика Калмыкия (Яшкуль)',
    region: 'Респ. Калмыкия (UTM 38N)',
    bbox: [44.6269, 45.7722, 44.7592, 45.8647],
    center: [44.6931, 45.8184],
    dateFrom: getDefaultDateFrom(),
    dateTo: getDefaultDateTo(),
    description: 'Полупустынные ландшафты и степные гари (UTM 38N)',
  },
  {
    id: 'astrakhan',
    name: 'Астраханская область (Северный камыш)',
    region: 'Астраханская обл. (UTM 37N)',
    bbox: [40.2862, 49.0810, 40.4290, 49.1747],
    center: [40.3576, 49.1279],
    dateFrom: getDefaultDateFrom(),
    dateTo: getDefaultDateTo(),
    description: 'Тростниковые заросли и очаги выгорания (UTM 37N)',
  },
];

interface LeftAnalyticsDockProps {
  report: BackendAnalyticalReport | null;
  selectedZone: ZonePreset | null;
  onSelectZone: (zone: ZonePreset) => void;
  // Date and sensor controls
  dateFrom: string;
  setDateFrom: (d: string) => void;
  dateTo: string;
  setDateTo: (d: string) => void;
  includeRadar: boolean;
  setIncludeRadar: (val: boolean) => void;
  // Drawing props
  isDrawing: boolean;
  onToggleDrawing: () => void;
  drawnPointsCount: number;
  calculatedAreaHa: number;
  onFinishDrawing: () => void;
  onClearDrawing: () => void;
  // Analysis actions
  onRunAnalysis: () => void;
  isAnalyzing: boolean;
  analysisProgress: number;
  // Export actions
  onGeneratePdf: () => void;
  onExportGeoJSON: () => void;
  onExportShapefile: () => void;
  onExportJsonReport: () => void;
  onExportCsvReport: () => void;
}

export const LeftAnalyticsDock: React.FC<LeftAnalyticsDockProps> = ({
  report,
  selectedZone,
  onSelectZone,
  dateFrom,
  setDateFrom,
  dateTo,
  setDateTo,
  includeRadar,
  setIncludeRadar,
  isDrawing,
  onToggleDrawing,
  drawnPointsCount,
  calculatedAreaHa,
  onFinishDrawing,
  onClearDrawing,
  onRunAnalysis,
  isAnalyzing,
  analysisProgress,
  onGeneratePdf,
  onExportGeoJSON,
  onExportShapefile,
  onExportJsonReport,
  onExportCsvReport,
}) => {
  const totalAreaHa = report?.total_burned_area_ha ?? 0;
  const thermalAnomalies = report?.active_thermal_anomalies_count ?? 0;
  const period = report?.period ?? (selectedZone ? `${dateFrom} — ${dateTo}` : '—');

  const breakdown = report?.breakdown ?? [
    { class_id: 1, name: 'Слабая степень (Low)', area_ha: 0, percentage: 0 },
    { class_id: 2, name: 'Средняя степень (Moderate)', area_ha: 0, percentage: 0 },
    { class_id: 3, name: 'Сильная степень (High)', area_ha: 0, percentage: 0 },
  ];

  return (
    <aside className="no-print absolute top-20 left-6 z-30 w-[340px] flex flex-col gap-2.5 pointer-events-none select-none max-h-[calc(100vh-100px)]">
      <div className="overflow-y-auto pr-1 space-y-2.5 pointer-events-auto scrollbar-thin">
        {/* CARD 1: ZONE PRESET & DATES & DRAWING */}
        <div className="p-4 rounded-3xl bg-[#121316]/95 border border-white/10 backdrop-blur-2xl shadow-2xl space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] tracking-wider uppercase font-mono text-orange-400 font-bold flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5" />
              <span>Территория интереса (AOI)</span>
            </span>
            <span className="text-[10px] font-mono text-neutral-400 bg-white/5 px-2 py-0.5 rounded-full border border-white/5">
              {report?.utm_zone || 'WGS84 / UTM'}
            </span>
          </div>

          {/* Preset Zone Dropdown */}
          <div className="relative">
            <select
              value={selectedZone?.id || 'custom'}
              onChange={(e) => {
                const zone = BACKEND_PRESETS.find((z) => z.id === e.target.value);
                if (zone) onSelectZone(zone);
              }}
              className="w-full appearance-none bg-[#1A1C22] border border-white/10 rounded-2xl px-3 py-2 text-xs text-white font-semibold focus:outline-none focus:border-orange-500/50 cursor-pointer pr-8"
            >
              {BACKEND_PRESETS.map((zone) => (
                <option key={zone.id} value={zone.id} className="bg-[#121316] text-white">
                  {zone.name}
                </option>
              ))}
              <option value="custom" className="bg-[#121316] text-orange-300">
                ✏️ Пользовательский полигон (карта)
              </option>
            </select>
            <ChevronDown className="w-4 h-4 text-neutral-400 absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>

          {/* DATES PRE / POST */}
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div>
              <label className="text-[10px] text-[#9699A3] flex items-center gap-1 mb-1 font-mono">
                <Calendar className="w-3 h-3 text-orange-400" />
                <span>Дата «до» (Pre):</span>
              </label>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="w-full bg-[#18191E] border border-white/10 rounded-xl px-2 py-1 text-[11px] text-white font-mono focus:outline-none focus:border-orange-500/50"
              />
            </div>
            <div>
              <label className="text-[10px] text-[#9699A3] flex items-center gap-1 mb-1 font-mono">
                <Calendar className="w-3 h-3 text-red-400" />
                <span>Дата «после» (Post):</span>
              </label>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="w-full bg-[#18191E] border border-white/10 rounded-xl px-2 py-1 text-[11px] text-white font-mono focus:outline-none focus:border-orange-500/50"
              />
            </div>
          </div>

          {/* RADAR SENTINEL-1 TOGGLE */}
          <label className="flex items-center gap-2 text-xs cursor-pointer select-none pt-1">
            <input
              type="checkbox"
              checked={includeRadar}
              onChange={(e) => setIncludeRadar(e.target.checked)}
              className="rounded bg-[#1A1C22] border-white/20 text-orange-500 focus:ring-0 focus:ring-offset-0 cursor-pointer"
            />
            <span className="text-[11px] text-neutral-300 flex items-center gap-1">
              <Radar className="w-3.5 h-3.5 text-cyan-400" />
              <span>Радиолокация Sentinel-1 SAR (сквозь дым)</span>
            </span>
          </label>

          {/* FREE DRAWING BUTTONS */}
          <div className="flex items-center justify-between gap-1.5 pt-1">
            <button
              onClick={onToggleDrawing}
              className={`flex-1 py-2 px-3 rounded-2xl font-bold text-xs flex items-center justify-center gap-1.5 transition-all cursor-pointer ${
                isDrawing
                  ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/25 animate-pulse'
                  : 'bg-white/10 text-neutral-200 hover:bg-white/15'
              }`}
            >
              <PenTool className="w-3.5 h-3.5" />
              <span>{isDrawing ? 'Разметка активна (клик)' : 'Нарисовать свой полигон'}</span>
            </button>

            {drawnPointsCount > 0 && (
              <button
                onClick={onClearDrawing}
                className="p-2 rounded-2xl bg-white/10 hover:bg-white/20 text-[#9699A3] hover:text-white transition-colors cursor-pointer"
                title="Очистить полигон"
              >
                <RotateCcw className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {drawnPointsCount > 0 && (
            <div className="flex items-center justify-between text-[11px] px-1 font-mono">
              <span className="text-[#9699A3]">
                Точек: <strong className="text-white">{drawnPointsCount}</strong>
              </span>
              <span className="text-emerald-400 font-bold">~{calculatedAreaHa.toFixed(1)} га</span>
              {isDrawing && drawnPointsCount >= 3 && (
                <button
                  onClick={onFinishDrawing}
                  className="text-blue-400 hover:text-blue-300 font-bold cursor-pointer underline"
                >
                  Завершить
                </button>
              )}
            </div>
          )}

          {/* MAIN ANALYZE BUTTON */}
          <button
            onClick={onRunAnalysis}
            disabled={isAnalyzing}
            className="w-full py-2.5 px-4 rounded-2xl bg-gradient-to-r from-orange-500 to-red-600 hover:from-orange-600 hover:to-red-700 disabled:opacity-50 text-white font-black text-xs tracking-wider uppercase transition-all shadow-lg shadow-orange-500/25 active:scale-[0.98] flex items-center justify-center gap-2 cursor-pointer"
          >
            {isAnalyzing ? (
              <>
                <div className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                <span>Анализ Sentinel + VIIRS ({analysisProgress}%)...</span>
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5 fill-white" />
                <span>Запустить космический анализ</span>
              </>
            )}
          </button>
        </div>

        {/* LIVE SATELLITE ENGINE BADGE */}
        <div className="p-2.5 rounded-2xl bg-[#18191E]/90 border border-white/10 flex items-center gap-2 text-xs text-neutral-300">
          <Sparkles className="w-3.5 h-3.5 text-orange-400 shrink-0" />
          <div className="text-[11px] leading-tight">
            <span className="font-semibold text-white block">Спутниковый мониторинг online</span>
            <span className="text-[10px] text-[#9699A3]">
              {report?.model_af?.includes('FIRMS') || report?.model_bs?.includes('STAC')
                ? 'Реальное время: Sentinel-2 STAC + NASA FIRMS VIIRS 375m'
                : 'Комплекс ДЗЗ: Sentinel-2/1 + VIIRS Active Fire'}
            </span>
          </div>
        </div>

        {/* SENSING CONTEXT / NEAREST PASS INFO */}
        {report && (report as any).nearest_scene && (
          <div className="p-2.5 rounded-2xl bg-cyan-950/40 border border-cyan-500/30 text-[11px] text-cyan-200 space-y-1">
            <div className="flex items-center gap-1.5 font-bold text-cyan-300">
              <Sparkles className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
              <span>Смежный спутниковый снимок</span>
            </div>
            <p className="text-[10px] text-neutral-300 leading-tight">
              Для точного квадрата прямых снимков нет. Подключена сцена <span className="font-mono text-white font-bold">{(report as any).nearest_scene.chip_id}</span> ({(report as any).nearest_scene.distance_km} км от полигона).
            </p>
          </div>
        )}

        {report && totalAreaHa === 0 && thermalAnomalies === 0 && (
          <div className="p-2.5 rounded-2xl bg-emerald-950/40 border border-emerald-500/30 text-[11px] text-emerald-200 space-y-1">
            <span className="font-bold text-emerald-300 block">🟢 Территория вне зоны горения</span>
            <p className="text-[10px] text-neutral-300 leading-tight">
              За выбранный период открытого огня VIIRS и следов гарей не обнаружено (0.0 га). Растительный покров стабилен.
            </p>
          </div>
        )}

        {/* CARD 2: TOTAL AREA & ACTIVE HOTSPOTS */}
        <div className="grid grid-cols-2 gap-2 p-3 rounded-3xl bg-[#121316]/95 border border-white/10 backdrop-blur-2xl shadow-2xl">
          <div className="p-2.5 rounded-2xl bg-[#18191E] border border-white/5">
            <span className="text-[10px] text-[#9699A3] block">Площадь гари</span>
            <div className="flex items-baseline gap-1 mt-0.5">
              <span className="text-2xl font-black text-red-500 font-mono">
                {totalAreaHa.toFixed(1)}
              </span>
              <span className="text-[10px] text-neutral-400">га</span>
            </div>
          </div>

          <div className="p-2.5 rounded-2xl bg-[#18191E] border border-white/5">
            <div className="flex items-center gap-1 text-[10px] text-orange-400 font-bold">
              <Flame className="w-3 h-3 fill-orange-400" />
              <span>Очагов (VIIRS)</span>
            </div>
            <div className="flex items-baseline gap-1 mt-0.5">
              <span className="text-2xl font-black text-white font-mono">{thermalAnomalies}</span>
              <span className="text-[10px] text-neutral-400">точки</span>
            </div>
          </div>
        </div>

        {/* CARD 3: 3 SEVERITY CLASSES BREAKDOWN */}
        <div className="p-3.5 rounded-3xl bg-[#121316]/95 border border-white/10 backdrop-blur-2xl shadow-2xl space-y-2">
          <div className="flex items-center justify-between text-[10px] text-[#9699A3] font-mono">
            <span>Распределение степеней:</span>
            <span title={period} className="truncate max-w-[150px]">{period}</span>
          </div>

          <div className="space-y-1.5 text-xs">
            {breakdown.map((b) => {
              const color =
                b.class_id === 3 ? 'bg-red-500' : b.class_id === 2 ? 'bg-orange-500' : 'bg-yellow-400';
              const textCol =
                b.class_id === 3 ? 'text-red-400' : b.class_id === 2 ? 'text-orange-400' : 'text-yellow-400';
              const areaVal = typeof b.area_ha === 'number' ? b.area_ha.toFixed(1) : '0.0';
              const pctVal = typeof b.percentage === 'number' ? b.percentage.toFixed(1) : '0.0';

              return (
                <div key={b.class_id} className="space-y-1">
                  <div className="flex justify-between items-center text-[11px]">
                    <span className={`font-bold ${textCol}`}>Класс {b.class_id} ({b.name.split('(')[0].trim()})</span>
                    <span className="font-mono text-white font-bold">
                      {areaVal} га ({pctVal}%)
                    </span>
                  </div>
                  <div className="w-full h-1.5 rounded-full bg-white/10 overflow-hidden">
                    <div className={`h-full ${color} rounded-full`} style={{ width: `${pctVal}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* CARD 4: ALL EXPORTS (CRITERION 4) */}
        <div className="p-3 rounded-3xl bg-[#121316]/95 border border-white/10 backdrop-blur-2xl shadow-2xl space-y-1.5">
          <button
            onClick={onGeneratePdf}
            className="w-full py-2 px-3 rounded-2xl bg-white text-black hover:bg-neutral-200 font-extrabold text-xs flex items-center justify-center gap-2 transition-all active:scale-95 shadow-md cursor-pointer"
          >
            <FileText className="w-4 h-4 text-black" />
            <span>Сгенерировать отчёт (PDF)</span>
          </button>

          <div className="grid grid-cols-2 gap-1.5 pt-0.5">
            <button
              onClick={onExportGeoJSON}
              className="py-2 px-2 rounded-xl bg-[#1C1E24] hover:bg-[#252830] border border-white/10 text-white text-[11px] font-medium flex items-center justify-center gap-1.5 transition-all active:scale-95 cursor-pointer"
              title="Выгрузить контуры гарей в стандарте RFC 7946 GeoJSON"
            >
              <Download className="w-3 h-3 text-orange-400" />
              <span>GeoJSON</span>
            </button>

            <button
              onClick={onExportShapefile}
              className="py-2 px-2 rounded-xl bg-[#1C1E24] hover:bg-[#252830] border border-white/10 text-white text-[11px] font-medium flex items-center justify-center gap-1.5 transition-all active:scale-95 cursor-pointer"
              title="Выгрузить ZIP-архив ESRI Shapefile (.shp, .shx, .dbf, .prj, .cpg)"
            >
              <Download className="w-3 h-3 text-emerald-400" />
              <span>Shapefile (.zip)</span>
            </button>

            <button
              onClick={onExportJsonReport}
              className="py-2 px-2 rounded-xl bg-[#1C1E24] hover:bg-[#252830] border border-white/10 text-white text-[11px] font-medium flex items-center justify-center gap-1.5 transition-all active:scale-95 cursor-pointer"
              title="Выгрузить официальную справку в формате JSON"
            >
              <FileCode className="w-3 h-3 text-blue-400" />
              <span>Справка (JSON)</span>
            </button>

            <button
              onClick={onExportCsvReport}
              className="py-2 px-2 rounded-xl bg-[#1C1E24] hover:bg-[#252830] border border-white/10 text-white text-[11px] font-medium flex items-center justify-center gap-1.5 transition-all active:scale-95 cursor-pointer"
              title="Выгрузить официальную справку в формате CSV для таблиц"
            >
              <FileSpreadsheet className="w-3 h-3 text-yellow-400" />
              <span>Справка (CSV)</span>
            </button>
          </div>
        </div>
      </div>
    </aside>
  );
};
