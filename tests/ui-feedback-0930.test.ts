import assert from 'node:assert/strict';
import test from 'node:test';
import { applyOrderFilters, emptyOrderFilters } from '../src/lib/queryFilterModel';
import { loadAllPages } from '../src/lib/loadAllPages';
import type { OrderRecord } from '../src/types';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import OrdersScreen from '../src/components/OrdersScreen';
import SalesScreen from '../src/components/SalesScreen';
import PurchasesScreen from '../src/components/PurchasesScreen';
import DateInput from '../src/components/DateInput';
import { formatQuantity } from '../src/lib/quantity';
import SummaryLedgerScreen from '../src/components/SummaryLedgerScreen';
import { applyPurchaseFilters, emptyPurchaseFilters } from '../src/lib/queryFilterModel';

test('basic manager history is opt-in and composes with department/date range', () => {
  const rows = [{ projectId: 'A', manager: '李四', managerHistory: ['张三', '李四'], department: '市场部', orderDate: '2026-09-30' }] as OrderRecord[];
  const filters = { ...emptyOrderFilters, manager: '张三', department: '市场部', startDate: '2026-09-01', endDate: '2026-09-30' };
  assert.equal(applyOrderFilters(rows, filters).length, 0);
  assert.equal(applyOrderFilters(rows, { ...filters, includeHistoryManager: 'true' }).length, 1);
  assert.equal(applyOrderFilters(rows, { ...filters, includeHistoryManager: 'true', endDate: '2026-09-29' }).length, 0);
});

test('four screens share manager filter, placeholders and correct date labels', () => {
  const entries: Array<[React.ComponentType<any>, Record<string, unknown>]> = [
    [OrdersScreen, { orders: [] }], [SalesScreen, { sales: [], orders: [] }],
    [PurchasesScreen, { purchases: [], orders: [] }],
    [SummaryLedgerScreen, { user: { roleCode: 'viewer', permissions: [] }, onNavigate() {} }],
  ];
  for (const [Screen, props] of entries) {
    const html = renderToStaticMarkup(React.createElement(Screen, props));
    assert.match(html, /包含历史负责人/);
    assert.match(html, /placeholder="输入项目经理姓名"/);
    assert.match(html, /placeholder="输入采购厂商名称"/);
    assert.doesNotMatch(html, /请输入客户经理姓名/);
    if (Screen === OrdersScreen) assert.equal((html.match(/type="date"/g) || []).length, 2);
    if (Screen === PurchasesScreen) { assert.match(html, /付款时间范围/); assert.doesNotMatch(html, /回款时间/); }
  }
});

test('purchase date range uses payment phases, not receipt dates', () => {
  const rows = [{ projectId: 'A', orderId: 'A', manager: '', department: '', supplier: '', contractNo: '', contractAmount: 0, invoiceAmount: 0, paymentAmount: 30,
    paymentPhases: [{ date: '2026-08-01', amount: 10 }, { date: '2026-09-30', amount: 20 }] }];
  const result = applyPurchaseFilters(rows, { ...emptyPurchaseFilters, paymentStartDate: '2026-09-01', paymentEndDate: '2026-09-30' });
  assert.equal(result.length, 1);
  assert.equal(result[0].paymentAmount, '20.00');
});

test('basic information combines department and manager filters', () => {
  const rows = [
    { projectId: 'A', manager: '张三', department: '市场部' },
    { projectId: 'B', manager: '李四', department: '市场部' },
    { projectId: 'C', manager: '张三', department: '采购部' },
  ] as OrderRecord[];
  assert.deepEqual(applyOrderFilters(rows, { ...emptyOrderFilters, manager: '张', department: '市场部' }).map(r => r.projectId), ['A']);
  assert.equal(applyOrderFilters(rows, emptyOrderFilters).length, 3);
});

test('first page is published before later pages finish, and snapshots do not mutate', async () => {
  const snapshots: number[][] = [];
  await loadAllPages(async ({ offset }) => {
    if (offset) assert.deepEqual(snapshots, [[1]]);
    return { total: 2, items: [offset + 1] };
  }, page => snapshots.push(page.items));
  assert.deepEqual(snapshots, [[1], [1, 2]]);
});

test('page failure preserves the published first page and reports the failure', async () => {
  const snapshots: number[][] = [];
  await assert.rejects(loadAllPages(async ({ offset }) => {
    if (offset) throw new Error('下一页失败');
    return { total: 2, items: [1] };
  }, page => snapshots.push(page.items)), /下一页失败/);
  assert.deepEqual(snapshots, [[1]]);
});

test('cancelled navigation does not publish old data or fetch subsequent pages', async () => {
  let current = true;
  let calls = 0;
  await loadAllPages(async () => {
    calls += 1;
    current = false;
    return { total: 2, items: [1] };
  }, () => assert.fail('stale page must not be published'), () => current);
  assert.equal(calls, 1);
});

test('quantity display rounds to two decimals without changing the raw input', () => {
  for (const [raw, displayed] of [['1.234567 台', '1.23 台'], ['2.999999', '3.00'], ['0', '0.00'], ['-1.235', '-1.24'], ['9007199254740993.125', '9007199254740993.13']]) {
    assert.equal(formatQuantity(raw), displayed);
  }
  assert.equal(formatQuantity(null), '');
  assert.equal(formatQuantity('-'), '-');
});

test('date placeholder is Chinese and selected dates retain ISO form values', () => {
  const empty = renderToStaticMarkup(React.createElement(DateInput, { value: '', onChange() {} }));
  assert.match(empty, /年 \/ 月 \/ 日/);
  assert.match(empty, /type="date"/);
  const selected = renderToStaticMarkup(React.createElement(DateInput, { value: '2026-09-30', onChange() {} }));
  assert.match(selected, /value="2026-09-30"/);
  assert.doesNotMatch(selected, /年 \/ 月 \/ 日/);
});

test('all three screens distinguish loading, error, and genuine empty results', () => {
  const entries: Array<[React.ComponentType<any>, Record<string, unknown>]> = [
    [OrdersScreen, { orders: [] }], [SalesScreen, { sales: [], orders: [] }], [PurchasesScreen, { purchases: [], orders: [] }],
  ];
  for (const [Screen, props] of entries) {
    const loading = renderToStaticMarkup(React.createElement(Screen, { ...props, loading: true }));
    assert.match(loading, /正在加载/);
    assert.doesNotMatch(loading, /暂无符合条件/);
    const failed = renderToStaticMarkup(React.createElement(Screen, { ...props, loadError: true }));
    assert.match(failed, /清单加载失败/);
    assert.doesNotMatch(failed, /暂无符合条件/);
  }
});
