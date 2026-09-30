"""Order ownership overrides never change source evidence or sibling orders."""
import json
from sqlalchemy import text, bindparam
from .serializers import clean_rows

FIELDS = ('account_manager', 'department', 'branch_company', 'team_level3_name')


def decode_history(value):
    return json.loads(value) if isinstance(value, str) else (value or [])


def manager_histories(conn, rows):
    if not rows:
        return {}
    order_ids = list({r['sales_order_id'] for r in rows})
    project_ids = list({r['project_id'] for r in rows})
    orders = {r['id']: r for r in conn.execute(text('SELECT id, ownership_overridden, manager_history '
              'FROM sales_order WHERE id IN :ids').bindparams(bindparam('ids', expanding=True)),
              {'ids': order_ids}).mappings()}
    projects = {}
    for entry in clean_rows(conn.execute(text('SELECT project_id, manager_name, history_order, effective_from, source '
                          'FROM project_manager_history WHERE project_id IN :ids ORDER BY history_order')
                          .bindparams(bindparam('ids', expanding=True)), {'ids': project_ids}).mappings().all()):
        project_id = entry.pop('project_id')
        projects.setdefault(project_id, []).append(entry)
    result = {}
    for row in rows:
        order = orders[row['sales_order_id']]
        if order['ownership_overridden']:
            history = decode_history(order['manager_history'])
        elif row['source_preserved']:
            history = [{'manager_name': row['account_manager'], 'history_order': 1,
                        'effective_from': None, 'source': '原表明细归属（未推断交接）'}]
        else:
            history = list(projects.get(row['project_id'], []))
        result[row['order_line_id']] = history
    return result


def manager_history(conn, row):
    return manager_histories(conn, [row])[row['order_line_id']]


def save_order_ownership(conn, row, values, effective_from, reason, managers):
    history = manager_history(conn, row)
    # Imported orders may contain several original managers. Record the observed
    # values without inventing a chronological relationship between them.
    for name in managers:
        if name and not any(h['manager_name'] == name for h in history):
            history.append({'manager_name': name, 'history_order': len(history) + 1,
                            'effective_from': None, 'source': '交接前归属快照'})
    if not history or any(name != values['account_manager'] for name in managers):
        history.append({'manager_name': values['account_manager'], 'history_order': len(history) + 1,
                        'effective_from': str(effective_from) if effective_from else None,
                        'source': 'manual_change', 'reason': reason})
    conn.execute(text('UPDATE sales_order SET ownership_overridden=1, account_manager=:account_manager, '
                      'department=:department, branch_company=:branch_company, team_level3_name=:team_level3_name, '
                      'manager_history=:history WHERE id=:id'),
                 {'id': row['sales_order_id'], **values, 'history': json.dumps(history, ensure_ascii=False)})
