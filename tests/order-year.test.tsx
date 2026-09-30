import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {currentOrderYear,orderYearOptions,orderYearParams} from '../src/lib/orderYear';
import OrderYearFilter,{OrderYearProvider} from '../src/components/OrderYearFilter';
import {loadAllPages} from '../src/lib/loadAllPages';
test('Beijing year boundary and historical/all scopes',()=>{
 assert.equal(currentOrderYear(new Date('2026-12-31T15:59:59Z')),'2026');
 assert.equal(currentOrderYear(new Date('2026-12-31T16:00:00Z')),'2027');
 assert.deepEqual(orderYearOptions([2024,2025,2024],'2026'),['2026','2025','2024']);
 assert.deepEqual(orderYearParams(''),{});
 assert.deepEqual(orderYearParams('2024'),{order_year:'2024'});
 const html=renderToStaticMarkup(<OrderYearProvider><OrderYearFilter/></OrderYearProvider>);
 assert.ok(html.includes('订单年度')&&html.includes('全部年份')&&html.includes('selected'));
});
test('discard a late page after changing the annual scope',async()=>{
 let active=true;let release:(value:{items:number[];total:number})=>void=()=>{};let displayed:number[]=[];
 const pending=loadAllPages(()=>new Promise(resolve=>{release=resolve}),page=>{displayed=page.items},()=>active);
 active=false;release({items:[2024],total:1});await pending;
 assert.deepEqual(displayed,[]);
});
