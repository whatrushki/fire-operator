import React, { useState } from 'react';
import type {
  GeoJSONFeatureCollection,
  BurnContourFeature,
  ThermalPointFeature,
} from '../../api/fireApi';
import { Layers, ChevronRight, Flame } from 'lucide-react';

interface RightContoursDockProps {
  burnGeoJson: GeoJSONFeatureCollection<BurnContourFeature> | null;
  thermalGeoJson: GeoJSONFeatureCollection<ThermalPointFeature> | null;
  onSelectFeature: (feature: any) => void;
  selectedFeature: any | null;
}

export const RightContoursDock: React.FC<RightContoursDockProps> = ({
  burnGeoJson,
  thermalGeoJson,
  onSelectFeature,
  selectedFeature,
}) => {
  const [tab, setTab] = useState<'contours' | 'hotspots'>('contours');

  const polygonFeatures = burnGeoJson?.features || [];
  const pointFeatures = thermalGeoJson?.features || [];

  if (polygonFeatures.length === 0 && pointFeatures.length === 0) return null;

  // Sort contours by area descending
  const sortedContours = [...polygonFeatures].sort((a, b) => {
    return (b.properties?.area_ha || 0) - (a.properties?.area_ha || 0);
  });

  return (
    <aside className="no-print absolute top-20 right-6 z-30 w-80 flex flex-col gap-2 pointer-events-none select-none">
      <div className="p-3.5 rounded-3xl bg-[#121316]/95 border border-white/10 backdrop-blur-2xl shadow-2xl pointer-events-auto space-y-2.5">
        {/* Tab switch: Contours vs Hotspots */}
        <div className="flex items-center gap-1 p-1 bg-[#18191E] rounded-2xl border border-white/5">
          <button
            onClick={() => setTab('contours')}
            className={`flex-1 py-1.5 px-2 rounded-xl text-xs font-bold flex items-center justify-center gap-1.5 transition-all cursor-pointer ${
              tab === 'contours'
                ? 'bg-[#252830] text-white shadow-md'
                : 'text-[#9699A3] hover:text-white'
            }`}
          >
            <Layers className="w-3.5 h-3.5 text-orange-400" />
            <span>Гари ({polygonFeatures.length})</span>
          </button>

          <button
            onClick={() => setTab('hotspots')}
            className={`flex-1 py-1.5 px-2 rounded-xl text-xs font-bold flex items-center justify-center gap-1.5 transition-all cursor-pointer ${
              tab === 'hotspots'
                ? 'bg-[#252830] text-white shadow-md'
                : 'text-[#9699A3] hover:text-white'
            }`}
          >
            <Flame className="w-3.5 h-3.5 text-red-500" />
            <span>Очаги AF ({pointFeatures.length})</span>
          </button>
        </div>

        {/* Polygons Tab */}
        {tab === 'contours' && (
          <div className="space-y-1.5 max-h-[calc(100vh-250px)] overflow-y-auto pr-1 scrollbar-thin">
            {sortedContours.length === 0 ? (
              <div className="text-center py-4 text-xs text-[#9699A3]">
                Нет обнаруженных контуров
              </div>
            ) : (
              sortedContours.slice(0, 100).map((f, idx) => {
                const props = f.properties || {};
                const sev = props.severity_class || 1;
                const isSelected =
                  selectedFeature?.properties?.contour_id === props.contour_id;

                const dotColor =
                  sev === 3 ? 'bg-red-500' : sev === 2 ? 'bg-orange-500' : 'bg-yellow-400';

                const sevLabel =
                  sev === 3 ? 'Сильная (3)' : sev === 2 ? 'Средняя (2)' : 'Слабая (1)';

                return (
                  <button
                    key={props.contour_id || idx}
                    onClick={() => onSelectFeature(f)}
                    className={`w-full p-2.5 rounded-2xl border text-left transition-all cursor-pointer flex items-center justify-between ${
                      isSelected
                        ? 'bg-[#252830] border-white/40 shadow-lg'
                        : 'bg-[#18191E] border-white/5 hover:bg-[#202228] hover:border-white/15'
                    }`}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span className={`w-2.5 h-2.5 rounded-full ${dotColor} shrink-0`} />
                      <div className="truncate">
                        <span className="text-xs font-bold text-white block truncate">
                          {props.contour_id || `CNT-${idx + 1}`}
                        </span>
                        <span className="text-[10px] font-mono text-[#9699A3]">
                          {sevLabel} • {props.utm_zone || 'UTM'}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0 ml-2">
                      <span className="text-xs font-mono font-black text-white">
                        {typeof props.area_ha === 'number' ? `${props.area_ha.toFixed(2)} га` : '—'}
                      </span>
                      <ChevronRight className="w-3.5 h-3.5 text-neutral-500" />
                    </div>
                  </button>
                );
              })
            )}
            {sortedContours.length > 100 && (
              <div className="text-center text-[10px] text-neutral-400 py-1">
                Показаны первые 100 из {sortedContours.length} контуров
              </div>
            )}
          </div>
        )}

        {/* Hotspots Tab */}
        {tab === 'hotspots' && (
          <div className="space-y-1.5 max-h-[calc(100vh-250px)] overflow-y-auto pr-1 scrollbar-thin">
            {pointFeatures.length === 0 ? (
              <div className="text-center py-4 text-xs text-[#9699A3]">
                Нет активных термоточек VIIRS
              </div>
            ) : (
              pointFeatures.map((f, idx) => {
                const p = f.properties || {};
                const isSelected =
                  selectedFeature?.properties?.point_id === p.point_id;

                return (
                  <button
                    key={p.point_id || idx}
                    onClick={() => onSelectFeature(f)}
                    className={`w-full p-2.5 rounded-2xl border text-left transition-all cursor-pointer flex items-center justify-between ${
                      isSelected
                        ? 'bg-[#252830] border-red-500/50 shadow-lg'
                        : 'bg-[#18191E] border-white/5 hover:bg-[#202228] hover:border-white/15'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <div className="w-6 h-6 rounded-full bg-red-500/20 text-red-500 flex items-center justify-center shrink-0">
                        <Flame className="w-3.5 h-3.5 fill-red-500" />
                      </div>
                      <div>
                        <span className="text-xs font-bold text-white block">
                          {p.point_id || `AF-${idx + 1}`}
                        </span>
                        <span className="text-[10px] font-mono text-[#9699A3]">
                          {p.satellite || 'VIIRS'} • ΔT: +{p.delta_t_k || '—'}K
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center gap-1.5 text-right">
                      <div>
                        <span className="text-xs font-mono font-bold text-red-400 block">
                          {p.brightness_temp_i4_k || '—'} K
                        </span>
                        <span className="text-[9px] text-emerald-400 font-mono">
                          {p.confidence || 'high'}
                        </span>
                      </div>
                      <ChevronRight className="w-3.5 h-3.5 text-neutral-500" />
                    </div>
                  </button>
                );
              })
            )}
          </div>
        )}
      </div>
    </aside>
  );
};
