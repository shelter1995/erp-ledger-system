import { accountApi, AggregateData, Department } from '../api';
import React, { useState, useEffect } from 'react';
import {
  ArrowRight,
  BadgeDollarSign,
  Calendar,
  CheckCircle2,
  ClipboardList,
  Filter,
  HandCoins,
  ReceiptText,
  RefreshCw,
  TrendingUp,
  Truck,
} from 'lucide-react';
import { OperationLog, OrderRecord, ProjectLedger, ScreenType } from '../types';
import {
  getDashboardDepartments,
  getDashboardLatestModifiedAt,
  getDashboardMetrics,
  getDashboardSalesRanking,
  getDashboardTrendData,
} from '../lib/dashboardMetrics';
import { approximateMoney, decimalMoney, formatMoney as formatExactMoney, type MoneyValue } from '../lib/money';

interface DashboardScreenProps {
  serverMode?: boolean;
  showLogs?: boolean;
  logs: OperationLog[];
  ledgers: ProjectLedger[];
  orders: OrderRecord[];
  onNavigate: (screen: ScreenType) => void;
}

interface TrendPoint {
  x: number;
  y: number;
}

function compactMoney(value: MoneyValue) {
  if (decimalMoney(value).abs().gte(10000)) {
    return `${decimalMoney(value).div(10000).toFixed(2)} 万元`;
  }
  return `${formatExactMoney(value)} 元`;
}

function smoothPath(points: TrendPoint[]) {
  if (points.length === 0) return '';
  if (points.length === 1) return `M ${points[0].x} ${points[0].y}`;

  return points.slice(1).reduce((path, point, index) => {
    const previous = points[index];
    const middleX = (previous.x + point.x) / 2;
    return `${path} C ${middleX} ${previous.y}, ${middleX} ${point.y}, ${point.x} ${point.y}`;
  }, `M ${points[0].x} ${points[0].y}`);
}

