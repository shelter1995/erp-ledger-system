import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import DashboardScreen from '../src/components/DashboardScreen';
import LedgerScreen from '../src/components/LedgerScreen';
import OrdersScreen from '../src/components/OrdersScreen';

test('ledger transfer actions render familiar upload and download icons', () => {
  const ordersMarkup = renderToStaticMarkup(React.createElement(OrdersScreen, {
    orders: [],
    onAddOrder: async () => undefined,
    onImportExcel: async () => ({ batch_id: 0, source_sha256: '', success_rows: 0, skipped_rows: 0 }),
    onUpdateOrder: async () => undefined,
    onDeleteOrder: async () => undefined,
    onBatchSaved: async () => undefined,
    canEnterOrders: true,
    canEditOrders: true,
    canDeleteOrders: true,
    canImportLedger: true,
  }));
  const ledgerMarkup = renderToStaticMarkup(React.createElement(LedgerScreen, {
    ledgers: [],
    orders: [],
    purchases: [],
    sales: [],
    onAddLedger: () => undefined,
    onDownloadTemplate: async () => new Blob(),
    onExportExcel: async () => new Blob(),
  }));

  assert.match(ordersMarkup, /aria-label="基本信息页面操作"/);
  assert.match(ordersMarkup, /lucide-upload/);
  assert.match(ledgerMarkup, /lucide-download/);
});

test('dashboard separates core metrics from cash and fulfillment metrics', () => {
  const markup = renderToStaticMarkup(React.createElement(DashboardScreen, {
    logs: [],
    ledgers: [],
    orders: [],
    onNavigate: () => undefined,
  }));

  assert.match(markup, /核心经营指标/);
  assert.match(markup, /资金与履约/);
  assert.match(markup, /lucide-badge-dollar-sign/);
  assert.match(markup, /lucide-truck/);
  assert.match(markup, /lucide-receipt-text/);
  assert.match(markup, /lucide-hand-coins/);
});
