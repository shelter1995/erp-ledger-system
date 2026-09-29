"""Additive schema preparation and explicitly reviewed account migration.

Preparing schema never maps existing accounts or grants permissions.
"""
import hashlib
import json
from sqlalchemy import text
from .authorization import PERMISSIONS, READ_PERMISSIONS, WRITE_PERMISSIONS, validate_policy

USER_COLUMNS = {
    'avatar_data': 'MEDIUMTEXT NULL',
    'account_type': "VARCHAR(32) NOT NULL DEFAULT 'department_user'",
    'home_department_id': 'BIGINT UNSIGNED NULL',
    'scope_mode': "VARCHAR(16) NOT NULL DEFAULT 'none'",
    'log_scope': "VARCHAR(16) NOT NULL DEFAULT 'self'",
    'must_change_password': 'TINYINT NOT NULL DEFAULT 0',
    'auth_version': 'BIGINT NOT NULL DEFAULT 1',
    'authorization_version': 'INT NOT NULL DEFAULT 0',
}
AUDIT_COLUMNS = {
    'actor_department_id': 'BIGINT UNSIGNED NULL',
    'department_ids_json': 'JSON NULL',
    'event_kind': "VARCHAR(16) NOT NULL DEFAULT 'unknown'",
    'scope_known': 'TINYINT NOT NULL DEFAULT 0',
}


def prepare_schema(conn):
    for table, definitions in [('erp_user', USER_COLUMNS), ('operation_log', AUDIT_COLUMNS)]:
        columns = set(conn.execute(text('SELECT COLUMN_NAME FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=:t'), {'t': table}).scalars())
        for name, definition in definitions.items():
            if name not in columns:
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {definition}'))
    for sql in [
        "CREATE TABLE IF NOT EXISTS department (id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT, name VARCHAR(64) NOT NULL UNIQUE, is_active TINYINT NOT NULL DEFAULT 1)",
        "CREATE TABLE IF NOT EXISTS department_alias (name VARCHAR(64) PRIMARY KEY, department_id BIGINT UNSIGNED NOT NULL, FOREIGN KEY (department_id) REFERENCES department(id))",
        "CREATE TABLE IF NOT EXISTS user_department (user_id BIGINT UNSIGNED NOT NULL, department_id BIGINT UNSIGNED NOT NULL, PRIMARY KEY(user_id,department_id), FOREIGN KEY(user_id) REFERENCES erp_user(id) ON DELETE CASCADE, FOREIGN KEY(department_id) REFERENCES department(id))",
        "CREATE TABLE IF NOT EXISTS authorization_lock (id INT PRIMARY KEY)",
        "INSERT IGNORE INTO authorization_lock (id) VALUES (1)",
    ]:
        conn.execute(text(sql))


def lock_authorization(conn):
    # Every account mutation and business write uses the same ordering: gate -> actor.
    conn.execute(text('SELECT id FROM authorization_lock WHERE id=1 FOR UPDATE')).one()


def _json(value):
    if isinstance(value, list):
        return value
    return json.loads(value) if value else []


def account_inventory(conn):
    rows = [dict(r) for r in conn.execute(text('SELECT id,username,display_name,role_code,permissions_json,department_scope_json,department_can_view,department_can_entry,is_active FROM erp_user ORDER BY id')).mappings()]
    names = set()
    for r in rows:
        names.update(str(x).strip() for x in _json(r['department_scope_json']) if str(x).strip())
    for table, column in [('project', 'department'), ('order_line', 'line_department')]:
        names.update(str(x).strip() for x in conn.execute(text(f'SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL')).scalars() if str(x).strip())
    snapshot = {'accounts': rows, 'departments': sorted(names)}
    digest = hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    candidates = []
    legacy_defaults = {'admin': {'system_admin', 'ledger_import', 'order_entry', 'order_edit', 'order_delete', 'sales_entry', 'sales_edit', 'sales_delete', 'purchase_entry', 'purchase_edit', 'purchase_delete'}, 'viewer': set()}
    for row in rows:
        old = set(_json(row['permissions_json'])) if row['permissions_json'] is not None else legacy_defaults.get(row['role_code'], {row['role_code']})
        scope = _json(row['department_scope_json'])
        p = (old & PERMISSIONS) | (READ_PERMISSIONS if not scope or row['department_can_view'] or 'system_admin' in old else set())
        if scope and not row['department_can_entry'] and 'system_admin' not in old:
            p -= WRITE_PERMISSIONS | {'ledger_import'}
        if 'ledger_import' in p:
            p.add('maintenance_view')
        is_admin = 'system_admin' in old
        candidates.append({**row, 'reviewed': False, 'candidate': {
            'account_type': 'super_admin' if is_admin else ('department_user' if scope else 'ledger_admin'),
            'scope_mode': 'all' if is_admin or not scope else 'selected',
            'departments': scope, 'home_department': scope[0] if scope else None,
            'permissions': sorted(PERMISSIONS if is_admin else p), 'log_scope': 'all' if is_admin else 'self',
        }, 'review_reason': '确认超级管理员身份及全部权限' if is_admin else ('空部门旧账号：必须确认是否全部门' if not scope else '确认部门、读取和写入范围')})
    return {'format': 1, 'source_digest': digest, 'departments': sorted(names),
            'department_mapping': {name:name for name in sorted(names)}, 'accounts': candidates}


