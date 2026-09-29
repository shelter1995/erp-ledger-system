"""Versioned account API; old auth router is not mounted."""
import base64
import binascii
import struct
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import text, bindparam
from ..auth import (CurrentUser, get_current_user, require_permission, hash_password, verify_password,
                    create_access_token, current_user_payload, user_from_row, ROLE_LABELS)
from ..authorization import PERMISSIONS, can_manage
from ..authorization_migration import lock_authorization
from ..account_service import public_account, check_manage, validate_departments, save_policy, ensure_super_admin_remains
from ..db import db
from ..audit import write_operation_log
from ..serializers import clean_rows

router = APIRouter(prefix='/api/auth', tags=['auth'])


class LoginRequest(BaseModel):
    username: str
    password: str


class UserPermissionUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    account_type: Literal['department_user', 'ledger_admin', 'super_admin']
    home_department_id: int | None = None
    scope_mode: Literal['none', 'selected', 'all']
    department_ids: list[int] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    log_scope: Literal['self', 'department', 'all'] = 'self'


class UserCreate(UserPermissionUpdate):
    username: str = Field(min_length=2, max_length=64, pattern=r'^[A-Za-z0-9_.-]+$')
    display_name: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=12, max_length=128)


class UserPasswordReset(BaseModel):
    password: str = Field(min_length=12, max_length=128)


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(min_length=12, max_length=128)
    confirm_password: str


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    display_name: str = Field(min_length=1, max_length=64)
    avatar_data: str | None = Field(default=None, max_length=180000)


@router.put('/profile')
def update_profile(payload: ProfileUpdate, user: CurrentUser = Depends(get_current_user)):
    name = payload.display_name.strip()
    if not name:
        raise HTTPException(422, '显示名称不能为空')
    avatar = payload.avatar_data
    if avatar:
        try:
            if not avatar.startswith('data:image/png;base64,'):
                raise ValueError()
            raw = base64.b64decode(avatar.split(',', 1)[1], validate=True)
            if len(raw) > 128 * 1024 or len(raw) < 45 or raw[:8] != b'\x89PNG\r\n\x1a\n' or raw[12:16] != b'IHDR' or raw[-8:] != b'IEND\xaeB`\x82':
                raise ValueError()
            width, height = struct.unpack('>II', raw[16:24])
            if not (1 <= width <= 512 and 1 <= height <= 512):
                raise ValueError()
        except (ValueError, binascii.Error, struct.error):
            raise HTTPException(422, '头像须为不超过 128 KB、512×512 像素的 PNG 图片') from None
    with db() as conn:
        before = {'display_name': user.display_name, 'avatar_changed': False}
        conn.execute(text('UPDATE erp_user SET display_name=:n,avatar_data=:a,updated_at=NOW() WHERE id=:id'), {'n': name, 'a': avatar or None, 'id': user.id})
        write_operation_log(conn, user, '账号安全', 'update_profile', '修改个人资料', before=before,
                            after={'display_name': name, 'avatar_changed': (avatar or None) != user.avatar_data})
        row = conn.execute(text('SELECT * FROM erp_user WHERE id=:id'), {'id': user.id}).mappings().one()
        result = current_user_payload(user_from_row(conn, row))
    return {'user': result}


def policy_audit(conn, account):
    fields = ('username', 'account_type', 'scope_mode', 'log_scope', 'permissions')
    result = {key: account[key] for key in fields}
    ids = account['department_ids']
    result['department_names'] = list(conn.execute(text('SELECT name FROM department WHERE id IN :ids ORDER BY id').bindparams(bindparam('ids', expanding=True)), {'ids': ids}).scalars()) if ids else []
    result['home_department'] = conn.execute(text('SELECT name FROM department WHERE id=:id'), {'id': account['home_department_id']}).scalar()
    return result


