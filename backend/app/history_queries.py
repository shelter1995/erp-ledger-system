"""History predicates never multiply financial rows; enrichment is page-scoped."""
from collections import defaultdict
from sqlalchemy import text, bindparam
from .serializers import clean_rows
from .edit_versions import read_context
from .order_ownership import decode_history


def order_match(column="order_line_id", *, project=False):
    select = "hp.project_code" if project else "hl.id"
    return f"""{column} IN (
      SELECT {select} FROM sales_order hs
      JOIN project hp ON hp.id=hs.project_id
      JOIN order_line hl ON hl.sales_order_id=hs.id AND hl.deleted_at IS NULL
      WHERE hs.deleted_at IS NULL AND hp.deleted_at IS NULL
      AND (hs.order_no LIKE :order_id OR EXISTS (
        SELECT 1 FROM sales_order_number_history hn
        WHERE hn.sales_order_id=hs.id AND hn.order_no LIKE :order_id)))"""


def manager_match(column="order_line_id"):
    # Aggregation prevents semijoin flattening into the large finance export:
    # MySQL otherwise explores an excessive number of join orders.
    return f"""{column} IN (SELECT hl.id FROM order_line hl
      JOIN sales_order hs ON hs.id=hl.sales_order_id
      JOIN project hp ON hp.id=hs.project_id
      WHERE hl.deleted_at IS NULL AND hs.deleted_at IS NULL AND hp.deleted_at IS NULL
      AND (CASE WHEN hs.ownership_overridden=1 THEN
        (hs.account_manager LIKE :manager OR JSON_SEARCH(hs.manager_history, 'one', :manager, NULL, '$[*].manager_name') IS NOT NULL)
      WHEN hl.source_preserved=1 THEN hl.line_account_manager LIKE :manager
      ELSE (hp.account_manager LIKE :manager OR EXISTS (
        SELECT 1 FROM project_manager_history hm WHERE hm.project_id=hp.id AND hm.manager_name LIKE :manager)) END)
      GROUP BY hl.id HAVING COUNT(*) > 0)"""


def enrich_history(conn, rows):
    items = clean_rows(rows)
    if not items:
        return items
    codes = list({r['project_code'] for r in items})
    projects = conn.execute(text('SELECT id, project_code FROM project WHERE project_code IN :codes')
                            .bindparams(bindparam('codes', expanding=True)), {'codes': codes}).mappings().all()
    ids = [r['id'] for r in projects]
    managers = defaultdict(list)
    for r in conn.execute(text('SELECT * FROM project_manager_history WHERE project_id IN :ids ORDER BY history_order')
                          .bindparams(bindparam('ids', expanding=True)), {'ids': ids}).mappings():
        managers[r['project_id']].append(r['manager_name'])
    by_code = {r['project_code']: r['id'] for r in projects}
    line_ids = [r['order_line_id'] for r in items if r.get('order_line_id')]
    source_lines = set()
    numbers, line_orders = defaultdict(list), {}
    if line_ids:
        for r in conn.execute(text('SELECT id, sales_order_id, source_preserved FROM order_line WHERE id IN :ids')
                              .bindparams(bindparam('ids', expanding=True)), {'ids': line_ids}).mappings():
            line_orders[r['id']] = r['sales_order_id']
            if r['source_preserved']:
                source_lines.add(r['id'])
        for r in conn.execute(text('SELECT sales_order_id, order_no FROM sales_order_number_history WHERE sales_order_id IN :ids ORDER BY history_order')
                              .bindparams(bindparam('ids', expanding=True)), {'ids': list(set(line_orders.values()))}).mappings():
            numbers[r['sales_order_id']].append(r['order_no'])
    order_managers = {}
    if line_orders:
        for order in conn.execute(text('SELECT id, manager_history FROM sales_order WHERE ownership_overridden=1 AND id IN :ids')
                                  .bindparams(bindparam('ids', expanding=True)), {'ids':list(set(line_orders.values()))}).mappings():
            order_managers[order['id']] = [h['manager_name'] for h in decode_history(order['manager_history'])]
    paths = source_order_paths(conn, line_ids)
    version_context=read_context(conn,ids)
    for r in items:
        r['edit_context']={'data_epoch':version_context['data_epoch'],'projects':{str(by_code[r['project_code']]):version_context['projects'][str(by_code[r['project_code']])]}}
        r['project_id'] = by_code[r['project_code']]
        r['manager_history'] = managers[r['project_id']] or ([r['account_manager']] if r.get('account_manager') else [])
        if r.get('order_line_id'):
            r['sales_order_id'] = line_orders[r['order_line_id']]
            r['order_number_history'] = numbers[r['sales_order_id']] or [r['order_no']]
            if r['order_line_id'] in paths:
                r['order_number_path'] = paths[r['order_line_id']]
            if r['order_line_id'] in source_lines:
                r['manager_history'] = [r['account_manager']] if r.get('account_manager') else []
            if r['sales_order_id'] in order_managers:
                r['manager_history'] = order_managers[r['sales_order_id']]
    return items


def source_order_paths(conn, line_ids):
    from .source_import import source_order_chain
    paths = {}
    for start in range(0,len(line_ids),1000):
        rows = conn.execute(text('''SELECT ol.id,
            JSON_UNQUOTE(JSON_EXTRACT(r.raw_json,'$.values[12]')) AS original_number
            FROM order_line ol JOIN ledger_raw_row r ON r.id=ol.raw_row_id
            WHERE ol.source_preserved=1 AND ol.id IN :ids''').bindparams(bindparam('ids',expanding=True)),
            {'ids':line_ids[start:start+1000]}).mappings()
        for row in rows:
            if row['original_number'] not in (None, '', 'null'):
                paths[row['id']] = source_order_chain(row['original_number'],0)
    return paths


def enrich_phases(conn, items, table, date_column, amount_column, key):
    if not items:
        return items
    groups = defaultdict(list)
    ids = [r['order_line_id'] for r in items]
    # Names are constants chosen by our list routes, never request input.
    rows = conn.execute(text(f'SELECT order_line_id, {date_column} AS date, {amount_column} AS amount FROM {table} WHERE deleted_at IS NULL AND order_line_id IN :ids ORDER BY phase_no, id')
                        .bindparams(bindparam('ids', expanding=True)), {'ids': ids}).mappings().all()
    for r in clean_rows(rows):
        groups[r['order_line_id']].append({'date': r['date'], 'amount': r['amount']})
    for r in items:
        r[key] = groups[r['order_line_id']]
    return items


def delivery_records(conn, line_ids):
    if not line_ids:
        return []
    rows = conn.execute(text('''SELECT dr.id,dr.order_line_id,ol.goods_name,
        dr.delivery_date,dr.delivery_quantity,dr.delivery_value,dr.delivery_revenue_no_tax
        FROM delivery_record dr JOIN order_line ol ON ol.id=dr.order_line_id
        WHERE dr.order_line_id IN :ids AND dr.deleted_at IS NULL
        ORDER BY dr.order_line_id,dr.id''').bindparams(bindparam('ids', expanding=True)),
        {'ids':list(line_ids)}).mappings().all()
    return clean_rows(rows)
