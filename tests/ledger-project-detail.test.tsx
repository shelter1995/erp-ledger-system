import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { LedgerProjectDetailContent } from '../src/components/LedgerProjectDetail';
import type { LedgerProjectDetail } from '../src/api';

const amounts = {
  order_value: '100.00', purchase_amount: '40.00', gross_profit: '7.00',
  total_received: '20.00', total_paid: '10.00', accounts_receivable: '80.00',
  accounts_payable: '30.00', delivery_value: '60.00', delivery_cost: '25.00',
  sales_invoice_amount: '50.00', total_finance_checked: '15.00',
  delivery_accounts_receivable: '40.00', invoice_accounts_receivable: '30.00',
};
const detail: LedgerProjectDetail = {
  ...amounts, project_code: 'P-1', project_name: '测试项目', department: '测试部门',
  account_manager: '测试经理', customer_unit_name: '测试客户', order_count: 2,
  order_date: '2026-09-30', orders: ['SO-1', 'SO-2'].map(order_no => ({
    ...amounts, order_no, order_date: '2026-09-30', status: 'open',
    department: '测试部门', account_manager: '测试经理', customer_unit_name: '测试客户',
  })),
};
const html = renderToStaticMarkup(<LedgerProjectDetailContent detail={detail}/>);
for (const label of ['项目信息', '测试项目', '测试客户', '测试部门', '测试经理', '订单数量', '最近销售订单日期', '毛利润', '应付账款', '已收账款']) {
  assert.ok(html.includes(label), `Missing ${label}`);
}
assert.ok(html.indexOf('项目信息') < html.indexOf('销售信息'));
assert.ok(html.indexOf('销售信息') < html.indexOf('采购信息'));
const sales = html.slice(html.indexOf('销售信息'), html.indexOf('采购信息'));
const purchases = html.slice(html.indexOf('采购信息'));
for (const section of [sales, purchases]) {
  for (const order of ['SO-1', 'SO-2', '2026-09-30']) assert.ok(section.includes(order));
}
assert.ok(sales.includes('A销售订单金额') && sales.includes('E发票金额'));
assert.ok(!sales.includes('D付款金额'));
assert.ok(purchases.includes('A采购金额') && purchases.includes('E收票金额'));
assert.ok(!purchases.includes('D回款金额'));
assert.ok(html.includes('>7.00<'), 'Use the current server gross profit instead of order minus purchase');
console.log('Ledger project detail rendering passed');