@router.post('/login')
def login(payload: LoginRequest):
    with db() as conn:
        row = conn.execute(text('SELECT * FROM erp_user WHERE username=:u'), {'u': payload.username}).mappings().first()
        if not row or not row['is_active'] or not verify_password(payload.password, row['password_hash']):
            raise HTTPException(401, '用户名或密码错误')
        user = user_from_row(conn, row)
        conn.execute(text('UPDATE erp_user SET last_login_at=NOW() WHERE id=:id'), {'id': user.id})
    return {'access_token': create_access_token(user), 'token_type': 'bearer', 'user': current_user_payload(user)}


@router.get('/me')
def me(user: CurrentUser = Depends(get_current_user)):
    return {'user': current_user_payload(user)}


@router.get('/roles')
def roles(user: CurrentUser = Depends(get_current_user)):
    return {'items': [{'role_code': k, 'role_label': ROLE_LABELS[k], 'permissions': sorted(PERMISSIONS) if k == 'super_admin' else []}
                      for k in ('department_user', 'ledger_admin', 'super_admin')]}


@router.post('/change-password')
def change_password(payload: PasswordChange, user: CurrentUser = Depends(get_current_user)):
    if payload.new_password != payload.confirm_password or payload.new_password == payload.old_password:
        raise HTTPException(422, '两次新密码必须一致，且不能与旧密码相同')
    with db() as conn:
        lock_authorization(conn)
        row = conn.execute(text('SELECT password_hash,auth_version FROM erp_user WHERE id=:id FOR UPDATE'), {'id': user.id}).mappings().one()
        if row['auth_version'] != user.auth_version:
            raise HTTPException(401, '登录已失效')
        if not verify_password(payload.old_password, row['password_hash']):
            raise HTTPException(400, '原密码不正确')
        conn.execute(text('UPDATE erp_user SET password_hash=:p,must_change_password=0,auth_version=auth_version+1,updated_at=NOW() WHERE id=:id'), {'p': hash_password(payload.new_password), 'id': user.id})
        write_operation_log(conn, user, '账号安全', 'change_password', '自行修改密码，旧登录凭证已失效')
    return {'message': '密码已修改，请重新登录'}


@router.post('/logout')
def logout(user: CurrentUser = Depends(get_current_user)):
    with db() as conn:
        conn.execute(text('UPDATE erp_user SET auth_version=auth_version+1 WHERE id=:id'), {'id': user.id})
    return {'message': '已退出登录'}


@router.get('/users')
def list_users(status: str = Query('active', pattern='^(active|inactive)$'), user: CurrentUser = Depends(require_permission('accounts_view'))):
    with db() as conn:
        rows = conn.execute(text('SELECT * FROM erp_user WHERE is_active=:active ORDER BY id'), {'active': int(status == 'active')}).mappings().all()
        items = [public_account(conn, row) for row in rows]
        return {'items': clean_rows([r for r in items if can_manage(user, r) or r['id'] == user.id])}


@router.post('/users')
def create_user(payload: UserCreate, user: CurrentUser = Depends(require_permission('accounts_create'))):
    with db() as conn:
        lock_authorization(conn)
        validate_departments(conn, payload)
        policy = payload.model_dump(exclude={'username', 'display_name', 'password'})
        check_manage(user, policy)
        if conn.execute(text('SELECT id FROM erp_user WHERE username=:u'), {'u': payload.username}).scalar():
            raise HTTPException(409, '账号已存在')
        result = conn.execute(text('INSERT INTO erp_user(username,password_hash,display_name,role_code,is_active,must_change_password) VALUES(:u,:p,:n,:r,1,1)'),
                              {'u': payload.username, 'p': hash_password(payload.password), 'n': payload.display_name, 'r': payload.account_type})
        save_policy(conn, result.lastrowid, payload)
        write_operation_log(conn, user, '账号管理', 'create_user', f'创建账号“{payload.username}”', after={'username': payload.username, **policy})
    return {'message': '账号已创建，首次登录必须修改密码'}


def _target(conn, user_id, actor):
    row = conn.execute(text('SELECT * FROM erp_user WHERE id=:id FOR UPDATE'), {'id': user_id}).mappings().first()
    if not row:
        raise HTTPException(404, '账号不存在')
    target = public_account(conn, row)
    check_manage(actor, target)
    return target


