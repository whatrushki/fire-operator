import React, { useState, useEffect } from 'react';
import {
  Flame,
  Trees,
  TrendingDown,
  RefreshCw,
  Columns2,
  Sparkles,
  ChevronUp,
  ChevronDown
} from 'lucide-react';

export type FirePhase = 'pre' | 'peak' | 'burn' | 'recovery';

interface FireTimelineGraphProps {
  currentPhase: FirePhase;
  onPhaseChange: (phase: FirePhase) => void;
  dateBefore: string;
  dateAfter: string;
  totalAreaHa: number;
  hotspotsCount: number;
  isSplitView: boolean;
  onToggleSplitView: () => void;
}

export const FireTimelineGraph: React.FC<FireTimelineGraphProps> = ({
  currentPhase,
  onPhaseChange,
  dateBefore,
  dateAfter,
  totalAreaHa,
  hotspotsCount,
  isSplitView,
  onToggleSplitView,
}) => {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);

  // Auto-cycle through phases if playing
  // Detect if the fire is fresh (< 30 days or active thermal hotspots present)
  const isFreshFire = React.useMemo(() => {
    try {
      if (hotspotsCount > 0) return true;
      const dTo = new Date(dateAfter);
      const dFrom = new Date(dateBefore);
      const diffDays = Math.abs((dTo.getTime() - dFrom.getTime()) / (1000 * 3600 * 24));
      return diffDays <= 35;
    } catch {
      return false;
    }
  }, [dateBefore, dateAfter, hotspotsCount]);

  // Auto-cycle through phases if playing
  useEffect(() => {
    if (!isPlaying) return;
    const phases: FirePhase[] = isFreshFire ? ['pre', 'peak', 'burn'] : ['pre', 'peak', 'burn', 'recovery'];
    const timer = setInterval(() => {
      const nextIdx = (phases.indexOf(currentPhase) + 1) % phases.length;
      onPhaseChange(phases[nextIdx]);
    }, 2800);
    return () => clearInterval(timer);
  }, [isPlaying, currentPhase, onPhaseChange, isFreshFire]);

  const hasFireData = totalAreaHa > 0 || hotspotsCount > 0;

  const phasesInfo = [
    {
      id: 'pre' as FirePhase,
      title: '1. До пожара',
      subtitle: 'Фон (Pre-fire)',
      color: 'emerald',
      badgeBg: 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300',
      activeBorder: 'border-emerald-500 bg-emerald-500/20 text-white shadow-emerald-500/25',
      icon: Trees,
      desc: hasFireData
        ? 'Здоровый растительный покров до инцидента: естественный фон (NDVI ~ 0.68).'
        : 'Естественный фоновый растительный покров: высокий NDVI (0.70), термоаномалий нет.',
      statLabel: 'Индекс NDVI',
      statValue: hasFireData ? '0.68 (до)' : '0.70 (норма)',
      isFreshDisabled: false,
    },
    {
      id: 'peak' as FirePhase,
      title: '2. Пик горения',
      subtitle: hasFireData ? 'Очаги (Active Fire)' : 'Очагов нет',
      color: 'red',
      badgeBg: 'bg-red-500/15 border-red-500/40 text-red-300',
      activeBorder: 'border-red-500 bg-red-500/25 text-white shadow-red-500/30',
      icon: Flame,
      desc: hasFireData
        ? 'Фаза активного пламени: резкий температурный скачок I4-I5 > 15K, детектирование VIIRS 375м.'
        : 'Открытого горения и термических аномалий VIIRS за выбранный период не зафиксировано.',
      statLabel: 'Термоточек VIIRS',
      statValue: `${hotspotsCount} очагов`,
      isFreshDisabled: false,
    },
    {
      id: 'burn' as FirePhase,
      title: '3. Гарь (Пост)',
      subtitle: hasFireData ? 'Зонирование (Burn Scar)' : 'Гарей нет',
      color: 'orange',
      badgeBg: 'bg-orange-500/15 border-orange-500/40 text-orange-300',
      activeBorder: 'border-orange-500 bg-orange-500/25 text-white shadow-orange-500/30',
      icon: TrendingDown,
      desc: hasFireData
        ? 'Послепожарный контур Sentinel-2: падение NDVI, скачок dNBR, классификация 3 степеней поражения.'
        : 'Следов гарей и спектральных аномалий dNBR в анализируемом полигоне не обнаружено.',
      statLabel: 'Площадь гари',
      statValue: `${totalAreaHa > 0 ? totalAreaHa.toFixed(1) : '0.0'} га`,
      isFreshDisabled: false,
    },
    {
      id: 'recovery' as FirePhase,
      title: isFreshFire ? '4. Восстановление' : '4. Восстановление',
      subtitle: !hasFireData ? 'Норма' : isFreshFire ? 'Фаза не наступила' : 'Регенерация (Recovery)',
      color: isFreshFire ? 'neutral' : 'cyan',
      badgeBg: isFreshFire
        ? 'bg-neutral-800 border-neutral-700 text-neutral-400'
        : 'bg-cyan-500/15 border-cyan-500/40 text-cyan-300',
      activeBorder: isFreshFire
        ? 'border-neutral-500 bg-neutral-800/80 text-neutral-300'
        : 'border-cyan-500 bg-cyan-500/25 text-white shadow-cyan-500/30',
      icon: RefreshCw,
      desc: !hasFireData
        ? 'Растительный покров стабилен, нарушение структуры биомассы не зафиксировано.'
        : isFreshFire
        ? 'Пожар свежий — фаза активной гари и тления. Растительный покров еще не успел восстановиться.'
        : 'Экологическая сукцессия: постепенное зарастание пионерными травами, регенерация почвы.',
      statLabel: 'Статус покрова',
      statValue: !hasFireData ? '100% (Норма)' : isFreshFire ? '0% (Свежий)' : '+18%/год',
      isFreshDisabled: isFreshFire,
    },
  ];

  return (
    <div className="no-print absolute bottom-3 left-1/2 -translate-x-1/2 z-20 w-[92%] max-w-[580px] lg:max-w-[620px] pointer-events-auto select-none transition-all duration-300">
      <div className="bg-[#121316]/95 border border-white/15 backdrop-blur-2xl rounded-3xl shadow-2xl overflow-hidden p-3 space-y-2.5">
        {/* HEADER BAR */}
        <div className="flex items-center justify-between gap-2 border-b border-white/10 pb-2">
          <div className="flex items-center gap-2 min-w-0">
            <div className={`p-1 rounded-xl border shrink-0 ${
              hasFireData
                ? 'bg-orange-500/20 border-orange-500/30 text-orange-400'
                : 'bg-emerald-500/20 border-emerald-500/30 text-emerald-400'
            }`}>
              {hasFireData ? <Sparkles className="w-3.5 h-3.5" /> : <Trees className="w-3.5 h-3.5" />}
            </div>
            <div className="truncate">
              <div className="flex items-center gap-1.5 flex-wrap">
                <h3 className="font-extrabold text-[11px] text-white uppercase tracking-wider truncate">
                  {hasFireData ? 'Динамика природного пожара' : 'Мониторинг фонового состояния'}
                </h3>
                <span className={`text-[9px] px-1.5 py-0.2 rounded-full font-mono border ${
                  hasFireData
                    ? 'bg-amber-500/20 border-amber-500/40 text-amber-300'
                    : 'bg-emerald-500/20 border-emerald-500/40 text-emerald-300'
                }`}>
                  {hasFireData ? (isFreshFire ? 'Инцидент зафиксирован' : 'Гарь в архиве') : 'Норма (0 га)'}
                </span>
              </div>
              <p className="text-[9px] text-neutral-400 truncate">
                {hasFireData
                  ? (isFreshFire ? 'Инцидент: До → Пик горения → Активная гарь' : 'Полный цикл: До → Пик → Гарь → Восстановление')
                  : 'Термоаномалий не выявлено: вегетационный покров стабилен'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            {/* Split View button */}
            <button
              onClick={onToggleSplitView}
              className={`py-1 px-2.5 rounded-xl text-[10px] font-bold flex items-center gap-1 transition-all cursor-pointer ${
                isSplitView
                  ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/30'
                  : 'bg-white/10 text-neutral-300 hover:bg-white/15'
              }`}
              title="Интерактивная шторка сравнения До и После"
            >
              <Columns2 className="w-3 h-3" />
              <span>{isSplitView ? 'Шторка: Вкл' : 'До / После'}</span>
            </button>

            {/* Play/pause animation */}
            <button
              onClick={() => setIsPlaying((p) => !p)}
              className={`py-1 px-2 rounded-xl text-[10px] font-bold flex items-center gap-1 transition-all cursor-pointer ${
                isPlaying
                  ? 'bg-emerald-600 text-white animate-pulse'
                  : 'bg-white/10 text-neutral-300 hover:bg-white/15'
              }`}
              title="Демонстрация этапов пожара"
            >
              <RefreshCw className={`w-3 h-3 ${isPlaying ? 'animate-spin' : ''}`} />
              <span>{isPlaying ? 'Стоп' : 'Анимация'}</span>
            </button>

            {/* Collapse toggle */}
            <button
              onClick={() => setIsCollapsed((c) => !c)}
              className="p-1 rounded-xl bg-white/10 text-neutral-400 hover:text-white transition-colors cursor-pointer"
            >
              {isCollapsed ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </button>
          </div>
        </div>

        {/* 4 PHASES BUTTONS */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {phasesInfo.map((phase) => {
            const Icon = phase.icon;
            const isActive = currentPhase === phase.id;
            return (
              <button
                key={phase.id}
                onClick={() => {
                  setIsPlaying(false);
                  onPhaseChange(phase.id);
                }}
                className={`p-2 rounded-2xl border text-left transition-all cursor-pointer flex flex-col justify-between gap-1 ${
                  isActive
                    ? `${phase.activeBorder} shadow-lg scale-[1.01]`
                    : 'bg-[#18191E]/90 border-white/5 text-neutral-300 hover:border-white/20'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <Icon className="w-3.5 h-3.5 shrink-0" />
                    <span className="font-extrabold text-[10px] truncate">{phase.title}</span>
                  </div>
                </div>

                <div className="flex justify-between items-baseline text-[9px]">
                  <span className="text-neutral-400 truncate">{phase.statLabel}:</span>
                  <span className="font-bold font-mono text-white shrink-0 ml-1">{phase.statValue}</span>
                </div>
              </button>
            );
          })}
        </div>

        {/* DETAILED GRAPH AND SPECTRAL CURVE (collapsible) */}
        {!isCollapsed && (
          <div className="space-y-2 pt-1 border-t border-white/10">
            {/* SVG SPECTRAL TRAJECTORY CHART */}
            <div className="relative h-20 w-full bg-[#0E0F12] rounded-2xl border border-white/5 px-3 py-2 flex flex-col justify-between overflow-hidden">
              <div className="absolute top-1 left-3 text-[9px] text-neutral-400 flex items-center gap-3 z-10 font-mono">
                <span className="flex items-center gap-1">
                  <span className="w-2.5 h-0.5 bg-emerald-400 inline-block rounded-full" />
                  NDVI (Вегетация)
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2.5 h-0.5 bg-orange-500 inline-block rounded-full" />
                  dNBR (Спектр гари)
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-red-500 inline-block" />
                  Очаги VIIRS
                </span>
              </div>

              {/* Dynamic SVG Curves */}
              <svg className="w-full h-full" viewBox="0 0 800 60" preserveAspectRatio="none">
                <defs>
                  <linearGradient id="fireGlow" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#EF4444" stopOpacity="0.4" />
                    <stop offset="100%" stopColor="#EF4444" stopOpacity="0.0" />
                  </linearGradient>
                </defs>

                {/* Vertical Stage Dividing Guides */}
                <line x1="200" y1="0" x2="200" y2="60" stroke="#ffffff" strokeOpacity="0.1" strokeDasharray="3 3" />
                <line x1="400" y1="0" x2="400" y2="60" stroke="#ffffff" strokeOpacity="0.1" strokeDasharray="3 3" />
                <line x1="600" y1="0" x2="600" y2="60" stroke="#ffffff" strokeOpacity="0.1" strokeDasharray="3 3" />

                {/* Highlight Active Stage Background */}
                {currentPhase === 'pre' && (
                  <rect x="0" y="0" width="200" height="60" fill="#10B981" fillOpacity="0.08" />
                )}
                {currentPhase === 'peak' && (
                  <rect x="200" y="0" width="200" height="60" fill="#EF4444" fillOpacity="0.12" />
                )}
                {currentPhase === 'burn' && (
                  <rect x="400" y="0" width="200" height="60" fill="#F97316" fillOpacity="0.1" />
                )}
                {currentPhase === 'recovery' && (
                  <rect x="600" y="0" width="200" height="60" fill={isFreshFire ? "#737373" : "#06B6D4"} fillOpacity="0.08" />
                )}

                {/* Peak fire glow area (only when fire data exists) */}
                {hasFireData && (
                  <polygon points="280,60 380,10 440,25 480,60" fill="url(#fireGlow)" />
                )}

                {/* Green NDVI curve */}
                {!hasFireData ? (
                  <path
                    d="M 0 18 L 800 18"
                    fill="none"
                    stroke="#10B981"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                  />
                ) : isFreshFire ? (
                  <path
                    d="M 0 16 Q 160 16, 260 22 T 350 54 Q 450 56, 560 54 L 800 54"
                    fill="none"
                    stroke="#10B981"
                    strokeWidth="2.5"
                    strokeDasharray="4 3"
                    strokeLinecap="round"
                  />
                ) : (
                  <path
                    d="M 0 16 Q 160 16, 260 22 T 350 54 Q 450 56, 560 48 T 800 32"
                    fill="none"
                    stroke="#10B981"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                  />
                )}

                {/* Orange dNBR curve */}
                {!hasFireData ? (
                  <path
                    d="M 0 52 L 800 52"
                    fill="none"
                    stroke="#F97316"
                    strokeWidth="2"
                    strokeLinecap="round"
                  />
                ) : isFreshFire ? (
                  <path
                    d="M 0 52 Q 180 52, 270 45 T 370 12 Q 440 18, 540 26 L 800 30"
                    fill="none"
                    stroke="#F97316"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                  />
                ) : (
                  <path
                    d="M 0 52 Q 180 52, 270 45 T 370 12 Q 440 18, 540 36 T 800 44"
                    fill="none"
                    stroke="#F97316"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                  />
                )}

                {/* Watermark in background when no fires */}
                {!hasFireData && (
                  <text x="400" y="38" fill="#52525B" fontSize="10" fontFamily="monospace" textAnchor="middle" fontWeight="bold">
                    [ Фоновый мониторинг: вегетационный покров стабилен, гарей нет ]
                  </text>
                )}

                {/* Thermal anomaly dots at peak (only when fire detected) */}
                {hasFireData && (
                  <>
                    <circle cx="340" cy="18" r="4" fill="#EF4444" className="animate-ping" />
                    <circle cx="340" cy="18" r="3.5" fill="#EF4444" />
                    <circle cx="365" cy="12" r="3.5" fill="#EF4444" />
                    <circle cx="390" cy="16" r="3.5" fill="#EF4444" />
                  </>
                )}

                {/* Phase Cursor Line */}
                {currentPhase === 'pre' && <line x1="100" y1="0" x2="100" y2="60" stroke="#10B981" strokeWidth="2" />}
                {currentPhase === 'peak' && <line x1="300" y1="0" x2="300" y2="60" stroke="#EF4444" strokeWidth="2" />}
                {currentPhase === 'burn' && <line x1="500" y1="0" x2="500" y2="60" stroke="#F97316" strokeWidth="2" />}
                {currentPhase === 'recovery' && <line x1="700" y1="0" x2="700" y2="60" stroke={isFreshFire ? "#a3a3a3" : "#06B6D4"} strokeWidth="2" />}
              </svg>

              {/* Stage markers bottom */}
              <div className="grid grid-cols-4 text-center text-[9px] font-mono text-neutral-400 z-10">
                <span className={currentPhase === 'pre' ? 'text-emerald-400 font-bold' : ''}>1. ДО ПОЖАРА</span>
                <span className={currentPhase === 'peak' ? 'text-red-400 font-bold' : ''}>2. ПИК (24 Ч)</span>
                <span className={currentPhase === 'burn' ? 'text-orange-400 font-bold' : ''}>3. ГАРЬ (BS)</span>
                <span className={currentPhase === 'recovery' ? (isFreshFire ? 'text-neutral-400 font-bold' : 'text-cyan-400 font-bold') : ''}>
                  {isFreshFire ? '4. БЕЗ РЕГЕНЕРАЦИИ' : '4. ВОССТАНОВЛЕНИЕ'}
                </span>
              </div>
            </div>

            {/* Current Phase Context Explanation */}
            <div className="text-[10px] text-neutral-300 bg-[#16171D] p-2 rounded-xl border border-white/5 flex items-center justify-between">
              <div className="flex items-center gap-1.5 truncate">
                <span className={`w-2 h-2 rounded-full shrink-0 ${currentPhase === 'recovery' && isFreshFire ? 'bg-neutral-500' : 'bg-orange-400'}`} />
                <span className="truncate">
                  {phasesInfo.find((p) => p.id === currentPhase)?.desc}
                </span>
              </div>
              <span className="text-[9px] font-mono text-neutral-400 shrink-0 ml-2">
                {dateBefore} — {dateAfter}
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
