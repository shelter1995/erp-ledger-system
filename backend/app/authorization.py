"""Explicit, fail-closed authorization. No database or role-name fallback."""
from fastapi import HTTPException

READ_PERMISSIONS = {'dashboard_view', 'ledger_view', 'order_view', 'sales_view', 'purchase_view'}
WRITE_PERMISSIONS = {f'{module}_{action}' for module in ('order', 'sales', 'purchase') for action in ('entry', 'edit', 'delete')}
MANAGEMENT_PERMISSIONS = {
    'department_transfer', 'maintenance_view', 'ledger_import', 'data_replace',
    'accounts_view', 'accounts_create', 'accounts_update', 'accounts_disable',
    'logs_view', 'backups_view', 'backups_create', 'backups_verify', 'backups_restore',
}
PERMISSIONS = READ_PERMISSIONS | WRITE_PERMISSIONS | MANAGEMENT_PERMISSIONS
ACCOUNT_TYPES = {'department_user', 'ledger_admin', 'super_admin'}
RESTRICTED_GRANTS = {'accounts_view', 'accounts_create', 'accounts_update', 'accounts_disable',
                     'data_replace', 'backups_restore', 'department_transfer'}


def validate_policy(account_type, scope_mode, department_ids, permissions, log_scope, home_department_id=None):
    if account_type not in ACCOUNT_TYPES or scope_mode not in {'none', 'selected', 'all'} or log_scope not in {'self', 'department', 'all'}:
        raise HTTPException(422, '无效的账号类型或权限范围')
    if set(permissions) - PERMISSIONS:
        raise HTTPException(422, '包含未知权限')
    if (scope_mode == 'selected') != bool(department_ids):
        raise HTTPException(422, '指定部门范围必须非空，其他范围不能包含部门')
    if account_type == 'department_user' and home_department_id is None:
        raise HTTPException(422, '部门账号必须设置所属部门')
    if account_type == 'super_admin' and scope_mode != 'all':
        raise HTTPException(422, '超级管理员必须使用全部门范围')
    for module in ('order', 'sales', 'purchase'):
        if any(f'{module}_{action}' in permissions for action in ('entry', 'edit', 'delete')) and f'{module}_view' not in permissions:
            raise HTTPException(422, '业务操作必须同时具有对应模块查看权限')
    for action, view in [('ledger_import', 'maintenance_view'), ('data_replace', 'maintenance_view'),
                         *[(f'accounts_{a}', 'accounts_view') for a in ('create', 'update', 'disable')],
                         *[(f'backups_{a}', 'backups_view') for a in ('create', 'verify', 'restore')]]:
        if action in permissions and view not in permissions:
            raise HTTPException(422, '操作权限必须同时具有所属页面查看权限')
    if {'data_replace', 'backups_restore'} & set(permissions) and scope_mode != 'all':
        raise HTTPException(422, '全局替换和恢复要求明确授权全部门')


def scope_contains(actor_mode, actor_ids, target_mode, target_ids):
    if actor_mode == 'all' or target_mode == 'none':
        return True
    return actor_mode == target_mode == 'selected' and set(target_ids) <= set(actor_ids)


def can_manage(actor, target):
    if actor.account_type == 'super_admin':
        return True
    if target.get('id') == actor.id or target['account_type'] == 'super_admin':
        return False
    target_permissions = set(target['permissions'])
    return (not target_permissions & RESTRICTED_GRANTS
            and target_permissions <= set(actor.permissions)
            and scope_contains(actor.scope_mode, actor.department_ids, target['scope_mode'], target['department_ids'])
            and {'self': 0, 'department': 1, 'all': 2}[target['log_scope']] <= {'self': 0, 'department': 1, 'all': 2}[actor.log_scope])


def route_permissions(path, method):
    """Additional read/module guards. Mutations retain their granular route dependency."""
    if path in {'/api/auth/me', '/api/auth/change-password', '/api/auth/logout', '/api/auth/roles'} or path.startswith('/api/departments'):
        return set()
    if path.startswith('/api/auth/users'):
        return {'accounts_view'}
    if path.startswith('/api/dashboard'):
        return {'dashboard_view'}
    if path.startswith('/api/ledgers'):
        return {'ledger_view'}
    if path in {'/api/orders/export', '/api/history/export'}:
        return {'order_view', 'sales_view', 'purchase_view'}
    if path.startswith('/api/orders/import') or path == '/api/orders/source-import' or path.startswith('/api/import-batches'):
        return {'maintenance_view', 'ledger_import'}
    if path.startswith('/api/import/'):
        return {'maintenance_view', 'data_replace'}
    if path in {'/api/history/transfer-project', '/api/history/transfer-order'}:
        return {'order_view', 'order_edit', 'department_transfer'}
    if path.startswith('/api/orders') or path.startswith('/api/history'):
        return {'order_view'}
    if path.startswith('/api/purchases'):
        return {'purchase_view'}
    if path.startswith('/api/sales'):
        return {'sales_view'}
    if path.startswith('/api/logs'):
        return {'logs_view'}
    if path.startswith('/api/backups'):
        return {'backups_view'}
    return set()
