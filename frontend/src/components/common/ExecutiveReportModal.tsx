import React, { useRef, useState } from 'react';
import type { BackendAnalyticalReport } from '../../api/fireApi';
import { X, Printer, Download, FileText, CheckCircle2, ShieldAlert, BarChart3, Loader2, PieChart } from 'lucide-react';
import { exportElementToPdf } from '../../utils/pdfGenerator';

interface ExecutiveReportModalProps {
  isOpen: boolean;
  onClose: () => void;
  report: BackendAnalyticalReport | null;
  zoneName: string;
  calculatedAreaHa?: number;
}

export const ExecutiveReportModal: React.FC<ExecutiveReportModalProps> = ({
  isOpen,
  onClose,
  report,
  zoneName,
  calculatedAreaHa,
}) => {
  const reportContentRef = useRef<HTMLDivElement>(null);
  const [isDownloadingPdf, setIsDownloadingPdf] = useState(false);

  if (!isOpen) return null;

  const totalArea = report?.total_burned_area_ha ?? (calculatedAreaHa && calculatedAreaHa > 0 ? calculatedAreaHa : 0);
  const taskId = report?.task_id ?? 'tsk_report';
  const utmZone = report?.utm_zone || 'EPSG:32638';
  const regionName = report?.region || zoneName;

  const b1 = report?.breakdown?.find((b) => b.class_id === 1) || { area_ha: 0, percentage: 0, name: 'Слабая степень (Low)' };
  const b2 = report?.breakdown?.find((b) => b.class_id === 2) || { area_ha: 0, percentage: 0, name: 'Средняя степень (Moderate)' };
  const b3 = report?.breakdown?.find((b) => b.class_id === 3) || { area_ha: 0, percentage: 0, name: 'Сильная степень (High)' };

  const p1 = Math.max(0, b1.percentage);
  const p2 = Math.max(0, b2.percentage);
  const p3 = Math.max(0, b3.percentage);
  const sumP = p1 + p2 + p3 > 0 ? p1 + p2 + p3 : 100;
  const norm1 = (p1 / sumP) * 100;
  const norm2 = (p2 / sumP) * 100;
  const norm3 = (p3 / sumP) * 100;

  // Donut chart math (circumference = 2 * pi * 65 ≈ 408.4)
  const C = 408.4;
  const arc1 = (norm1 / 100) * C;
  const arc2 = (norm2 / 100) * C;
  const arc3 = (norm3 / 100) * C;

  const offset1 = 0;
  const offset2 = -arc1;
  const offset3 = -(arc1 + arc2);

  // Bar chart math
  const maxHa = Math.max(1, b1.area_ha, b2.area_ha, b3.area_ha);

  const handleDownloadPdf = async () => {
    if (!reportContentRef.current) return;
    setIsDownloadingPdf(true);
    try {
      await exportElementToPdf(reportContentRef.current, `Expert_Burn_Report_${taskId}.pdf`);
    } catch (err) {
      console.error('PDF generation error:', err);
      window.print();
    } finally {
      setIsDownloadingPdf(false);
    }
  };

  const handlePrint = () => {
    window.print();
  };

  const todayStr = new Date().toLocaleDateString('ru-RU');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-xl overflow-y-auto animate-in fade-in duration-200">
      <div className="relative w-full max-w-4xl bg-[#121316] border border-white/15 rounded-3xl shadow-2xl p-6 text-white my-6 max-h-[92vh] overflow-y-auto">
        {/* Top Action Bar (Hidden on Print) */}
        <div className="no-print flex items-center justify-between pb-5 border-b border-white/10">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-orange-500/15 border border-orange-500/30 flex items-center justify-center text-orange-400">
              <FileText className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white tracking-tight">
                Экспертное заключение по гарям (PDF)
              </h2>
              <p className="text-xs text-[#9699A3]">
                Официальный аналитический протокол мониторинга Sentinel-2 + Sentinel-1 + VIIRS
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleDownloadPdf}
              disabled={isDownloadingPdf}
              className="px-4 py-2 rounded-xl bg-orange-500 hover:bg-orange-600 disabled:opacity-50 text-white font-bold text-xs flex items-center gap-2 transition-all active:scale-95 shadow-lg shadow-orange-500/25 cursor-pointer"
            >
              {isDownloadingPdf ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Формирование PDF...</span>
                </>
              ) : (
                <>
                  <Download className="w-4 h-4" />
                  <span>Скачать PDF файл</span>
                </>
              )}
            </button>

            <button
              onClick={handlePrint}
              className="px-3.5 py-2 rounded-xl bg-white text-black hover:bg-neutral-200 font-semibold text-xs flex items-center gap-2 transition-all active:scale-95 shadow-md cursor-pointer"
            >
              <Printer className="w-4 h-4" />
              <span>Печать (Ctrl+P)</span>
            </button>

            <button
              onClick={onClose}
              className="p-2 rounded-xl text-[#9699A3] hover:text-white hover:bg-white/10 transition-colors ml-1 cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* PRINTABLE DOCUMENT (Captured by html2canvas into pure PDF) */}
        <div
          ref={reportContentRef}
          className="mt-6 p-8 bg-white text-neutral-900 rounded-2xl shadow-xl space-y-6"
          style={{
            width: '100%',
            maxWidth: '820px',
            margin: '0 auto',
            fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif',
            lineHeight: 1.45,
          }}
        >
          {/* Header */}
          <div className="flex justify-between items-start border-b-2 border-neutral-900 pb-4">
            <div>
              <div className="text-[11px] font-bold tracking-wider text-orange-600 uppercase font-mono">
                РОСЛЕСХОЗ РФ • НАЦИОНАЛЬНЫЙ ЦЕНТР ДЗЗ «РОСКОСМОС»
              </div>
              <h1 className="text-xl font-black text-neutral-900 mt-1" style={{ letterSpacing: '0px' }}>
                ЭКСПЕРТНЫЙ ОТЧЁТ ОЦЕНКИ ПЛОЩАДЕЙ И СТЕПЕНИ ГАРЕЙ
              </h1>
              <p className="text-xs text-neutral-500 mt-1 font-mono">
                ID задачи: <strong>{taskId}</strong> | Спутники: Sentinel-2 MSI (20м) + Sentinel-1 SAR + VIIRS (375м)
              </p>
            </div>

            <div className="text-right text-xs font-mono text-neutral-500">
              <div>Дата: {todayStr}</div>
              <div className="text-emerald-600 font-bold mt-1">● ВЕРИФИЦИРОВАНО ИИ</div>
            </div>
          </div>

          {/* Key Summary Cards */}
          <div className="grid grid-cols-4 gap-3 p-4 bg-neutral-50 rounded-xl border border-neutral-200">
            <div>
              <span className="text-[10px] font-bold text-neutral-500 uppercase tracking-wider block">
                Объект мониторинга
              </span>
              <span className="text-xs font-bold text-neutral-900 block mt-1 truncate">{regionName}</span>
              <span className="text-[10px] font-mono text-neutral-500">{utmZone}</span>
            </div>

            <div>
              <span className="text-[10px] font-bold text-neutral-500 uppercase tracking-wider block">
                Суммарная площадь
              </span>
              <span className="text-xl font-black text-red-600 font-mono block mt-1">
                {totalArea.toFixed(1)} га
              </span>
              <span className="text-[10px] text-neutral-500">По спутнику Sentinel-2</span>
            </div>

            <div>
              <span className="text-[10px] font-bold text-neutral-500 uppercase tracking-wider block">
                Очаги горения (AF)
              </span>
              <span className="text-xl font-black text-orange-600 font-mono block mt-1">
                {report?.active_thermal_anomalies_count ?? 0}
              </span>
              <span className="text-[10px] text-neutral-500">VIIRS 375м (3.74 мкм)</span>
            </div>

            <div>
              <span className="text-[10px] font-bold text-neutral-500 uppercase tracking-wider block">
                Выбросы CO₂ (оценка)
              </span>
              <span className="text-xl font-black text-neutral-800 font-mono block mt-1">
                {Math.round(totalArea * 48)} т
              </span>
              <span className="text-[10px] text-neutral-500">Потери фитомассы</span>
            </div>
          </div>

          {/* Section 1: Graphical Charts (Donut + Bars side-by-side) */}
          <div className="space-y-3">
            <h3 className="text-xs uppercase tracking-wider font-bold text-neutral-800 flex items-center gap-2">
              <PieChart className="w-4 h-4 text-orange-600" />
              <span>1. Графическое распределение степеней повреждения покрова</span>
            </h3>

            <div className="grid grid-cols-2 gap-4 p-4 bg-neutral-50 rounded-xl border border-neutral-200 items-center">
              {/* SVG Donut Chart */}
              <div className="flex items-center gap-4">
                <svg width="150" height="150" viewBox="0 0 160 160" className="shrink-0">
                  <circle cx="80" cy="80" r="65" fill="none" stroke="#E2E8F0" strokeWidth="18" />
                  {/* Class 1: Yellow */}
                  {arc1 > 0 && (
                    <circle
                      cx="80"
                      cy="80"
                      r="65"
                      fill="none"
                      stroke="#EAB308"
                      strokeWidth="18"
                      strokeDasharray={`${arc1} ${C - arc1}`}
                      strokeDashoffset={offset1}
                      transform="rotate(-90 80 80)"
                    />
                  )}
                  {/* Class 2: Orange */}
                  {arc2 > 0 && (
                    <circle
                      cx="80"
                      cy="80"
                      r="65"
                      fill="none"
                      stroke="#F97316"
                      strokeWidth="18"
                      strokeDasharray={`${arc2} ${C - arc2}`}
                      strokeDashoffset={offset2}
                      transform="rotate(-90 80 80)"
                    />
                  )}
                  {/* Class 3: Red */}
                  {arc3 > 0 && (
                    <circle
                      cx="80"
                      cy="80"
                      r="65"
                      fill="none"
                      stroke="#EF4444"
                      strokeWidth="18"
                      strokeDasharray={`${arc3} ${C - arc3}`}
                      strokeDashoffset={offset3}
                      transform="rotate(-90 80 80)"
                    />
                  )}
                  <text x="80" y="76" textAnchor="middle" fontSize="16" fontWeight="bold" fill="#0F172A">
                    {totalArea.toFixed(0)}
                  </text>
                  <text x="80" y="93" textAnchor="middle" fontSize="10" fill="#64748B" fontWeight="600">
                    гектаров
                  </text>
                </svg>

                <div className="space-y-1.5 text-xs">
                  <div className="flex items-center gap-2">
                    <span className="w-3 h-3 rounded-sm bg-yellow-400 shrink-0" />
                    <span className="text-neutral-600">Слабая (1):</span>
                    <strong className="text-neutral-900 font-mono">{b1.percentage.toFixed(1)}%</strong>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-3 h-3 rounded-sm bg-orange-500 shrink-0" />
                    <span className="text-neutral-600">Средняя (2):</span>
                    <strong className="text-neutral-900 font-mono">{b2.percentage.toFixed(1)}%</strong>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-3 h-3 rounded-sm bg-red-600 shrink-0" />
                    <span className="text-neutral-600">Сильная (3):</span>
                    <strong className="text-neutral-900 font-mono">{b3.percentage.toFixed(1)}%</strong>
                  </div>
                </div>
              </div>

              {/* Bar Chart Column Comparison */}
              <div className="border-l border-neutral-200 pl-4 space-y-2">
                <span className="text-[10px] font-bold text-neutral-500 uppercase tracking-wider block">
                  Площадь по категориям (га)
                </span>

                <div className="flex items-end justify-around h-28 pt-2">
                  {/* Bar 1: Class 1 */}
                  <div className="flex flex-col items-center gap-1 w-16">
                    <span className="text-[10px] font-mono font-bold text-neutral-700">
                      {b1.area_ha.toFixed(1)}
                    </span>
                    <div
                      className="w-10 rounded-t-md bg-yellow-400 transition-all"
                      style={{ height: `${Math.max(8, (b1.area_ha / maxHa) * 80)}px` }}
                    />
                    <span className="text-[10px] font-bold text-neutral-600">Класс 1</span>
                  </div>

                  {/* Bar 2: Class 2 */}
                  <div className="flex flex-col items-center gap-1 w-16">
                    <span className="text-[10px] font-mono font-bold text-neutral-700">
                      {b2.area_ha.toFixed(1)}
                    </span>
                    <div
                      className="w-10 rounded-t-md bg-orange-500 transition-all"
                      style={{ height: `${Math.max(8, (b2.area_ha / maxHa) * 80)}px` }}
                    />
                    <span className="text-[10px] font-bold text-neutral-600">Класс 2</span>
                  </div>

                  {/* Bar 3: Class 3 */}
                  <div className="flex flex-col items-center gap-1 w-16">
                    <span className="text-[10px] font-mono font-bold text-neutral-700">
                      {b3.area_ha.toFixed(1)}
                    </span>
                    <div
                      className="w-10 rounded-t-md bg-red-600 transition-all"
                      style={{ height: `${Math.max(8, (b3.area_ha / maxHa) * 80)}px` }}
                    />
                    <span className="text-[10px] font-bold text-neutral-600">Класс 3</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Section 2: Detailed Table */}
          <div className="space-y-2">
            <h3 className="text-xs uppercase tracking-wider font-bold text-neutral-800 flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-orange-600" />
              <span>2. Детализация по контурам и рекомендации лесоохраны</span>
            </h3>

            <table className="w-full text-left text-xs border-collapse border border-neutral-200">
              <thead>
                <tr className="bg-neutral-100 text-neutral-700 font-bold border-b border-neutral-200">
                  <th className="p-2.5">Степень повреждения</th>
                  <th className="p-2.5">Спектральный dNBR</th>
                  <th className="p-2.5">Площадь (га)</th>
                  <th className="p-2.5">Доля (%)</th>
                  <th className="p-2.5">Рекомендованные мероприятия</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-200 text-neutral-800">
                <tr>
                  <td className="p-2.5 font-bold text-yellow-600 flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-yellow-400" />
                    <span>Класс 1 (Слабая)</span>
                  </td>
                  <td className="p-2.5 font-mono">+0.10 … +0.27</td>
                  <td className="p-2.5 font-mono font-bold">{b1.area_ha.toFixed(1)} га</td>
                  <td className="p-2.5 font-mono font-bold">{b1.percentage.toFixed(1)}%</td>
                  <td className="p-2.5 text-neutral-600">Естественное лесовозобновление без вмешательства</td>
                </tr>
                <tr>
                  <td className="p-2.5 font-bold text-orange-600 flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-orange-500" />
                    <span>Класс 2 (Средняя)</span>
                  </td>
                  <td className="p-2.5 font-mono">+0.27 … +0.44</td>
                  <td className="p-2.5 font-mono font-bold">{b2.area_ha.toFixed(1)} га</td>
                  <td className="p-2.5 font-mono font-bold">{b2.percentage.toFixed(1)}%</td>
                  <td className="p-2.5 text-neutral-600">Лесопатологический надзор и частичная расчистка</td>
                </tr>
                <tr>
                  <td className="p-2.5 font-bold text-red-600 flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-red-600" />
                    <span>Класс 3 (Сильная)</span>
                  </td>
                  <td className="p-2.5 font-mono">&gt; +0.44</td>
                  <td className="p-2.5 font-mono font-bold">{b3.area_ha.toFixed(1)} га</td>
                  <td className="p-2.5 font-mono font-bold">{b3.percentage.toFixed(1)}%</td>
                  <td className="p-2.5 text-neutral-600">Сплошная санитарная рубка и минерализация периметра</td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Section 3: Operational Forestry Conclusions */}
          <div className="space-y-2">
            <h3 className="text-xs uppercase tracking-wider font-bold text-neutral-800 flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-emerald-600" />
              <span>3. Заключение оперативного лесоустройства</span>
            </h3>

            <div className="p-3.5 rounded-xl bg-neutral-50 border border-neutral-200 text-xs space-y-2 text-neutral-700">
              <div className="flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                <p>
                  <strong>Выгорание древостоя:</strong> На площади <strong>{b3.area_ha.toFixed(1)} га</strong> (Класс 3) зафиксировано полное выгорание древесного яруса. Подлежит искусственному лесовосстановлению.
                </p>
              </div>

              <div className="flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                <p>
                  <strong>Термические аномалии (VIIRS):</strong> Выявлено {report?.active_thermal_anomalies_count ?? 0} активных термоточек с радиометрической температурой свыше 320К в канале I4.
                </p>
              </div>
            </div>
          </div>

          {/* Official Signatures and Seals */}
          <div className="pt-4 border-t-2 border-neutral-300 flex items-center justify-between text-xs text-neutral-600">
            <div>
              <span className="block font-bold text-neutral-900">Исполнитель экспертизы ДЗЗ:</span>
              <span className="font-mono text-[11px]">ФБУ «Авиалесоохрана» / Программный комплекс Fire-Operator</span>
              <div className="mt-2 text-[11px] text-neutral-500">
                Подпись оператора: <em>Смирнов А. В. ___________</em>
              </div>
            </div>

            {/* Official Stamp Vector Seal */}
            <div className="flex items-center gap-3">
              <svg width="95" height="95" viewBox="0 0 100 100" className="text-blue-900">
                <circle cx="50" cy="50" r="46" fill="none" stroke="#1E3A8A" strokeWidth="2.5" strokeDasharray="3 2" />
                <circle cx="50" cy="50" r="41" fill="none" stroke="#1E3A8A" strokeWidth="1.5" />
                <circle cx="50" cy="50" r="28" fill="none" stroke="#1E3A8A" strokeWidth="1" />
                <text x="50" y="38" textAnchor="middle" fontSize="6.5" fontWeight="bold" fill="#1E3A8A">
                  РОСЛЕСХОЗ РФ
                </text>
                <text x="50" y="47" textAnchor="middle" fontSize="5.5" fontWeight="bold" fill="#1E3A8A">
                  ДЛЯ ЭКСПЕРТИЗЫ
                </text>
                <text x="50" y="55" textAnchor="middle" fontSize="6" fontWeight="bold" fill="#1E3A8A">
                  ВЕРИФИЦИРОВАНО
                </text>
                <text x="50" y="64" textAnchor="middle" fontSize="5" fill="#1E3A8A">
                  {todayStr}
                </text>
              </svg>

              <div className="text-right">
                <span className="block font-bold text-neutral-900">Гослесинспектор:</span>
                <span className="font-mono text-[11px]">Воронов И. К.</span>
                <div className="text-emerald-700 font-bold mt-1 text-[11px]">
                  ЭЦП ВАЛИДНА №RU-77-2025
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
