import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import PurchasesScreen from '../src/components/PurchasesScreen';
import SalesScreen from '../src/components/SalesScreen';

test('sales screen renders its empty state without parsing blank draft amounts', () => {
  const markup = renderToStaticMarkup(React.createElement(SalesScreen, {
    sales: [],
    orders: [],
    canEnterSales: true,
    canEditSales: true,
    canDeleteSales: true,
  }));

  assert.match(markup, /暂无符合条件的销售记录/);
});

test('purchases screen renders its empty state without parsing blank draft amounts', () => {
  const markup = renderToStaticMarkup(React.createElement(PurchasesScreen, {
    purchases: [],
    orders: [],
    canEnterPurchases: true,
    canEditPurchases: true,
    canDeletePurchases: true,
  }));

  assert.match(markup, /暂无符合条件的采购记录/);
});
