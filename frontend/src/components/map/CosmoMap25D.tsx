import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import DeckGL from '@deck.gl/react';
import type { MapViewState } from '@deck.gl/core';
import { GeoJsonLayer, ScatterplotLayer, TextLayer, PathLayer, PolygonLayer, BitmapLayer } from '@deck.gl/layers';
import { TileLayer } from '@deck.gl/geo-layers';
import type {
  GeoJSONFeatureCollection,
  BurnContourFeature,
  ThermalPointFeature,
} from '../../api/fireApi';
import type { ZonePreset } from '../common/LeftAnalyticsDock';
import type { FirePhase } from '../common/FireTimelineGraph';
import {
  Flame,
  PenTool,
  Check,
  RotateCcw,
  Columns2,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';

// Static Regional Labels across Russia for clear geographic orientation
const REGIONAL_LABELS = [
  {
    name: 'Цимлянск / Водохранилище',
    coordinates: [44.9544, 48.5831] as [number, number],
    type: 'region',
    description: 'Прибрежная полоса Цимлянского водохранилища (UTM 38N)'
  },
  {
    name: 'Ростовская обл. (Долина Маныча)',
    coordinates: [44.8219, 46.7403] as [number, number],
    type: 'region',
    description: 'Степные массивы и гари (UTM 38N, 559 контуров)'
  },
  {
    name: 'Элиста (Калмыкия)',
    coordinates: [44.6931, 45.8184] as [number, number],
    type: 'region',
    description: 'Степные ландшафты и массивы сухостоя (UTM 38N)'
  },
  {
    name: 'Астраханская обл. (Камыш)',
    coordinates: [40.3576, 49.1279] as [number, number],
    type: 'region',
    description: 'Тростниковые заросли и лиманы (UTM 37N)'
  },
  {
    name: 'Волгоград (Город)',
    coordinates: [44.51, 48.71] as [number, number],
    type: 'city',
    description: 'Нижнее Поволжье'
  },
  {
    name: 'Ростов-на-Дону (Город)',
    coordinates: [39.72, 47.23] as [number, number],
    type: 'city',
    description: 'Нижний Дон'
  },
  {
    name: 'Москва',
    coordinates: [37.62, 55.75] as [number, number],
    type: 'city',
    description: 'Центральный ФО'
  }
];

interface CosmoMap25DProps {
  burnGeoJson: GeoJSONFeatureCollection<BurnContourFeature> | null;
  thermalGeoJson: GeoJSONFeatureCollection<ThermalPointFeature> | null;
  selectedZone: ZonePreset | null;
  isSplitView: boolean;
  selectedFeature?: any | null;
  onSelectFeature?: (feature: any) => void;
  // Drawing mode props
  isDrawing: boolean;
  drawnPoints: [number, number][];
  onAddPoint: (point: [number, number]) => void;
  onFinishDrawing: () => void;
  onClearDrawing: () => void;
  calculatedAreaHa: number;
  onRunAnalysis?: () => void;
  dateBefore?: string;
  dateAfter?: string;
  currentPhase?: FirePhase;
}

export const CosmoMap25D: React.FC<CosmoMap25DProps> = ({
  burnGeoJson,
  thermalGeoJson,
  selectedZone,
  isSplitView,
  selectedFeature,
  onSelectFeature,
  isDrawing,
  drawnPoints,
  onAddPoint,
  onFinishDrawing,
  onClearDrawing,
  calculatedAreaHa,
  onRunAnalysis: _onRunAnalysis,
  dateBefore = '2024-06-01',
  dateAfter = '2024-09-15',
  currentPhase = 'burn',
}) => {
  // Base map style: 'satellite' (ArcGIS World Imagery) or 'osm' (OpenStreetMap)
  const [baseMapType, setBaseMapType] = useState<'satellite' | 'osm'>('satellite');

  // Split view divider position (percentage 0..100)
  const [splitPos, setSplitPos] = useState(50);
  const isDraggingSplitRef = useRef(false);

  // Deck.gl ViewState
  const [viewState, setViewState] = useState<MapViewState>({
    longitude: 44.9544,
    latitude: 48.5831,
    zoom: 11,
    pitch: 25,
    bearing: 0,
    maxZoom: 18,
    minZoom: 3,
  });

  // Tooltip state for hover
  const [hoverInfo, setHoverInfo] = useState<{
    x: number;
    y: number;
    title: string;
    items: { label: string; value: string }[];
  } | null>(null);

  // Synchronize map center when selectedZone changes
  useEffect(() => {
    if (selectedZone) {
      setViewState((prev) => ({
        ...prev,
        longitude: selectedZone.center[0],
        latitude: selectedZone.center[1],
        zoom: 9.5,
        transitionDuration: 1000,
      }));
    }
  }, [selectedZone]);

  // Handle map click: either adds drawing points or selects features
  const handleMapClick = useCallback(
    (info: any) => {
      if (isDrawing && info.coordinate) {
        const [lon, lat] = info.coordinate;
        onAddPoint([+lon.toFixed(5), +lat.toFixed(5)]);
        return;
      }

      if (info.object && onSelectFeature) {
        onSelectFeature(info.object);
      }
    },
    [isDrawing, onAddPoint, onSelectFeature]
  );

  // Split-view dragging handlers
  const handleSplitMouseDown = () => {
    isDraggingSplitRef.current = true;
  };

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isDraggingSplitRef.current) return;
      const pct = Math.max(5, Math.min(95, (e.clientX / window.innerWidth) * 100));
      setSplitPos(pct);
    };

    const handleMouseUp = () => {
      isDraggingSplitRef.current = false;
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, []);

  // -------------------------------------------------------------
  // DECK.GL LAYERS BUILDER
  // -------------------------------------------------------------
  // -------------------------------------------------------------
  // DECK.GL LAYERS: PRE-FIRE BASE (strictly unburned terrain)
  // -------------------------------------------------------------
  const preFireLayers = useMemo(() => {
    const tileUrl =
      baseMapType === 'osm'
        ? 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
        : 'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';

    const labelsData = [...REGIONAL_LABELS];
    if (selectedZone) {
      labelsData.push({
        name: `★ ${selectedZone.name}`,
        coordinates: selectedZone.center,
        type: 'active',
        description: selectedZone.description,
      });
    }

    return [
      new TileLayer({
        id: 'base-tiles-pre',
        data: tileUrl,
        minZoom: 0,
        maxZoom: 19,
        tileSize: 256,
        renderSubLayers: (props: any) => {
          const { boundingBox } = props.tile;
          return new BitmapLayer(props, {
            data: undefined,
            image: props.data,
            bounds: [boundingBox[0][0], boundingBox[0][1], boundingBox[1][0], boundingBox[1][1]],
          });
        },
      }),
      new TextLayer({
        id: 'regional-labels-pre',
        data: labelsData,
        getPosition: (d: any) => [d.coordinates[0], d.coordinates[1], 10],
        getText: (d: any) => d.name,
        getSize: (d: any) => (d.type === 'active' ? 17 : d.type === 'region' ? 14 : 12),
        getColor: (d: any) =>
          d.type === 'active'
            ? [255, 170, 0, 255]
            : d.type === 'region'
            ? [255, 255, 255, 230]
            : [200, 210, 225, 200],
        getTextAnchor: 'start',
        getAlignmentBaseline: 'center',
        background: true,
        getBackgroundColor: () => [15, 16, 20, 200],
        backgroundPadding: [6, 4],
        fontFamily: 'Inter, system-ui, sans-serif',
        fontWeight: 'bold',
        characterSet: 'auto',
      }),
    ];
  }, [baseMapType, selectedZone]);

  // -------------------------------------------------------------
  // DECK.GL LAYERS: POST-FIRE / FULL (scars, hotspots, drawings)
  // -------------------------------------------------------------
  const postFireLayers = useMemo(() => {
    const resultLayers: any[] = [];

    // 1. BASE TILE LAYER (OpenStreetMap or Satellite)
    const tileUrl =
      baseMapType === 'osm'
        ? 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
        : 'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';

    resultLayers.push(
      new TileLayer({
        id: 'base-tiles',
        data: tileUrl,
        minZoom: 0,
        maxZoom: 19,
        tileSize: 256,
        renderSubLayers: (props: any) => {
          const { boundingBox } = props.tile;
          return new BitmapLayer(props, {
            data: undefined,
            image: props.data,
            bounds: [boundingBox[0][0], boundingBox[0][1], boundingBox[1][0], boundingBox[1][1]],
          });
        },
      })
    );

    // 2. REGION & CITY TEXT LABELS LAYER
    const labelsData = [...REGIONAL_LABELS];
    if (selectedZone) {
      labelsData.push({
        name: `★ ${selectedZone.name}`,
        coordinates: selectedZone.center,
        type: 'active',
        description: selectedZone.description,
      });
    }

    resultLayers.push(
      new TextLayer({
        id: 'regional-labels',
        data: labelsData,
        getPosition: (d: any) => [d.coordinates[0], d.coordinates[1], 10],
        getText: (d: any) => d.name,
        getSize: (d: any) => (d.type === 'active' ? 17 : d.type === 'region' ? 14 : 12),
        getColor: (d: any) =>
          d.type === 'active'
            ? [255, 170, 0, 255]
            : d.type === 'region'
            ? [255, 255, 255, 230]
            : [200, 210, 225, 200],
        getTextAnchor: 'start',
        getAlignmentBaseline: 'center',
        background: true,
        getBackgroundColor: () => [15, 16, 20, 200],
        backgroundPadding: [6, 4],
        fontFamily: 'Inter, system-ui, sans-serif',
        fontWeight: 'bold',
        characterSet: 'auto',
      })
    );

    // Filter layers based on current Phase:
    // 'pre': Hide fire burns and thermal spots (pure pre-fire landscape)
    // 'peak': Show intense active thermal spots + preliminary scars
    // 'burn': Show full 3-class burn scars + thermal spots
    // 'recovery': Show burn scars with recovery styling
    const showBurns = currentPhase === 'burn' || currentPhase === 'recovery' || currentPhase === 'peak';
    const showHotspots = currentPhase === 'peak' || currentPhase === 'burn';

    // 3. BURN SEVERITY CONTOURS GEOJSON LAYER (3 CLASSES: Low, Moderate, High)
    if (showBurns && burnGeoJson && burnGeoJson.features && burnGeoJson.features.length > 0) {
      resultLayers.push(
        new GeoJsonLayer({
          id: 'burn-severity-contours',
          data: burnGeoJson,
          pickable: true,
          stroked: true,
          filled: true,
          extruded: false,
          lineWidthMinPixels: 2,
          getFillColor: (f: any) => {
            const cls = f.properties?.severity_class;
            if (cls === 3) return [239, 68, 68, 190]; // Class 3: Red (High)
            if (cls === 2) return [249, 115, 22, 175]; // Class 2: Orange (Moderate)
            return [234, 179, 8, 160]; // Class 1: Yellow (Low)
          },
          getLineColor: (f: any) => {
            const cls = f.properties?.severity_class;
            if (cls === 3) return [255, 100, 100, 255];
            if (cls === 2) return [255, 160, 60, 255];
            return [255, 220, 50, 255];
          },
          getLineWidth: (f: any) => {
            return selectedFeature?.id === f.id ? 4 : 2;
          },
          onHover: (info: any) => {
            if (info.object) {
              const props = info.object.properties || {};
              setHoverInfo({
                x: info.x,
                y: info.y,
                title: `Контур гари: ${props.contour_id || 'ID'}`,
                items: [
                  { label: 'Класс степени', value: `${props.severity_class} (${props.severity_ru || '—'})` },
                  { label: 'Площадь', value: `${props.area_ha ?? '—'} га` },
                  { label: 'Индекс dNBR', value: `${props.dnbr_mean ?? '—'}` },
                  { label: 'Зона UTM', value: `${props.utm_zone || 'EPSG:32638'}` },
                ],
              });
            } else {
              setHoverInfo(null);
            }
          },
        })
      );
    }

    // 4. ACTIVE FIRE THERMAL POINTS LAYER (VIIRS 375m)
    if (showHotspots && thermalGeoJson && thermalGeoJson.features && thermalGeoJson.features.length > 0) {
      resultLayers.push(
        new ScatterplotLayer({
          id: 'viirs-thermal-anomalies',
          data: thermalGeoJson.features,
          pickable: true,
          opacity: 0.9,
          stroked: true,
          filled: true,
          radiusScale: 1,
          radiusMinPixels: 7,
          radiusMaxPixels: 22,
          lineWidthMinPixels: 2.5,
          getPosition: (f: any) => f.geometry.coordinates,
          getRadius: (f: any) => {
            const i4 = f.properties?.brightness_temp_i4_k || 320;
            return Math.max(12, (i4 - 300) * 1.5);
          },
          getFillColor: (f: any) => {
            const i4 = f.properties?.brightness_temp_i4_k || 320;
            return i4 > 340 ? [255, 30, 0, 240] : [255, 110, 0, 220];
          },
          getLineColor: () => [255, 240, 100, 255],
          onHover: (info: any) => {
            if (info.object) {
              const p = info.object.properties || {};
              setHoverInfo({
                x: info.x,
                y: info.y,
                title: `Термоточка: ${p.point_id || 'AF-HOT'}`,
                items: [
                  { label: 'Спутник', value: `${p.satellite || 'VIIRS NOAA-20'}` },
                  { label: 'Яркостная темп. I4', value: `${p.brightness_temp_i4_k ?? '—'} K` },
                  { label: 'Радиационный контраст ΔT', value: `${p.delta_t_k ?? '—'} K` },
                  { label: 'Достоверность', value: `${p.confidence || 'номинальная'}` },
                  { label: 'Дата фиксации', value: `${p.acq_date || '—'}` },
                ],
              });
            } else {
              setHoverInfo(null);
            }
          },
        })
      );
    }

    // 5. REAL-TIME USER DRAWING LAYERS
    if (drawnPoints && drawnPoints.length > 0) {
      // Drawn vertices as blue markers
      resultLayers.push(
        new ScatterplotLayer({
          id: 'drawing-vertices',
          data: drawnPoints.map((pt, idx) => ({ pt, idx })),
          getPosition: (d: any) => d.pt,
          getFillColor: () => [59, 130, 246, 255],
          getLineColor: () => [255, 255, 255, 255],
          stroked: true,
          radiusMinPixels: 6,
          radiusMaxPixels: 9,
        })
      );

      // Lines connecting vertices
      if (drawnPoints.length >= 2) {
        resultLayers.push(
          new PathLayer({
            id: 'drawing-path',
            data: [{ path: drawnPoints }],
            getPath: (d: any) => d.path,
            getColor: () => [34, 211, 238, 255],
            widthMinPixels: 3,
            rounded: true,
          })
        );
      }

      // Filled polygon if >= 3 points
      if (drawnPoints.length >= 3) {
        resultLayers.push(
          new PolygonLayer({
            id: 'drawing-polygon-fill',
            data: [{ polygon: drawnPoints }],
            getPolygon: (d: any) => d.polygon,
            getFillColor: () => [34, 211, 238, 60],
            getLineColor: () => [34, 211, 238, 255],
            stroked: true,
            lineWidthMinPixels: 2,
          })
        );
      }
    }

    return resultLayers;
  }, [
    baseMapType,
    selectedZone,
    currentPhase,
    burnGeoJson,
    thermalGeoJson,
    selectedFeature,
    drawnPoints,
  ]);

  return (
    <div className="relative w-full h-full overflow-hidden bg-[#0A0B0E] select-none">
      {/* 1. MAIN DECK.GL CANVAS (POST-FIRE WITH SCARS & HOTSPOTS) */}
      <div className={`w-full h-full relative ${isDrawing ? 'cursor-crosshair' : 'cursor-grab'}`}>
        <DeckGL
          viewState={viewState}
          onViewStateChange={({ viewState: vs }: any) => setViewState(vs)}
          controller={{ doubleClickZoom: false, dragPan: true, scrollZoom: true }}
          layers={postFireLayers}
          onClick={handleMapClick}
          getCursor={({ isDragging }) => (isDrawing ? 'crosshair' : isDragging ? 'grabbing' : 'grab')}
        />
      </div>

      {/* 2. SYNCHRONIZED PRE-FIRE CANVAS CLIPPED BY SLIDER */}
      {isSplitView && (
        <div
          className="absolute inset-0 pointer-events-none z-10 overflow-hidden"
          style={{ clipPath: `inset(0 ${100 - splitPos}% 0 0)` }}
        >
          <DeckGL
            viewState={viewState}
            controller={false}
            layers={preFireLayers}
          />
          {/* Top Label (ДО) */}
          <div className="absolute top-20 left-1/4 -translate-x-1/2 z-20 pointer-events-none">
            <div className="bg-emerald-950/90 text-emerald-200 border border-emerald-500/50 px-3 py-1.5 rounded-2xl text-xs font-black shadow-2xl flex items-center gap-1.5 backdrop-blur-md">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
              <span>ДО ПОЖАРА ({dateBefore}) — ИСХОДНЫЙ ФОН</span>
            </div>
          </div>
        </div>
      )}

      {isSplitView && (
        <>
          {/* Top Label (ПОСЛЕ) */}
          <div className="absolute top-20 right-1/4 translate-x-1/2 z-20 pointer-events-none">
            <div className="bg-red-950/90 text-red-200 border border-red-500/50 px-3 py-1.5 rounded-2xl text-xs font-black shadow-2xl flex items-center gap-1.5 backdrop-blur-md">
              <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-ping" />
              <span>ПОСЛЕ ПОЖАРА ({dateAfter}) — ГАРИ И ОЧАГИ</span>
            </div>
          </div>

          {/* Draggable Divider Bar */}
          <div
            className="absolute top-0 bottom-0 z-20 w-1 bg-white shadow-[0_0_15px_rgba(255,255,255,0.8)] cursor-ew-resize pointer-events-auto"
            style={{ left: `${splitPos}%` }}
            onMouseDown={handleSplitMouseDown}
          >
            <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-8 h-8 rounded-full bg-white text-black flex items-center justify-center shadow-2xl border-2 border-neutral-900 cursor-ew-resize hover:scale-110 transition-transform">
              <Columns2 className="w-4 h-4 text-neutral-900" />
            </div>
          </div>
        </>
      )}

      {/* 3. FLOATING TOOLTIP ON HOVER */}
      {hoverInfo && (
        <div
          className="pointer-events-none absolute z-40 p-3 rounded-2xl bg-[#121316]/95 border border-white/20 backdrop-blur-xl shadow-2xl text-xs text-white max-w-xs space-y-1.5"
          style={{ left: hoverInfo.x + 15, top: hoverInfo.y + 15 }}
        >
          <div className="font-extrabold text-orange-400 border-b border-white/10 pb-1 flex items-center gap-1.5">
            <Flame className="w-3.5 h-3.5" />
            <span>{hoverInfo.title}</span>
          </div>
          <div className="space-y-1 text-[11px]">
            {hoverInfo.items.map((it, idx) => (
              <div key={idx} className="flex justify-between gap-3">
                <span className="text-neutral-400">{it.label}:</span>
                <span className="font-mono font-bold text-white text-right">{it.value}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 4. TOP MAP CONTROLS: BASE MAP TOGGLE & ZOOM */}
      <div className="absolute top-20 right-6 z-30 flex flex-col gap-2 pointer-events-auto">
        {/* Toggle Satellite / OpenStreetMap */}
        <div className="p-1 rounded-2xl bg-[#121316]/90 border border-white/15 backdrop-blur-2xl shadow-xl flex items-center gap-1">
          <button
            onClick={() => setBaseMapType('satellite')}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer ${
              baseMapType === 'satellite'
                ? 'bg-orange-500 text-white shadow-md shadow-orange-500/30'
                : 'text-neutral-400 hover:text-white'
            }`}
          >
            Спутник
          </button>
          <button
            onClick={() => setBaseMapType('osm')}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer ${
              baseMapType === 'osm'
                ? 'bg-orange-500 text-white shadow-md shadow-orange-500/30'
                : 'text-neutral-400 hover:text-white'
            }`}
          >
            OpenStreetMap
          </button>
        </div>

        {/* Zoom Controls */}
        <div className="flex flex-col rounded-2xl bg-[#121316]/90 border border-white/15 backdrop-blur-2xl shadow-xl overflow-hidden divide-y divide-white/10">
          <button
            onClick={() => setViewState((vs) => ({ ...vs, zoom: Math.min(18, vs.zoom + 1) }))}
            className="p-2.5 text-neutral-300 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
            title="Приблизить (+)"
          >
            <ZoomIn className="w-4 h-4" />
          </button>
          <button
            onClick={() => setViewState((vs) => ({ ...vs, zoom: Math.max(3, vs.zoom - 1) }))}
            className="p-2.5 text-neutral-300 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
            title="Отдалить (-)"
          >
            <ZoomOut className="w-4 h-4" />
          </button>
          <button
            onClick={() =>
              setViewState((vs) => ({
                ...vs,
                pitch: vs.pitch === 0 ? 40 : 0,
                bearing: 0,
              }))
            }
            className="p-2.5 text-neutral-300 hover:text-white hover:bg-white/10 transition-colors cursor-pointer text-[10px] font-bold"
            title="Переключить перспективу 2.5D / 2D"
          >
            {((viewState.pitch ?? 0) > 0) ? '2D' : '2.5D'}
          </button>
        </div>
      </div>

      {/* 5. DRAWING MODE FLOATING BANNER */}
      {isDrawing && (
        <div className="absolute top-20 left-1/2 -translate-x-1/2 z-30 bg-[#121316]/95 border border-blue-500/50 backdrop-blur-2xl shadow-2xl rounded-3xl p-3 px-5 flex items-center gap-4 animate-bounce">
          <div className="flex items-center gap-2">
            <PenTool className="w-4 h-4 text-blue-400 animate-pulse" />
            <div className="text-xs">
              <span className="font-extrabold text-white block">Разметка полигона активна</span>
              <span className="text-[11px] text-neutral-400">
                Кликайте по карте для добавления точек границы
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2 border-l border-white/10 pl-3">
            <div className="text-right">
              <span className="text-[10px] text-neutral-400 block font-mono">
                Точек: <strong className="text-white">{drawnPoints.length}</strong>
              </span>
              <span className="text-emerald-400 font-bold text-xs font-mono">
                ~{calculatedAreaHa.toFixed(1)} га
              </span>
            </div>

            {drawnPoints.length >= 3 && (
              <button
                onClick={onFinishDrawing}
                className="py-1.5 px-3 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs flex items-center gap-1 shadow-lg shadow-blue-500/30 transition-all cursor-pointer"
              >
                <Check className="w-3.5 h-3.5" />
                <span>Готово</span>
              </button>
            )}

            {drawnPoints.length > 0 && (
              <button
                onClick={onClearDrawing}
                className="p-1.5 rounded-xl bg-white/10 hover:bg-white/20 text-neutral-300 hover:text-white transition-colors cursor-pointer"
                title="Сбросить точки"
              >
                <RotateCcw className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
