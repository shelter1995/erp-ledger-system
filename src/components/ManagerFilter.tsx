import React, { useId } from 'react';

export default function ManagerFilter({ value, includeHistory, onChange, onHistoryChange }: {
  value: string;
  includeHistory: string;
  onChange: (value: string) => void;
  onHistoryChange: (value: string) => void;
}) {
  const id = useId();
  return <div className="space-y-1.5">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <label htmlFor={id} className="text-xs font-medium text-slate-500">客户经理</label>
      <label className="flex items-center gap-2 text-xs text-slate-500">
        <input type="checkbox" checked={includeHistory === 'true'} onChange={e => onHistoryChange(e.target.checked ? 'true' : '')} />
        包含历史负责人
      </label>
    </div>
    <input id={id} type="text" placeholder="输入客户经理姓名" value={value} onChange={e => onChange(e.target.value)}
      className="block w-full px-3 py-2 border border-slate-200 rounded-lg focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none text-xs text-slate-700" />
  </div>;
}
