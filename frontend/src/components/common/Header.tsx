import React from 'react';
import { Flame, SlidersHorizontal, CheckCircle2, Code2, ExternalLink } from 'lucide-react';
import { REMOTE_API_ORIGIN } from '../../api/fireApi';

interface HeaderProps {
  isSplitView: boolean;
  onToggleSplitView: () => void;
  selectedEntityTitle?: string;
  subTitle?: string;
  isBackendHealthy?: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  isSplitView,
  onToggleSplitView,
  selectedEntityTitle = 'Ростовская область (Нижний Дон)',
  subTitle = 'UTM 37N',
  isBackendHealthy = true,
}) => {
  return (
    <header className="no-print absolute top-4 left-6 right-6 z-40 flex items-center justify-between pointer-events-none select-none">
      {/* Brand & Service Identity */}
      <div className="flex items-center gap-3 p-2 px-4 rounded-full bg-[#101216]/95 border border-white/10 backdrop-blur-2xl shadow-2xl pointer-events-auto">
        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-orange-500 to-red-600 flex items-center justify-center text-white shadow-lg shadow-orange-500/20">
          <Flame className="w-4 h-4 fill-white" />
        </div>

        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-extrabold text-white tracking-wide uppercase">
              Fire-Operator
            </span>
            <span
              className={`text-[10px] font-mono px-2 py-0.5 rounded-full border flex items-center gap-1 ${
                isBackendHealthy
                  ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                  : 'bg-red-500/15 text-red-400 border-red-500/30'
              }`}
            >
              <CheckCircle2 className="w-2.5 h-2.5" />
              <span>{isBackendHealthy ? 'REST API Онлайн' : 'Подключение к API...'}</span>
            </span>
          </div>
          <p className="text-[10px] text-[#9699A3] font-mono">
            Двухэтапный космический мониторинг: Sentinel-2 + Sentinel-1 + VIIRS
          </p>
        </div>
      </div>

      {/* Right Controls: Comparison Slider Toggle & Location & API Link */}
      <div className="flex items-center gap-2.5 pointer-events-auto">
        {/* Interactive Before/After Split Switch */}
        <button
          onClick={onToggleSplitView}
          className={`px-4 py-2 rounded-full border backdrop-blur-2xl shadow-xl flex items-center gap-2 text-xs font-semibold transition-all cursor-pointer ${
            isSplitView
              ? 'bg-orange-500 text-white border-orange-400 shadow-orange-500/25'
              : 'bg-[#101216]/95 border-white/10 text-neutral-300 hover:text-white hover:bg-white/10'
          }`}
          title="Включить шторку сравнения: снимок до пожара и после локализации"
        >
          <SlidersHorizontal className="w-3.5 h-3.5" />
          <span>{isSplitView ? 'Шторка активна (↔)' : 'Сравнить до и после пожара'}</span>
        </button>

        {/* Selected Zone Pill */}
        <div className="px-4 py-2 rounded-full bg-[#101216]/95 border border-white/10 backdrop-blur-2xl shadow-2xl flex items-center gap-2 text-xs">
          <span className="w-2 h-2 rounded-full bg-orange-400 animate-pulse" />
          <span className="font-bold text-white">{selectedEntityTitle}</span>
          {subTitle && <span className="text-[#9699A3] font-mono">({subTitle})</span>}
        </div>

        {/* Swagger UI / REST API link */}
        <a
          href={`${REMOTE_API_ORIGIN}/docs`}
          target="_blank"
          rel="noreferrer"
          className="px-3.5 py-2 rounded-full bg-[#101216]/95 border border-white/10 hover:border-white/25 text-neutral-300 hover:text-white backdrop-blur-2xl shadow-2xl flex items-center gap-1.5 text-xs font-semibold transition-all"
          title="Открыть интерактивную документацию Swagger UI (FastAPI)"
        >
          <Code2 className="w-3.5 h-3.5 text-blue-400" />
          <span>Swagger API</span>
          <ExternalLink className="w-3 h-3 text-neutral-500" />
        </a>
      </div>
    </header>
  );
};
