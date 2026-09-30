import React, { createContext, useContext, useState } from 'react';
import { currentOrderYear, orderYearOptions } from '../lib/orderYear';

const OrderYearContext = createContext({
  year: currentOrderYear(), years: [currentOrderYear()],
  setYear: (_year: string) => {}, setYears: (_years: number[]) => {},
});

export function OrderYearProvider({ children }: { children: React.ReactNode }) {
  const [year, setYear] = useState(currentOrderYear);
  const [available, setAvailable] = useState<number[]>([]);
  return <OrderYearContext.Provider value={{ year, setYear, years: orderYearOptions(available), setYears: setAvailable }}>
    {children}
  </OrderYearContext.Provider>;
}

export function useOrderYear() { return useContext(OrderYearContext); }

export default function OrderYearFilter() {
  const { year, years, setYear } = useOrderYear();
  return <label className="block min-w-0 space-y-1.5 text-xs font-medium text-slate-500">
    <span>订单年度</span>
    <select aria-label="订单年度" title="按销售订单日期归属年度；与回款、付款日期分别筛选"
      className="block w-full min-w-0 px-3 py-2 border border-slate-200 rounded-lg bg-white text-xs text-slate-700 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
      value={year} onChange={e => setYear(e.target.value)}>
      {[...new Set([...years, ...(year ? [year] : [])])].sort((a,b) => Number(b)-Number(a)).map(value =>
        <option key={value} value={value}>{value} 年{value === currentOrderYear() ? '（本年）' : ''}</option>)}
      <option value="">全部年份</option>
    </select>
  </label>;
}
