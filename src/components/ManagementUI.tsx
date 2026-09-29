import React, { useEffect, useRef } from 'react';
import { ChevronLeft, ChevronRight, X } from 'lucide-react';

export function Modal({title,children,onClose,busy=false,wide=false}:{title:string;children:React.ReactNode;onClose:()=>void;busy?:boolean;wide?:boolean}) {
  const ref=useRef<HTMLDialogElement>(null);
  useEffect(()=>{const dialog=ref.current;dialog?.showModal();return()=>dialog?.close();},[]);
  return <dialog ref={ref} onCancel={e=>{e.preventDefault();if(!busy)onClose();}} className={`erp-ui m-auto w-[calc(100%-2rem)] ${wide?'max-w-4xl':'max-w-xl'} max-h-[90vh] rounded-xl border border-slate-200 bg-white p-0 text-slate-800 shadow-xl backdrop:bg-slate-900/45`} aria-label={title}>
    <header className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-200 bg-white px-6 py-4"><h2 className="text-lg font-semibold">{title}</h2><button type="button" disabled={busy} onClick={onClose} className="ui-button !p-1.5" aria-label="关闭弹窗"><X className="h-4 w-4"/></button></header>
    <div className="p-6">{children}</div>
  </dialog>;
}

export function PageSizeSelect({value,onChange}:{value:number;onChange:(value:number)=>void}) {
  return <label className="flex shrink-0 items-center gap-2 text-xs text-slate-500">每页<select aria-label="每页条数" className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs text-slate-700 outline-none focus:border-blue-500" value={value} onChange={e=>onChange(Number(e.target.value))}>{[5,10,20,50].map(n=><option key={n} value={n}>{n}</option>)}</select>条</label>;
}

export function Pagination({page,size,total,onPage,onSize,busy=false}:{page:number;size:number;total:number;onPage:(p:number)=>void;onSize:(s:number)=>void;busy?:boolean}) {
  const pages=Math.max(1,Math.ceil(total/size));
  return <div className="flex flex-wrap items-center justify-between gap-4 border-t border-slate-200 bg-slate-50 px-5 py-4 text-xs text-slate-500">
    <span>显示 {total?Math.min(page*size+1,total):0} 到 {Math.min((page+1)*size,total)} 条，共 {total} 条记录</span>
    <div className="flex flex-wrap items-center gap-3"><PageSizeSelect value={size} onChange={s=>{onSize(s);onPage(0);}}/><button type="button" className="ui-button !p-1.5" aria-label="上一页" disabled={busy||page===0} onClick={()=>onPage(page-1)}><ChevronLeft className="h-4 w-4"/></button><span>第 {page+1} / {pages} 页</span><button type="button" className="ui-button !p-1.5" aria-label="下一页" disabled={busy||page+1>=pages} onClick={()=>onPage(page+1)}><ChevronRight className="h-4 w-4"/></button></div>
  </div>;
}

export function PageHeading({title,description,children}:{title:string;description:string;children?:React.ReactNode}) {
  return <header className="flex flex-wrap items-center justify-between gap-4"><div><h1 className="text-2xl font-bold tracking-tight text-slate-900">{title}</h1><p className="mt-1 text-sm text-slate-500">{description}</p></div>{children}</header>;
}
