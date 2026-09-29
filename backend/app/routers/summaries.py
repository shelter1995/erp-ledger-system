"""Read-only aggregate DTOs: no contracts, invoices, line IDs or editable records."""
from collections import defaultdict
from decimal import Decimal
from io import BytesIO
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from openpyxl import Workbook
from ..department_service import department_filter
from sqlalchemy import text
from ..auth import CurrentUser, get_current_user, apply_department_scope
from ..db import db
from ..validation import BusinessDate
from ..ledger_excel import content_disposition
from ..history_queries import order_match, manager_match

router = APIRouter(tags=['summaries'])
AMOUNTS = ('order_value', 'purchase_amount', 'gross_profit', 'total_received', 'total_paid', 'accounts_receivable',
           'delivery_accounts_receivable', 'invoice_accounts_receivable', 'accounts_payable', 'delivery_value', 'delivery_cost', 'sales_invoice_amount', 'gross_profit_no_tax', 'labor_cost', 'other_cost', 'total_finance_paid', 'financial_accounts_payable', 'total_finance_checked')


@router.get('/api/sales/order-options')
@router.get('/api/purchases/order-options')
def order_options(user: CurrentUser = Depends(get_current_user)):
    from ..serializers import clean_rows
    conditions, params = ['1=1'], {}
    apply_department_scope(conditions, params, user, 'f.department')
    columns='order_line_id,project_code,project_name,order_no,department,account_manager,goods_name,quantity,unit_name,order_value,customer_unit_name'
    with db() as conn:
        rows=conn.execute(text('SELECT '+','.join('f.'+c for c in columns.split(','))+',p.id AS project_id,p.version AS project_version FROM v_order_line_finance f JOIN project p ON p.project_code=f.project_code WHERE '+' AND '.join(conditions)),params).mappings().all()
        epoch=conn.execute(text('SELECT data_epoch FROM business_state WHERE id=1')).scalar_one()
        items=clean_rows(rows)
        for row in items:
            version=row.pop('project_version')
            row['edit_context']={'data_epoch':int(epoch),'projects':{str(row['project_id']):int(version)}}
        return {'items':items}



def read_summary(conn, user, filters):
    conditions, params = ['1=1'], {}
    apply_department_scope(conditions, params, user, 'f.department')
    for key, column in [('project_id','project_code'), ('order_id','order_no'), ('manager','account_manager'), ('client_unit','customer_unit_name'), ('supplier_name','supplier_name')]:
        if filters.get(key):
            params[key] = '%' + filters[key] + '%'
            conditions.append(order_match('f.order_line_id') if key == 'order_id' else manager_match('f.project_code') if key == 'manager' and filters.get('include_history_manager') else f'f.{column} LIKE :{key}')
    if filters.get('department'):
        params['department'] = filters['department']
        conditions.append(department_filter('f.department'))
    for key, op in [('start_date','>='), ('end_date','<=')]:
        if filters.get(key):
            params[key] = filters[key]
            conditions.append(f'f.order_date {op} :{key}')
    invoices = []
    for key, op in [('invoice_start_date','>='), ('invoice_end_date','<=')]:
        if filters.get(key):
            params[key] = filters[key]
            invoices.append(f'si.invoice_date {op} :{key}')
    if invoices:
        conditions.append('EXISTS (SELECT 1 FROM sales_invoice si WHERE si.order_line_id=f.order_line_id AND si.deleted_at IS NULL AND ' + ' AND '.join(invoices) + ')')
    columns = ','.join(f'f.{c}' for c in AMOUNTS)
    rows = conn.execute(text(f'SELECT f.project_code,f.project_name,f.order_no,f.department,f.account_manager,f.customer_unit_name,f.team_level3_name,f.order_date,f.close_status,f.last_modified_at,{columns} FROM v_order_line_finance f WHERE {" AND ".join(conditions)}'), params).mappings().all()
    orders = defaultdict(list)
    for row in rows:
        orders[(row['project_code'], row['order_no'])].append(row)
    closed = {key: all(str(r['close_status']).lower() in {'closed','已关闭','关闭','已闭合','已结案'} or Decimal(r['accounts_receivable'] or 0) == 0 for r in values) for key, values in orders.items()}
    status = filters.get('order_status')
    if status:
        rows = [r for r in rows if closed[(r['project_code'], r['order_no'])] == (status == 'closed')]
        orders = {k:v for k,v in orders.items() if closed[k] == (status == 'closed')}
    def total(items, field):
        return format(sum((Decimal(r[field] or 0) for r in items), Decimal(0)), '.2f')
    metrics = {key: total(rows, col) for key, col in [('totalOrderAmount','order_value'),('grossProfit','gross_profit'),('accountsReceivable','accounts_receivable'),('deliveryAccountsReceivable','delivery_accounts_receivable'),('invoiceAccountsReceivable','invoice_accounts_receivable'),('accountsPayable','accounts_payable')]}
    metrics.update(orderCount=len(orders), closedCount=sum(closed[k] for k in orders))
    projects, months, ranking = defaultdict(list), defaultdict(list), defaultdict(list)
    for r in rows:
        projects[r['project_code']].append(r)
        if r['order_date']:
            months[str(r['order_date'])[:7]].append(r)
        ranking[(r['team_level3_name'] or '未登记三级团队') if filters.get('department') else (r['department'] or '未登记部门')].append(r)
    orders_by_project = defaultdict(list)
    for (project_code, order_no), order_group in orders.items():
        orders_by_project[project_code].append((order_no, order_group))
    items = []
    for code, group in projects.items():
        item = {c: total(group,c) for c in AMOUNTS}
        item.update(project_code=code, order_count=len({r['order_no'] for r in group}))
        for field in ('project_name','department','account_manager','customer_unit_name'):
            item[field] = '；'.join(sorted({str(r[field]) for r in group if r[field]}))
        item['orders'] = []
        for order_no, order_group in orders_by_project[code]:
            order_item = {c:total(order_group,c) for c in AMOUNTS}
            order_item.update(order_no=order_no, status='closed' if closed[(code,order_no)] else 'open')
            for field in ('department','account_manager','customer_unit_name'):
                order_item[field]='；'.join(sorted({str(r[field]) for r in order_group if r[field]}))
            item['orders'].append(order_item)
        item['orders'].sort(key=lambda r:r['order_no'])
        items.append(item)
    return {'items': sorted(items, key=lambda r:r['project_code']), 'metrics': metrics,
            'trends': [{'month': month, 'orderAmount': total(group,'order_value'), 'profit': total(group,'gross_profit')} for month, group in sorted(months.items())],
            'ranking': sorted([{'label': label, 'amount': total(group,'order_value')} for label, group in ranking.items() if Decimal(total(group,'order_value')) > 0], key=lambda r:(-Decimal(r['amount']), r['label']))[:5],
            'latestModifiedAt': max((str(r['last_modified_at']) for r in rows if r['last_modified_at']), default='')}


