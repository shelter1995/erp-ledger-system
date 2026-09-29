import { Plus, Upload, ShieldCheck, RotateCcw, Eye } from 'lucide-react';
import { Modal, PageHeading, Pagination } from './ManagementUI';
import { formatDatabaseUtcTime } from '../lib/dateTime';
import React, { useEffect, useState } from 'react';
import { api, accountApi, BackendOperationLog, BackendBackupInfo } from '../api';
import { AuthUser, hasPermission } from '../lib/permissions';
import { formatOperationLogSummary, formatOperationLogChangeGroups } from '../lib/operationLogDisplay';
import SourceLedgerImport from './SourceLedgerImport';
import ImportBatchHistory from './ImportBatchHistory';
import MaintenanceImport from './MaintenanceImport';

export function MaintenanceScreen({user}:{user:AuthUser}) {
  const [open,setOpen]=useState(false);const [revision,setRevision]=useState(0);
  return <div className="erp-ui space-y-6"><PageHeading title="数据维护与台账批量导入" description="导入台账、查看导入记录及维护业务数据。"/>
    {hasPermission(user,'ledger_import')&&<><section className="ui-card p-5 space-y-3"><h2 className="text-sm font-semibold">台账批量导入</h2><p className="text-sm text-slate-600">仅可导入授权部门的数据，确认前请核对预览结果。</p><button onClick={()=>setOpen(true)} className="ui-primary"><Upload className="h-4 w-4"/>选择台账并预检</button></section><div key={revision} className="ui-card p-5"><h2 className="mb-4 text-sm font-semibold">导入记录</h2><ImportBatchHistory onImported={async()=>{setRevision(v=>v+1);}} onBusy={()=>{}}/></div></>}
    {hasPermission(user,'data_replace')&&<MaintenanceImport onRefresh={()=>setRevision(v=>v+1)}/>}
    {!hasPermission(user,'ledger_import')&&!hasPermission(user,'data_replace')&&<p className="ui-card p-6 text-sm text-slate-500">尚未授予导入或维护操作权限。</p>}
    {open&&<SourceLedgerImport onClose={()=>setOpen(false)} onImported={async()=>{setRevision(v=>v+1);}}/>}
  </div>;
}

