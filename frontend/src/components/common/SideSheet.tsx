import React from 'react';
import { X, Flame, Layers, Download, ShieldCheck } from 'lucide-react';

interface SideSheetProps {
  isOpen: boolean;
  onClose: () => void;
  feature: any | null;
  zoneName?: string;
}

export const SideSheet: React.FC<SideSheetProps> = ({
  isOpen,
  onClose,
  feature,
  zoneName = 'Исследуемая зона',
}) => {
  if (!isOpen || !feature) return null;

  const props = feature.properties || {};
  const isPoint = feature.geometry?.type === 'Point';

  const contourId = isPoint
    ? props.point_id || 'AF-HOTSPOT'
    : props.contour_id || 'BS-CONTOUR';

  const severityClass = props.severity_class || 1;
  const severityRu =
    props.severity_ru ||
    props.severity_en ||
    (severityClass === 3
      ? 'Сильная степень (High)'
      : severityClass === 2
      ? 'Средняя степень (Moderate)'
      : 'Слабая степень (Low)');

  const areaHa = props.area_ha ?? 0;
  const utmZone = props.utm_zone || 'UTM EPSG:32638';

  const handleDownloadGeoJSON = () => {
    const blob = new Blob([JSON.stringify(feature, null, 2)], { type: 'application/geo+json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${contourId}.geojson`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="fixed inset-y-0 right-0 z-50 w-full max-w-[420px] bg-[#141519]/95 border-l border-white/10 backdrop-blur-2xl shadow-2xl p-6 flex flex-col justify-between animate-in slide-in-from-right duration-300">
      <div>
        {/* Header */}
        <div className="flex items-start justify-between pb-4 border-b border-white/[0.08]">
          <div className="flex items-center gap-2.5">
            <div
              className={`w-9 h-9 rounded-2xl flex items-center justify-center border ${
                isPoint
                  ? 'bg-red-500/15 border-red-500/30 text-red-400'
                  : severityClass === 3
                  ? 'bg-red-500/15 border-red-500/30 text-red-400'
                  : severityClass === 2
                  ? 'bg-orange-500/15 border-orange-500/30 text-orange-400'
                  : 'bg-yellow-500/15 border-yellow-500/30 text-yellow-400'
              }`}
            >
              {isPoint ? <Flame className="w-5 h-5 fill-red-500" /> : <Layers className="w-5 h-5" />}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-base font-semibold text-white">{contourId}</span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-white/10 text-neutral-300">
                  {utmZone}
                </span>
              </div>
              <p className="text-xs text-[#9699A3] mt-0.5">{zoneName}</p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-full text-[#9699A3] hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="mt-5 space-y-4">
          {/* Main Area or Temperature Metric */}
          <div className="p-4 rounded-[20px] bg-[#18191D] border border-white/[0.06]">
            <span className="text-[11px] text-[#9699A3]">
              {isPoint ? 'Параметры открытого горения VIIRS AF' : 'Площадь контура гари'}
            </span>
            <div className="flex items-baseline gap-1.5 mt-1">
              <span className="text-3xl font-bold tracking-tight text-white font-mono">
                {isPoint ? `${props.brightness_temp_i4_k || '—'} K` : `${areaHa.toFixed(2)} га`}
              </span>
              <span className="text-xs text-[#9699A3] font-mono">
                {isPoint ? '(Канал I4, 3.74 мкм)' : '(Sentinel-2 MSI 20м)'}
              </span>
            </div>

            <div className="mt-2.5 flex items-center gap-2 text-xs">
              <span
                className={`px-2.5 py-0.5 rounded-full text-[10px] font-medium border ${
                  isPoint
                    ? 'bg-red-500/20 text-red-400 border-red-500/30'
                    : severityClass === 3
                    ? 'bg-red-500/20 text-red-400 border-red-500/30'
                    : severityClass === 2
                    ? 'bg-orange-500/20 text-orange-400 border-orange-500/30'
                    : 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30'
                }`}
              >
                {isPoint ? `Очаг: ${props.confidence || 'high'}` : severityRu}
              </span>
              {!isPoint && (
                <span className="text-[11px] text-[#9699A3] font-mono">
                  Класс {severityClass}
                </span>
              )}
            </div>
          </div>

          {/* Details Table */}
          <div className="p-4 rounded-[20px] bg-[#18191D] border border-white/[0.06] space-y-2.5 text-xs">
            {isPoint ? (
              <>
                <div className="flex justify-between items-center py-1 border-b border-white/[0.04]">
                  <span className="text-[#9699A3]">Спутниковый сенсор:</span>
                  <span className="font-mono text-white font-medium">{props.satellite || 'VIIRS NOAA-20/21'}</span>
                </div>
                <div className="flex justify-between items-center py-1 border-b border-white/[0.04]">
                  <span className="text-[#9699A3]">Температура фона I5 (11.45 мкм):</span>
                  <span className="font-mono text-white font-medium">{props.brightness_temp_i5_k || '—'} K</span>
                </div>
                <div className="flex justify-between items-center py-1 border-b border-white/[0.04]">
                  <span className="text-[#9699A3]">Радиационный контраст ΔT (I4-I5):</span>
                  <span className="font-mono text-emerald-400 font-bold">+{props.delta_t_k || '—'} K</span>
                </div>
                <div className="flex justify-between items-center py-1">
                  <span className="text-[#9699A3]">Фильтрация факелов / бликов:</span>
                  <span className="font-mono text-emerald-400 font-bold flex items-center gap-1">
                    <ShieldCheck className="w-3.5 h-3.5" />
                    <span>Подтверждено</span>
                  </span>
                </div>
              </>
            ) : (
              <>
                <div className="flex justify-between items-center py-1 border-b border-white/[0.04]">
                  <span className="text-[#9699A3]">Сенсор ДЗЗ:</span>
                  <span className="font-mono text-white font-medium">Sentinel-2 MSI (L2A)</span>
                </div>
                <div className="flex justify-between items-center py-1 border-b border-white/[0.04]">
                  <span className="text-[#9699A3]">Разрешение пикселя:</span>
                  <span className="font-mono text-white font-medium">20 м (0.04 га/пикс)</span>
                </div>
                <div className="flex justify-between items-center py-1 border-b border-white/[0.04]">
                  <span className="text-[#9699A3]">Картографическая проекция:</span>
                  <span className="font-mono text-white font-medium">{utmZone}</span>
                </div>
                <div className="flex justify-between items-center py-1">
                  <span className="text-[#9699A3]">Спектральный индекс dNBR:</span>
                  <span className="font-mono text-orange-400 font-bold">
                    {props.dnbr_mean ? `+${props.dnbr_mean}` : severityClass === 3 ? '> +0.44' : severityClass === 2 ? '+0.27…+0.44' : '+0.10…+0.27'}
                  </span>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Export Single Feature */}
      <div className="pt-4 border-t border-white/[0.08]">
        <button
          onClick={handleDownloadGeoJSON}
          className="w-full py-2.5 px-4 rounded-xl bg-white/10 hover:bg-white/15 text-white text-xs font-semibold flex items-center justify-center gap-2 transition-all active:scale-98 cursor-pointer border border-white/10"
        >
          <Download className="w-4 h-4 text-orange-400" />
          <span>Выгрузить объект в GeoJSON</span>
        </button>
      </div>
    </div>
  );
};