export default function DashboardScreen({ logs, ledgers, orders, onNavigate, serverMode = false, showLogs = true }: DashboardScreenProps) {
  const [hoveredTrendIndex, setHoveredTrendIndex] = useState<number | null>(null);
  const [selectedDepartment, setSelectedDepartment] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  const [aggregate,setAggregate]=useState<Omit<AggregateData,'items'>|null>(null);
  const [departments,setDepartments]=useState<Department[]>([]);
  const [loadError,setLoadError]=useState('');
  useEffect(()=>{if(!serverMode)return;let active=true;setLoadError('');accountApi.dashboard({department:selectedDepartment,start_date:startDate,end_date:endDate}).then(r=>{if(active)setAggregate(r);}).catch(e=>{if(active)setLoadError(e.message);});return()=>{active=false;};},[serverMode,selectedDepartment,startDate,endDate]);
  useEffect(()=>{if(serverMode)accountApi.departments().then(r=>setDepartments(r.items)).catch(e=>setLoadError(e.message));},[serverMode]);
  const departmentOptions = serverMode ? departments.filter(d=>d.is_active).map(d=>d.name) : getDashboardDepartments(orders);
  const dashboardFilters = { department: selectedDepartment, startDate, endDate };
  const dashboardMetrics = (serverMode ? aggregate?.metrics : null) || getDashboardMetrics({ ledgers, orders, ...dashboardFilters });
  const salesRanking = (serverMode ? aggregate?.ranking : null) || getDashboardSalesRanking(orders, selectedDepartment, startDate, endDate);
  const salesRankingTitle = selectedDepartment ? '三级团队销售订单金额排行' : '部门销售订单金额排行';
  const recentLogs = logs.slice(0, 5);
  const trendData = (serverMode ? aggregate?.trends : null) || getDashboardTrendData(orders, dashboardFilters);
  const latestModifiedAt = (serverMode ? aggregate?.latestModifiedAt : null) || getDashboardLatestModifiedAt(orders, dashboardFilters);
  const maxTrendValue = Math.max(...trendData.flatMap((item) => [approximateMoney(item.orderAmount), approximateMoney(item.profit)]), 1);
  const toPoint = (value: MoneyValue, index: number): TrendPoint => ({
    x: trendData.length === 1 ? 300 : (index / (trendData.length - 1)) * 600,
    y: 180 - (Math.max(approximateMoney(value), 0) / maxTrendValue) * 150,
  });
  const orderPoints = trendData.map((item, index) => toPoint(item.orderAmount, index));
  const profitPoints = trendData.map((item, index) => toPoint(item.profit, index));
  const orderPath = smoothPath(orderPoints);
  const profitPath = smoothPath(profitPoints);
  const orderAreaPath = orderPoints.length
    ? `${orderPath} L ${orderPoints[orderPoints.length - 1].x} 200 L ${orderPoints[0].x} 200 Z`
    : '';
  const hoveredTrend = hoveredTrendIndex === null ? null : trendData[hoveredTrendIndex];
  const hoveredPoint = hoveredTrendIndex === null ? null : orderPoints[hoveredTrendIndex];
  const tooltipX = hoveredPoint ? Math.min(Math.max(hoveredPoint.x, 88), 512) : 0;
  const tooltipY = hoveredPoint ? Math.max(hoveredPoint.y - 54, 8) : 0;

  const maxRankingAmount = Math.max(...salesRanking.map((item) => approximateMoney(item.amount)), 1);

  const coreMetrics = [
    {
      label: '销售订单总金额',
      value: compactMoney(dashboardMetrics.totalOrderAmount),
      description: '当前筛选范围内的订单金额',
      icon: BadgeDollarSign,
      iconClass: 'bg-blue-50 text-blue-700',
      accentClass: 'border-t-blue-600',
    },
    {
      label: '毛利润',
      value: compactMoney(dashboardMetrics.grossProfit),
      description: '订单金额－采购金额－税金＋退税',
      icon: TrendingUp,
      iconClass: 'bg-emerald-50 text-emerald-700',
      accentClass: 'border-t-emerald-600',
    },
    {
      label: '订单总数',
      value: `${dashboardMetrics.orderCount.toLocaleString('zh-CN')} 个`,
      description: '按销售订单号去重统计',
      icon: ClipboardList,
      iconClass: 'bg-slate-100 text-slate-700',
      accentClass: 'border-t-slate-500',
    },
  ] as const;

  const fulfillmentMetrics = [
    { label: '交付应收款', value: compactMoney(dashboardMetrics.deliveryAccountsReceivable), description: '已交付但尚未回款', icon: Truck, iconClass: 'bg-sky-50 text-sky-700' },
    { label: '开票应收款', value: compactMoney(dashboardMetrics.invoiceAccountsReceivable), description: '已开票但尚未回款', icon: ReceiptText, iconClass: 'bg-indigo-50 text-indigo-700' },
    { label: '应付账款', value: compactMoney(dashboardMetrics.accountsPayable), description: '采购金额减已付款金额', icon: HandCoins, iconClass: 'bg-amber-50 text-amber-700' },
    { label: '已关闭订单', value: `${dashboardMetrics.closedCount.toLocaleString('zh-CN')} 个`, description: '当前筛选范围内已关闭', icon: CheckCircle2, iconClass: 'bg-emerald-50 text-emerald-700' },
  ] as const;

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 font-sans">仪表盘概览</h1>{loadError&&<p role="alert" className="text-red-700">{loadError}</p>}
          <p className="text-sm text-slate-500 font-sans mt-1">欢迎回来，这是今天的业务实时动态。</p>
        </div>
        <div className="flex flex-wrap items-center gap-3 self-start sm:self-center">
          <label className="flex items-center gap-2 px-3 py-1.5 bg-white border border-slate-200 text-slate-700 rounded-lg shadow-sm text-xs">
            <Filter className="w-4 h-4 text-blue-600" />
            <span className="font-medium text-slate-500">部门</span>
            <select
              value={selectedDepartment}
              onChange={(event) => setSelectedDepartment(event.target.value)}
              className="bg-transparent outline-none text-slate-800 font-medium cursor-pointer min-w-[92px]"
              aria-label="按部门筛选仪表盘指标"
            >
              <option value="">全部部门</option>
              {departmentOptions.map((department) => (
                <option key={department} value={department}>
                  {department}
                </option>
              ))}
            </select>
          </label>
          <div className="flex items-center gap-2 px-3 py-1.5 bg-white border border-slate-200 text-slate-700 rounded-lg shadow-sm text-xs">
            <Calendar className="w-4 h-4 text-slate-400" />
            <span className="font-medium text-slate-500">销售订单日期</span>
            <input
              type="date"
              value={startDate}
              onChange={(event) => setStartDate(event.target.value)}
              max={endDate || undefined}
              className="w-[116px] bg-transparent outline-none text-slate-800 font-medium cursor-pointer"
              aria-label="销售订单日期开始日期"
            />
            <span className="text-slate-400">至</span>
            <input
              type="date"
              value={endDate}
              onChange={(event) => setEndDate(event.target.value)}
              min={startDate || undefined}
              className="w-[116px] bg-transparent outline-none text-slate-800 font-medium cursor-pointer"
              aria-label="销售订单日期结束日期"
            />
          </div>
          <div className="flex items-center gap-2 px-3 py-1.5 bg-white border border-slate-200 text-slate-700 rounded-lg shadow-sm text-xs font-mono" title="当前筛选结果中的数据最新修改时间">
            <Calendar className="w-4 h-4 text-slate-400" />
            <span className="font-sans font-medium text-slate-500">数据最新修改（北京时间）</span>
            <span>{latestModifiedAt || '--'}</span>
          </div>
        </div>
      </div>

      <section className="space-y-3" aria-labelledby="core-metrics-heading">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="core-metrics-heading" className="text-sm font-semibold text-slate-900">核心经营指标</h2>
          <p className="text-xs text-slate-500">按当前部门与销售订单日期统计</p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {coreMetrics.map((metric) => {
            const Icon = metric.icon;
            return (
              <article key={metric.label} className={`rounded-xl border border-t-2 border-slate-200 bg-white p-5 shadow-sm ${metric.accentClass}`}>
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-slate-600">{metric.label}</p>
                    <p className="mt-3 text-3xl font-extrabold tracking-tight text-slate-950 tabular-nums">{metric.value}</p>
                    <p className="mt-2 text-xs text-slate-500">{metric.description}</p>
                  </div>
                  <div className={`shrink-0 rounded-lg p-2.5 ${metric.iconClass}`}>
                    <Icon className="h-5 w-5" />
                  </div>
                </div>
              </article>
            );
          })}
        </div>

        <div className="flex items-center gap-3 pt-2">
          <h3 className="shrink-0 text-xs font-semibold text-slate-600">资金与履约</h3>
          <div className="h-px flex-1 bg-slate-200" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
          {fulfillmentMetrics.map((metric) => {
            const Icon = metric.icon;
            return (
              <article key={metric.label} className="rounded-xl border border-slate-200 bg-slate-50/70 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-xs font-medium text-slate-600">{metric.label}</p>
                    <p className="mt-2 text-2xl font-bold tracking-tight text-slate-950 tabular-nums">{metric.value}</p>
                    <p className="mt-1.5 text-xs text-slate-500">{metric.description}</p>
                  </div>
                  <div className={`shrink-0 rounded-lg p-2 ${metric.iconClass}`}>
                    <Icon className="h-4 w-4" />
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
          <div className="flex justify-between items-center mb-6">
            <h3 className="font-semibold text-slate-900 text-sm">订单与毛利润趋势</h3>
            <div className="flex items-center gap-4 text-xs font-medium text-slate-500">
              <div className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-full bg-blue-600 inline-block" />
                <span>订单金额</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-full bg-slate-500 border-dashed border-2 inline-block border-slate-500" />
                <span>毛利润</span>
              </div>
            </div>
          </div>

          <div className="relative h-64 w-full">
            <div className="absolute inset-0 flex flex-col justify-between pointer-events-none opacity-30 py-4">
              <div className="border-b border-slate-200 w-full" />
              <div className="border-b border-slate-200 w-full" />
              <div className="border-b border-slate-200 w-full" />
              <div className="border-b border-slate-200 w-full" />
            </div>
            {trendData.length > 0 ? (
              <svg className="w-full h-full overflow-visible" preserveAspectRatio="none" viewBox="0 0 600 200">
                <defs>
                  <linearGradient id="blueGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#1167c9" stopOpacity="0.12" />
                    <stop offset="100%" stopColor="#1167c9" stopOpacity="0" />
                  </linearGradient>
                </defs>
                <path d={orderAreaPath} fill="url(#blueGrad)" />
                <path d={orderPath} fill="none" stroke="#1167c9" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                <path
                  d={profitPath}
                  fill="none"
                  stroke="#64748b"
                  strokeWidth="2"
                  strokeDasharray="5 5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                {trendData.map((item, index) => {
                  const orderPoint = orderPoints[index];
                  const profitPoint = profitPoints[index];
                  return (
                    <g key={item.month} onMouseEnter={() => setHoveredTrendIndex(index)} onMouseLeave={() => setHoveredTrendIndex(null)}>
                      <circle cx={orderPoint.x} cy={orderPoint.y} r="11" fill="transparent" />
                      <circle cx={profitPoint.x} cy={profitPoint.y} r="11" fill="transparent" />
                      <circle cx={orderPoint.x} cy={orderPoint.y} r="3.8" fill="#1167c9" stroke="#ffffff" strokeWidth="1.5" />
                      <circle cx={profitPoint.x} cy={profitPoint.y} r="3.4" fill="#64748b" stroke="#ffffff" strokeWidth="1.4" />
                    </g>
                  );
                })}
                {hoveredTrend && (
                  <g pointerEvents="none">
                    <rect x={tooltipX - 86} y={tooltipY} width="172" height="48" rx="6" fill="#0f172a" opacity="0.92" />
                    <text x={tooltipX - 74} y={tooltipY + 17} fill="#ffffff" fontSize="10" fontWeight="600">
                      {hoveredTrend.month}
                    </text>
                    <text x={tooltipX - 74} y={tooltipY + 32} fill="#bfdbfe" fontSize="9">
                      订单金额 {compactMoney(hoveredTrend.orderAmount)}
                    </text>
                    <text x={tooltipX + 8} y={tooltipY + 32} fill="#cbd5e1" fontSize="9">
                      毛利润 {compactMoney(hoveredTrend.profit)}
                    </text>
                  </g>
                )}
              </svg>
            ) : (
              <div className="absolute inset-0 flex items-center justify-center text-sm text-slate-400">暂无符合筛选条件的趋势数据</div>
            )}
          </div>

          <div className="flex justify-between mt-4 text-xs font-mono text-slate-400">
            {trendData.length > 0 && trendData.map((item) => <span key={item.month}>{item.month}</span>)}
          </div>
        </div>

        <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm flex flex-col justify-between">
          <div>
            <h3 className="font-semibold text-slate-900 text-sm mb-5">{salesRankingTitle}</h3>
            <div className="space-y-4">
              {salesRanking.map((item) => (
                <div key={item.label} className="space-y-1.5">
                  <div className="flex justify-between text-xs font-medium gap-3">
                    <span className="text-slate-700 truncate">{item.label}</span>
                    <span className="text-slate-900 font-mono shrink-0">{compactMoney(item.amount)}</span>
                  </div>
                  <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
                    <div
                      className="bg-blue-600 h-full rounded-full transition-all duration-500"
                      style={{ width: `${Math.max((approximateMoney(item.amount) / maxRankingAmount) * 100, 4)}%` }}
                    />
                  </div>
                </div>
              ))}
              {salesRanking.length === 0 && (
                <div className="text-xs text-slate-400 py-4 text-center">
                  {selectedDepartment ? '暂无符合筛选条件的三级团队排行数据' : '暂无符合筛选条件的部门排行数据'}
                </div>
              )}
            </div>
          </div>
          <div className="mt-5 pt-4 border-t border-slate-100 text-center text-xs text-slate-400 font-sans">
            数据来自后端业务台账汇总
          </div>
        </div>
      </div>

      {showLogs && <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        <div className="p-5 border-b border-slate-200 flex justify-between items-center">
          <h3 className="font-semibold text-slate-900 text-sm">操作日志</h3>
          <div className="flex items-center gap-2">
            <button className="p-1.5 hover:bg-slate-50 text-slate-500 rounded-lg border border-slate-200 transition-colors">
              <Filter className="w-4 h-4" />
            </button>
            <button className="p-1.5 hover:bg-slate-50 text-slate-500 rounded-lg border border-slate-200 transition-colors">
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200">
                <th className="px-6 py-3 font-medium text-xs text-slate-500">操作人</th>
                <th className="px-6 py-3 font-medium text-xs text-slate-500">操作模块</th>
                <th className="px-6 py-3 font-medium text-xs text-slate-500">详情</th>
                <th className="px-6 py-3 font-medium text-xs text-slate-500">状态</th>
                <th className="px-6 py-3 font-medium text-xs text-slate-500">操作时间</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {recentLogs.map((log) => (
                <tr key={log.id} className="hover:bg-slate-50 transition-colors group">
                  <td className="px-6 py-3.5 text-sm font-medium text-slate-700">{log.user}</td>
                  <td className="px-6 py-3.5 text-sm text-slate-600">{log.module}</td>
                  <td className="px-6 py-3.5 text-sm text-slate-600 max-w-md truncate">{log.details}</td>
                  <td className="px-6 py-3.5">
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200/50">
                      {log.status}
                    </span>
                  </td>
                  <td className="px-6 py-3.5 text-xs text-slate-400 font-mono">{log.time}</td>
                </tr>
              ))}
              {recentLogs.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-sm text-slate-400">
                    暂无操作日志
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="p-4 bg-slate-50/50 border-t border-slate-100 flex justify-center">
          <button
            onClick={() => onNavigate('logs')}
            className="flex items-center gap-1 text-xs font-semibold text-blue-600 hover:text-blue-700 hover:gap-1.5 transition-all"
          >
            <span>查看全部日志</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>}
    </div>
  );
}