export function LogsScreen() {
  const [departmentNames,setDepartmentNames]=useState<Record<number,string>>({});
  useEffect(()=>{let active=true;accountApi.departments().then(r=>{if(active)setDepartmentNames(Object.fromEntries(r.items.map(d=>[d.id,d.name])));}).catch(()=>{});return()=>{active=false;};},[]);
  const [items,setItems]=useState<BackendOperationLog[]>([]);const [error,setError]=useState('');const [page,setPage]=useState(0);const [size,setSize]=useState(20);const [selected,setSelected]=useState<BackendOperationLog|null>(null);const [total,setTotal]=useState(0);
  useEffect(()=>{let active=true;setError('');accountApi.logs(page*size,size).then(r=>{if(active){setItems(r.items);setTotal(r.total);}}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[page,size]);
  return <div className="erp-ui space-y-6"><PageHeading title="操作日志" description="查看授权范围内的操作记录，点击详情核对具体变更。"/>{error&&<p role="alert" className="text-sm text-red-600">{error}</p>}<section className="ui-card"><div className="overflow-x-auto"><table className="ui-table min-w-[720px]"><thead><tr>{['时间','操作人','模块','操作内容','结果','操作'].map(x=><th key={x}>{x}</th>)}</tr></thead><tbody>{items.map(item=><tr key={item.id}><td className="whitespace-nowrap">{formatDatabaseUtcTime(item.created_at)}</td><td className="min-w-32 max-w-44 break-words">{item.user_name}</td><td className="whitespace-nowrap">{item.module_name}</td><td className="min-w-52 max-w-sm"><p className="line-clamp-2 leading-5">{formatOperationLogSummary(item)}</p></td><td><span className={`whitespace-nowrap rounded-full px-2 py-1 ${item.status==='success'?'bg-emerald-50 text-emerald-700':'bg-red-50 text-red-600'}`}>{item.status==='success'?'成功':'失败'}</span></td><td><button className="ui-button" onClick={()=>setSelected(item)}><Eye className="h-3.5 w-3.5"/>详情</button></td></tr>)}</tbody></table>{!items.length&&<p className="p-8 text-center text-sm text-slate-500">暂无可查看的日志</p>}</div><Pagination page={page} size={size} total={total} onPage={setPage} onSize={setSize}/></section>
    {selected&&<Modal wide title="操作详情" onClose={()=>setSelected(null)}><div className="space-y-5 text-sm"><dl className="grid grid-cols-2 gap-4 rounded-lg bg-slate-50 p-4"><div><dt className="text-xs text-slate-500">操作人</dt><dd className="mt-1">{selected.user_name}</dd></div><div><dt className="text-xs text-slate-500">操作时间</dt><dd className="mt-1">{formatDatabaseUtcTime(selected.created_at)}</dd></div></dl><p className="font-medium">{formatOperationLogSummary(selected)}</p>{formatOperationLogChangeGroups(selected,departmentNames).map((group,index)=><section key={index} className="rounded-lg border border-slate-200"><h3 className="border-b border-slate-200 bg-slate-50 px-4 py-3 text-xs font-semibold">{group.title}</h3><ul className="divide-y divide-slate-100">{group.changes.map((change,i)=><li className="px-4 py-3 leading-6 break-words" key={i}>{change}</li>)}</ul></section>)}{!formatOperationLogChangeGroups(selected,departmentNames).length&&<p className="text-xs text-slate-500">此操作未记录字段差异，请参阅操作内容。</p>}</div></Modal>}
  </div>;
}

export function BackupsScreen({user}:{user:AuthUser}) {
  const [page,setPage]=useState(0);const [size,setSize]=useState(20);const [total,setTotal]=useState(0);
  const [items,setItems]=useState<BackendBackupInfo[]>([]);const [message,setMessage]=useState('');const [busy,setBusy]=useState(false);
  async function load(){const result=await accountApi.backups(page*size,size);setItems(result.items);setTotal(result.total);}
  useEffect(()=>{let active=true;accountApi.backups(page*size,size).then(result=>{if(active){setItems(result.items);setTotal(result.total);}}).catch(e=>{if(active)setMessage(e.message);});return()=>{active=false;};},[page,size]);
  async function run(fn:()=>Promise<unknown>){if(busy)return;setBusy(true);setMessage('');try{await fn();await load();}catch(e){setMessage(e instanceof Error?e.message:'操作失败');}finally{setBusy(false);}}
  return <div className="erp-ui space-y-6"><PageHeading title="数据备份与恢复" description="管理全局业务备份，校验备份文件并恢复业务数据。">{hasPermission(user,'backups_create')&&<button disabled={busy} className="ui-primary" onClick={()=>void run(async()=>{await api.createBackup();setMessage('备份已创建');})}><Plus className="h-4 w-4"/>创建备份</button>}</PageHeading><p className="rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-xs leading-5 text-blue-800">业务备份不包含账号和日志。恢复会替换全部业务数据，系统先创建恢复前备份。</p>{message&&<p role="status" className="p-3 bg-amber-50 rounded-lg text-sm">{message}</p>}<section className="ui-card"><div className="overflow-x-auto"><table className="ui-table"><thead><tr>{['文件名','大小','时间','操作'].map(x=><th key={x}>{x}</th>)}</tr></thead><tbody>{items.map(item=><tr key={item.id}><td>{item.file_name}</td><td className="whitespace-nowrap">{item.file_size_label}</td><td className="whitespace-nowrap">{formatDatabaseUtcTime(item.backup_time)}</td><td><div className="flex gap-2">{hasPermission(user,'backups_verify')&&<button className="ui-button" disabled={busy} onClick={()=>void run(async()=>setMessage((await api.verifyBackup(item.id)).message))}><ShieldCheck className="h-3.5 w-3.5"/>校验</button>}{hasPermission(user,'backups_restore')&&<button disabled={busy} className="ui-danger" onClick={()=>{if(window.confirm(`确认使用 ${item.file_name} 替换全部业务数据？`))void run(async()=>{await api.restoreBackup(item.id);setMessage('恢复完成，请重新打开业务页面');});}}><RotateCcw className="h-3.5 w-3.5"/>恢复</button>}</div></td></tr>)}</tbody></table>{!items.length&&<p className="p-8 text-center text-sm text-slate-500">暂无业务备份</p>}</div><Pagination page={page} size={size} total={total} onPage={setPage} onSize={setSize} busy={busy}/></section></div>;
}