@router.put('/users/{user_id}')
def update_user_permissions(user_id: int, payload: UserPermissionUpdate, user: CurrentUser = Depends(require_permission('accounts_update'))):
    with db() as conn:
        lock_authorization(conn)
        target = _target(conn, user_id, user)
        validate_departments(conn, payload)
        check_manage(user, {'id': user_id, **payload.model_dump()})
        if target['account_type'] == 'super_admin' and payload.account_type != 'super_admin':
            ensure_super_admin_remains(conn, user_id)
        before = policy_audit(conn, target)
        save_policy(conn, user_id, payload)
        after = policy_audit(conn, {**target, **payload.model_dump()})
        write_operation_log(conn, user, '账号管理', 'update_user_permissions', f'修改账号“{target["username"]}”权限', before=before, after=after)
    return {'message': '权限已更新，该账号需要重新登录'}


@router.post('/users/{user_id}/reset-password')
def reset_user_password(user_id: int, payload: UserPasswordReset, user: CurrentUser = Depends(get_current_user)):
    if user.account_type != 'super_admin':
        raise HTTPException(403, '仅超级管理员可以重置密码')
    with db() as conn:
        lock_authorization(conn)
        target = _target(conn, user_id, user)
        if not target['is_active']:
            raise HTTPException(409, '请先恢复账号')
        conn.execute(text('UPDATE erp_user SET password_hash=:p,must_change_password=1,auth_version=auth_version+1,updated_at=NOW() WHERE id=:id'), {'p': hash_password(payload.password), 'id': user_id})
        write_operation_log(conn, user, '账号管理', 'reset_user_password', f'重置账号“{target["username"]}”密码')
    return {'message': '密码已重置，首次登录必须修改'}


def _set_active(user_id, active, actor):
    with db() as conn:
        lock_authorization(conn)
        target = _target(conn, user_id, actor)
        if bool(target['is_active']) == bool(active):
            raise HTTPException(409, '账号已启用' if active else '账号已停用')
        if not active and user_id == actor.id:
            raise HTTPException(409, '不能停用当前账号')
        if not active and target['account_type'] == 'super_admin':
            ensure_super_admin_remains(conn, user_id)
        conn.execute(text('UPDATE erp_user SET is_active=:a,auth_version=auth_version+1,updated_at=NOW() WHERE id=:id'), {'a': active, 'id': user_id})
        write_operation_log(conn, actor, '账号管理', 'restore_user' if active else 'delete_user', f'{"恢复" if active else "停用"}账号“{target["username"]}”')
    return {'message': '账号状态已更新'}


@router.delete('/users/{user_id}')
def deactivate_user(user_id: int, user: CurrentUser = Depends(require_permission('accounts_disable'))):
    return _set_active(user_id, 0, user)


@router.post('/users/{user_id}/restore')
def restore_user(user_id: int, user: CurrentUser = Depends(require_permission('accounts_disable'))):
    return _set_active(user_id, 1, user)


@router.delete('/users/{user_id}/permanent')
def permanently_delete_user(user_id: int, user: CurrentUser = Depends(get_current_user)):
    if user.account_type != 'super_admin':
        raise HTTPException(403, '仅超级管理员可操作')
    with db() as conn:
        lock_authorization(conn)
        target = _target(conn, user_id, user)
        if target['is_active']:
            raise HTTPException(409, '请先停用账号')
        for table, column in [('operation_log', 'user_id'), ('backup_record', 'created_by'), ('import_batch', 'uploaded_by')]:
            conn.execute(text(f'UPDATE {table} SET {column}=NULL WHERE {column}=:id'), {'id': user_id})
        conn.execute(text('DELETE FROM erp_user WHERE id=:id'), {'id': user_id})
        write_operation_log(conn, user, '账号管理', 'permanently_delete_user', f'永久删除账号“{target["username"]}”')
    return {'message': '账号已删除'}
