"""Account persistence and authorization transaction boundary."""
import json
from fastapi import HTTPException
from sqlalchemy import text, bindparam
from .authorization import PERMISSIONS, can_manage, validate_policy
from .authorization_migration import lock_authorization


def revalidate_write(conn):
    from .edit_versions import request_context
    request = request_context.get(None)
    if request is None or request.method not in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        return
    actor = getattr(request.state, 'current_user', None)
    if actor is None:
        return
    lock_authorization(conn)
    row = conn.execute(text('SELECT is_active,auth_version FROM erp_user WHERE id=:id FOR UPDATE'), {'id': actor.id}).mappings().first()
    if not row or not row['is_active'] or row['auth_version'] != actor.auth_version:
        raise HTTPException(401, '登录或权限已变更，请重新登录')


def public_account(conn, row):
    fields = ('id','username','display_name','account_type','home_department_id','scope_mode','log_scope','is_active','must_change_password','last_login_at','created_at','updated_at','authorization_version')
    result = {key: row[key] for key in fields}
    from .auth import parse_json_list
    result['permissions'] = sorted(PERMISSIONS) if row['account_type'] == 'super_admin' else parse_json_list(row['permissions_json'])
    result['department_ids'] = list(conn.execute(text('SELECT department_id FROM user_department WHERE user_id=:id'), {'id': row['id']}).scalars())
    return result


def check_manage(actor, target):
    if not can_manage(actor, target):
        raise HTTPException(403, '不能管理此账号或授予超出自身范围的权限')


def validate_departments(conn, policy):
    validate_policy(policy.account_type, policy.scope_mode, policy.department_ids, policy.permissions, policy.log_scope, policy.home_department_id)
    ids = set(policy.department_ids)
    if policy.home_department_id is not None:
        ids.add(policy.home_department_id)
    if ids:
        active = set(conn.execute(text('SELECT id FROM department WHERE is_active=1 AND id IN :ids').bindparams(bindparam('ids', expanding=True)), {'ids': sorted(ids)}).scalars())
        if active != ids:
            raise HTTPException(422, '部门不存在或已停用')


def save_policy(conn, user_id, policy):
    conn.execute(text('UPDATE erp_user SET account_type=:kind,role_code=:kind,home_department_id=:home,scope_mode=:scope,log_scope=:logs,permissions_json=:permissions,authorization_version=1,auth_version=auth_version+1,updated_at=NOW() WHERE id=:id'),
        {'kind': policy.account_type, 'home': policy.home_department_id, 'scope': policy.scope_mode, 'logs': policy.log_scope, 'permissions': json.dumps(sorted(set(policy.permissions))), 'id': user_id})
    conn.execute(text('DELETE FROM user_department WHERE user_id=:id'), {'id': user_id})
    for dept in set(policy.department_ids):
        conn.execute(text('INSERT INTO user_department(user_id,department_id) VALUES(:u,:d)'), {'u': user_id, 'd': dept})


def ensure_super_admin_remains(conn, target_id):
    count = conn.execute(text("SELECT COUNT(*) FROM erp_user WHERE id<>:id AND is_active=1 AND account_type='super_admin' AND authorization_version=1"), {'id': target_id}).scalar()
    if not count:
        raise HTTPException(409, '至少保留一个有效超级管理员')
