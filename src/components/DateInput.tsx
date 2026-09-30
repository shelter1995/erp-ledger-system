import React from 'react';

/** A Chinese empty hint independent of the browser's native date locale. */
export default function DateInput({ className = '', value, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  const empty = !value;
  return <span className="relative inline-grid w-full min-w-0">
    <input {...props} type="date" lang="zh-CN" value={value}
      className={`${className} ${empty ? 'date-input-empty' : ''}`} />
    {empty && <span aria-hidden="true" className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-xs text-slate-400">年 / 月 / 日</span>}
  </span>;
}