def apply_mapping(conn, report):
    lock_authorization(conn)
    if conn.execute(text("SELECT 1 FROM schema_migration WHERE migration_key='20260929_authorization_v2'")).scalar():
        raise ValueError('新权限映射已执行；禁止覆盖之后的人工授权修改')
    if conn.execute(text('SELECT COUNT(*) FROM erp_user WHERE authorization_version>0')).scalar():
        raise ValueError('已有新权限账号，禁止通过旧账号映射覆盖现有授权')
    inventory = account_inventory(conn)
    if inventory['source_digest'] != report.get('source_digest'):
        raise ValueError('账号或部门已变化，请重新生成核对清单')
    expected = {r['id'] for r in inventory['accounts']}
    mappings = report.get('accounts', [])
    if {r['id'] for r in mappings} != expected or len(mappings) != len(expected) or not all(r.get('reviewed') is True for r in mappings):
        raise ValueError('必须逐一核对全部账号，不能遗漏或重复')
    active_ids = {r['id'] for r in inventory['accounts'] if r['is_active']}
    if not any(r['id'] in active_ids and r['candidate']['account_type'] == 'super_admin' for r in mappings):
        raise ValueError('至少需要一个有效超级管理员')
    # Department creation is explicit and transaction-bound; no business rows change.
    department_mapping = report.get('department_mapping', {})
    if set(department_mapping) != set(inventory['departments']) or any(not isinstance(n,str) or not n.strip() or len(n)>64 for n in department_mapping.values()):
        raise ValueError('必须为全部历史部门名称提供有效的规范名称映射')
    for canonical in sorted(set(department_mapping.values())):
        if not conn.execute(text('SELECT id FROM department WHERE name=:n'), {'n': canonical}).scalar():
            conn.execute(text('INSERT INTO department(name) VALUES (:n)'), {'n': canonical})
    for name in inventory['departments']:
        existing = conn.execute(text('SELECT department_id FROM department_alias WHERE name=:n'), {'n': name}).scalar()
        department_id = conn.execute(text('SELECT id FROM department WHERE name=:n'), {'n': department_mapping[name]}).scalar_one()
        if existing is not None and existing != department_id:
            raise ValueError('历史部门名称已有不同映射，禁止覆盖')
        if existing is None:
            conn.execute(text('INSERT INTO department_alias(name,department_id) VALUES(:n,:id)'), {'n': name, 'id': department_id})
    for canonical in sorted(set(department_mapping.values())):
        conn.execute(text('INSERT IGNORE INTO department_alias(name,department_id) SELECT name,id FROM department WHERE name=:n'), {'n':canonical})
    directory = dict(conn.execute(text('SELECT name,department_id FROM department_alias')).all())
    for r in mappings:
        p = r['candidate']
        try:
            ids = sorted({directory[n] for n in p['departments']}) if p['scope_mode'] == 'selected' else []
            home = directory[p['home_department']] if p.get('home_department') else None
        except KeyError as exc:
            raise ValueError('映射包含未登记部门') from exc
        validate_policy(p['account_type'], p['scope_mode'], ids, p['permissions'], p['log_scope'], home)
        conn.execute(text('UPDATE erp_user SET account_type=:kind,role_code=:kind,scope_mode=:scope,home_department_id=:home,log_scope=:logs,permissions_json=:permissions,authorization_version=1,auth_version=auth_version+1 WHERE id=:id'),
                     {'kind': p['account_type'], 'scope': p['scope_mode'], 'home': home, 'logs': p['log_scope'], 'permissions': json.dumps(p['permissions']), 'id': r['id']})
        conn.execute(text('DELETE FROM user_department WHERE user_id=:id'), {'id': r['id']})
        for department_id in ids:
            conn.execute(text('INSERT INTO user_department VALUES(:u,:d)'), {'u': r['id'], 'd': department_id})
    conn.execute(text("INSERT INTO schema_migration(migration_key) VALUES('20260929_authorization_v2')"))