def summary_filters(project_id: str = '', order_id: str = '', department: str = '', manager: str = '', client_unit: str = '',
                    supplier_name: str = '', include_history_manager: bool = False, order_status: str = Query('', pattern='^(|open|closed)$'),
                    start_date: BusinessDate | None = None, end_date: BusinessDate | None = None,
                    invoice_start_date: BusinessDate | None = None, invoice_end_date: BusinessDate | None = None):
    for start, end in [(start_date,end_date), (invoice_start_date,invoice_end_date)]:
        if start and end and start > end:
            raise HTTPException(422, '开始日期不能晚于结束日期')
    return dict(include_history_manager=include_history_manager,project_id=project_id,order_id=order_id,department=department,manager=manager,client_unit=client_unit,supplier_name=supplier_name,order_status=order_status,
                start_date=start_date,end_date=end_date,invoice_start_date=invoice_start_date,invoice_end_date=invoice_end_date)


@router.get('/api/dashboard/data')
def dashboard_data(filters: dict = Depends(summary_filters), user: CurrentUser = Depends(get_current_user)):
    with db() as conn:
        data = read_summary(conn, user, filters)
    return {k:v for k,v in data.items() if k != 'items'}


@router.get('/api/ledgers/summary')
def ledger_summary(filters: dict = Depends(summary_filters), user: CurrentUser = Depends(get_current_user)):
    with db() as conn:
        return read_summary(conn, user, filters)


@router.get('/api/ledgers/export-summary')
def export_summary(filters: dict = Depends(summary_filters), user: CurrentUser = Depends(get_current_user)):
    with db() as conn:
        items = read_summary(conn, user, filters)['items']
    columns = [('project_code','框架编号'),('project_name','项目名称'),('department','部门'),('account_manager','客户经理'),('customer_unit_name','客户单位'),('order_count','订单数'),
               ('order_value','订单金额'),('purchase_amount','采购金额'),('gross_profit','毛利润'),('total_received','回款合计'),('total_paid','付款合计'),('accounts_receivable','应收'),('accounts_payable','应付')]
    wb = Workbook(); ws = wb.active; ws.title = '台账汇总'
    ws.append([label for key,label in columns])
    for row in items:
        ws.append([str(row[key]) for key,label in columns])
        for cell in ws[ws.max_row]:
            cell.data_type = 's'
    ws.freeze_panes='A2'; ws.auto_filter.ref=ws.dimensions
    output=BytesIO(); wb.save(output); wb.close()
    return Response(output.getvalue(),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':content_disposition('台账汇总.xlsx')})
