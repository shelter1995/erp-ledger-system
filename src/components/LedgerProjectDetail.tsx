import { useOrderYear } from './OrderYearFilter';
import { orderYearParams } from '../lib/orderYear';
import React, { useEffect, useState } from 'react';
import { ChevronRight } from 'lucide-react';
import { accountApi, LedgerProjectDetail as ProjectDetail, LedgerMaterialLine } from '../api';
import { formatMoney } from '../lib/money';
import { formatQuantity } from '../lib/quantity';
import { Modal } from './ManagementUI';

const salesColumns = [
  ['order_value', 'A销售订单金额'], ['delivery_value', 'B交付收入'],
  ['total_received', 'D回款金额'], ['sales_invoice_amount', 'E发票金额'],
  ['delivery_accounts_receivable', '交付应收款'], ['invoice_accounts_receivable', '开票应收款'],
] as const;
const purchaseColumns = [
  ['purchase_amount', 'A采购金额'], ['delivery_cost', 'B交付成本'],
  ['total_paid', 'D付款金额'], ['total_finance_checked', 'E收票金额'],
] as const;

function OrderTable({ title, orders, columns }: {
  title: string;
  orders: ProjectDetail['orders'];
  columns: readonly (readonly [keyof Pick<LedgerMaterialLine, 'order_value' | 'purchase_amount' | 'delivery_value' | 'delivery_cost' | 'total_received' | 'total_paid' | 'sales_invoice_amount' | 'total_finance_checked' | 'delivery_accounts_receivable' | 'invoice_accounts_receivable'>, string])[];
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const toggle = (orderNo: string) => setExpanded(previous => {
    const next = new Set(previous);
    if (next.has(orderNo)) next.delete(orderNo); else next.add(orderNo);
    return next;
  });
  return <section>
    <h3 className="mb-3 text-sm font-bold text-slate-900">{title}</h3>
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="ui-table whitespace-nowrap">
        <thead><tr><th>订单号</th><th>销售订单日期</th>{columns.map(([key, label]) => <th key={key} className="text-right">{label}</th>)}</tr></thead>
        <tbody>{orders.map(order => <React.Fragment key={order.order_no}>
          <tr>
            <td className="font-mono text-blue-600">{order.lines ? <button
              type="button" className="inline-flex items-center gap-2 rounded px-1 py-1 hover:bg-blue-50 focus-visible:outline focus-visible:outline-blue-500"
              aria-expanded={expanded.has(order.order_no)}
              aria-label={`${expanded.has(order.order_no) ? '收起' : '展开'}${title}订单 ${order.order_no} 的物资/服务条目`}
              onClick={() => toggle(order.order_no)}>
              <ChevronRight className={`h-3.5 w-3.5 transition-transform ${expanded.has(order.order_no) ? 'rotate-90' : ''}`}/>{order.order_no}
            </button> : order.order_no}</td><td>{order.order_date || '-'}</td>
            {columns.map(([key]) => <td key={key} className="text-right font-mono">{formatMoney(order[key])}</td>)}
          </tr>
          {order.lines && expanded.has(order.order_no) && <tr>
            <td colSpan={2 + columns.length} className="bg-slate-50 p-3">
              <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
                <table className="ui-table whitespace-nowrap" aria-label={`${title}订单 ${order.order_no} 的物资/服务条目`}>
                  <thead><tr><th>物资/服务名称</th><th>规格型号</th><th>数量</th><th>采购厂商</th>
                    {columns.map(([key, label]) => <th key={key} className="text-right">{label}</th>)}
                  </tr></thead>
                  <tbody>{order.lines.length ? order.lines.map((line, index) => <tr key={index}>
                    <td className="!whitespace-normal min-w-40">{line.goods_name || '-'}</td>
                    <td>{line.specification_model || '-'}</td>
                    <td>{line.quantity === '' ? '-' : `${formatQuantity(line.quantity)} ${line.unit_name}`.trim()}</td>
                    <td>{line.supplier_name || '-'}</td>
                    {columns.map(([key]) => <td key={key} className="text-right font-mono">{formatMoney(line[key])}</td>)}
                  </tr>) : <tr><td colSpan={4 + columns.length} className="text-center text-slate-500">暂无物资/服务条目</td></tr>}</tbody>
                </table>
              </div>
            </td>
          </tr>}
        </React.Fragment>)}</tbody>
      </table>
    </div>
    {orders.some(order => !order.lines) && <p className="mt-2 text-xs text-slate-500">查看物资/服务条目需要基本信息查看权限。</p>}
  </section>;
}

export function LedgerProjectDetailContent({ detail }: { detail: ProjectDetail }) {
  const fields = [
    ['客户单位名称', detail.customer_unit_name], ['负责部门', detail.department],
    ['客户经理', detail.account_manager],
    ['订单状态', detail.orders.every(order => order.status === 'closed') ? '已关闭' : '进行中'],
    ['订单数量', String(detail.order_count)], ['最近销售订单日期', detail.order_date],
    ['销售订单金额', `${formatMoney(detail.order_value)}`], ['毛利润', `${formatMoney(detail.gross_profit)}`],
  ];
  const finance = [
    ['应付账款', detail.accounts_payable], ['已付账款', detail.total_paid],
    ['交付应收款', detail.delivery_accounts_receivable], ['开票应收款', detail.invoice_accounts_receivable],
    ['已收账款', detail.total_received],
  ];
  return <div className="space-y-5">
    <p className="text-base font-semibold text-slate-900 break-words">{detail.project_name || '-'}</p>
    <section>
      <h3 className="mb-3 text-sm font-bold text-slate-900">项目信息</h3>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">{fields.map(([label, value]) =>
        <div key={label} className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
          <p className="text-xs text-slate-500">{label}</p><p className="mt-1 text-xs font-semibold break-words">{value || '-'}</p>
        </div>)}</div>
      <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">{finance.map(([label, value]) =>
        <div key={label} className="rounded-lg border border-slate-200 px-3 py-2">
          <p className="text-xs text-slate-500">{label}</p><p className="mt-1 text-xs font-bold font-mono">{formatMoney(value)}</p>
        </div>)}</div>
    </section>
    <OrderTable title="销售信息" orders={detail.orders} columns={salesColumns}/>
    <OrderTable title="采购信息" orders={detail.orders} columns={purchaseColumns}/>
  </div>;
}

export default function LedgerProjectDetail({ projectCode, onClose }: { projectCode: string; onClose: () => void }) {
  const {year}=useOrderYear();
  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    setDetail(null); setError('');
    accountApi.projectDetail(projectCode,orderYearParams(year)).then(result => {
      if (active) setDetail(result);
    }).catch(error => {
      if (active) setError(error instanceof Error ? error.message : '项目详情加载失败');
    });
    return () => { active = false; };
  }, [projectCode,year]);
  return <Modal wide title={`${projectCode} · 项目详情`} onClose={onClose}>
    {error ? <p role="alert" className="text-sm text-red-600">{error}</p>
      : detail ? <LedgerProjectDetailContent detail={detail}/>
      : <p role="status" className="text-sm text-slate-500">正在加载所选年度的项目订单…</p>}
  </Modal>;
}
