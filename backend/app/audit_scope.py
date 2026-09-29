import json
from sqlalchemy import text


def event_scope(conn, user, module, detail):
    names = set()
    unknown = False
    def collect(value):
        nonlocal unknown
        if isinstance(value, dict):
            if 'department' in value:
                if value['department']:
                    names.add(value['department'])
                else:
                    unknown = True
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)
    collect(detail)
    ids = set()
    for name in names:
        department_id = conn.execute(text('SELECT department_id FROM department_alias WHERE name=:n'), {'n': name}).scalar()
        if department_id is None:
            unknown = True
        else:
            ids.add(department_id)
    kind = 'security' if module == '账号安全' else ('business' if module in {'订单管理', '采购管理', '销售管理', '基本信息', '采购信息', '销售信息'} else 'system')
    return {'actor_department_id': user.home_department_id, 'department_ids_json': json.dumps(sorted(ids)),
            'event_kind': kind, 'scope_known': int(kind == 'security' or (bool(ids) and not unknown))}


def log_filter(user):
    if user.account_type == 'super_admin' or user.log_scope == 'all':
        return '1=1', {}
    base = "scope_known=1 AND event_kind='business' AND JSON_LENGTH(department_ids_json)=1"
    if user.log_scope == 'self':
        return f"user_id=:actor AND (({base}) OR (scope_known=1 AND event_kind='security'))", {'actor': user.id}
    if not user.department_ids and user.scope_mode != 'all':
        return '1=0', {}
    if user.scope_mode == 'all':
        return base, {}
    params = {f'd{i}': json.dumps(d) for i, d in enumerate(user.department_ids)}
    predicate = ' OR '.join(f'JSON_CONTAINS(department_ids_json, :d{i})' for i in range(len(user.department_ids)))
    return f'{base} AND ({predicate})', params
