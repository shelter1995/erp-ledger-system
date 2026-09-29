from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Callable

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text

from .config import settings
from .db import db
from .authorization import PERMISSIONS, route_permissions
from .authorization_migration import prepare_schema

Permission = str
ALL_PERMISSIONS = {
    "order_entry",
    "order_edit",
    "order_delete",
    "purchase_entry",
    "purchase_edit",
    "purchase_delete",
    "sales_entry",
    "sales_edit",
    "sales_delete",
    "system_admin",
    # 整表导入是独立权限点：能录订单不等于能一次性导入整份台账（含采购及销售财务数据）。
    "ledger_import",
}

ALL_PERMISSIONS |= PERMISSIONS

ROLE_PERMISSIONS: dict[str, set[Permission]] = {
    "admin": set(ALL_PERMISSIONS),
    "order_entry": {"order_entry"},
    "purchase_entry": {"purchase_entry"},
    "sales_entry": {"sales_entry"},
    "viewer": set(),
}

ROLE_PERMISSIONS.update({'super_admin': set(PERMISSIONS), 'ledger_admin': set(), 'department_user': set()})

ROLE_LABELS: dict[str, str] = {
    "admin": "管理员",
    "order_entry": "订单录入员",
    "purchase_entry": "采购录入员",
    "sales_entry": "销售录入员",
    "viewer": "查看员",
}

ROLE_LABELS.update({'super_admin': '系统超级管理员', 'ledger_admin': '台账管理员', 'department_user': '部门账号'})

security = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    id: int
    username: str
    display_name: str
    role_code: str
    permissions: list[str]
    department_scope: list[str]
    department_can_view: bool
    department_can_entry: bool
    account_type: str = 'department_user'
    scope_mode: str | None = None
    department_ids: list[int] = field(default_factory=list)
    home_department_id: int | None = None
    log_scope: str = 'self'
    must_change_password: bool = False
    auth_version: int = 1
    authorization_version: int = 0
    avatar_data: str | None = None


def has_permission(role_code: str, permission: Permission, permissions: list[str] | set[str] | None = None) -> bool:
    if role_code == 'super_admin':
        return permission in ALL_PERMISSIONS
    granted = set(permissions) if permissions is not None else ROLE_PERMISSIONS.get(role_code, set())
    return permission in granted


def normalize_permissions(role_code: str, permissions: list[str] | None) -> list[str]:
    if permissions is None:
        return sorted(ROLE_PERMISSIONS.get(role_code, set()))
    return sorted({permission for permission in permissions if permission in ALL_PERMISSIONS})


def parse_json_list(value: object) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()]


def encode_json_list(values: list[str]) -> str:
    clean_values = [value.strip() for value in values if value.strip()]
    return json.dumps(clean_values, ensure_ascii=False)


def apply_department_scope(
    conditions: list[str],
    params: dict[str, object],
    user: CurrentUser,
    column_name: str = "department",
) -> None:
    if user.account_type == 'super_admin' or user.scope_mode == 'all':
        return
    if user.scope_mode == 'none' or (user.scope_mode == 'selected' and not user.department_scope):
        conditions.append('1=0')
        return
    if user.scope_mode is None and not user.department_scope:
        conditions.append('1=0')
        return
    if not user.department_can_view:
        conditions.append("1=0")
        return
    placeholders: list[str] = []
    for index, department in enumerate(user.department_scope):
        key = f"scope_department_{index}"
        placeholders.append(f":{key}")
        params[key] = department
    conditions.append(f"{column_name} IN ({', '.join(placeholders)})")


def can_access_department(user: CurrentUser, department: str | None, require_entry: bool = False) -> bool:
    if user.account_type == 'super_admin' or user.scope_mode == 'all':
        return True
    if user.scope_mode == 'none' or not user.department_scope:
        return False
    if user.authorization_version == 0:
        if require_entry and not user.department_can_entry:
            return False
        if not require_entry and not user.department_can_view:
            return False
    return bool(department and department in user.department_scope)



def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"pbkdf2_sha256$120000${salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt, expected = stored_hash.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations))
    return hmac.compare_digest(digest.hex(), expected)


def create_access_token(user: CurrentUser, expires_in_seconds: int = 12 * 60 * 60) -> str:
    payload = {
        "sub": user.username,
        "uid": user.id,
        "av": user.auth_version,
        "role": user.role_code,
        "exp": int(time.time()) + expires_in_seconds,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    payload_b64 = _b64encode(payload_bytes)
    signature = _sign(payload_b64.encode("ascii"))
    return f"{payload_b64}.{signature}"


def decode_access_token(token: str) -> dict:
    try:
        payload_b64, signature = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    if not hmac.compare_digest(_sign(payload_b64.encode("ascii")), signature):
        raise HTTPException(status_code=401, detail="Invalid token")
    try:
        payload = json.loads(_b64decode(payload_b64))
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    if int(payload.get("exp", 0)) < int(time.time()):
        raise HTTPException(status_code=401, detail="Token expired")
    return payload


def migrate_ledger_import_permission(conn) -> None:
    """首次升级时给原有 system_admin 账号补上 ledger_import。

    只处理显式权限 JSON 的账号：
    - 含 system_admin 且缺 ledger_import → 追加；
    - 普通账号不隐式获权；
    - permissions_json 为空（NULL）表示继承角色默认，保持不动，admin 角色本身已含新权限；
    - 显式空数组 "[]" 保持为空，不改成继承角色默认。

    schema_migration 的唯一键让这项兼容迁移在每个数据库只执行一次；迁移标记与
    权限更新位于同一事务，失败时一并回滚。迁移完成后的人工撤权不会被重启覆盖。
    """
    marker = conn.execute(
        text(
            """
            INSERT IGNORE INTO schema_migration (migration_key)
            VALUES ('20260916_add_ledger_import_permission')
            """
        )
    )
    if marker.rowcount == 0:
        return

    rows = conn.execute(text("SELECT id, permissions_json FROM erp_user")).mappings().all()
    for row in rows:
        stored = row["permissions_json"]
        if stored in (None, ""):
            continue
        permissions = parse_json_list(stored)
        if "system_admin" not in permissions or "ledger_import" in permissions:
            continue
        conn.execute(
            text("UPDATE erp_user SET permissions_json = :permissions_json WHERE id = :user_id"),
            {"user_id": int(row["id"]), "permissions_json": encode_json_list(permissions + ["ledger_import"])},
        )


def ensure_default_admin() -> None:
    with db() as conn:
        _ensure_user_permission_columns(conn)
        prepare_schema(conn)
        existing = conn.execute(
            text("SELECT password_hash FROM erp_user WHERE username = 'admin'")
        ).mappings().first()
        if not existing and not conn.execute(text('SELECT COUNT(*) FROM erp_user')).scalar():
            if len(settings.default_admin_password) < 12:
                raise RuntimeError('新系统初始管理员密码至少需要 12 个字符')
            conn.execute(
                text(
                    """
                    INSERT INTO erp_user
                      (username, password_hash, display_name, role_code, permissions_json,
                       department_scope_json, department_can_view, department_can_entry, is_active)
                    VALUES
                      (:username, :password_hash, :display_name, :role_code, :permissions_json,
                       :department_scope_json, 1, 1, 1)
                    """
                ),
                {
                    "username": "admin",
                    "password_hash": hash_password(settings.default_admin_password),
                    "display_name": "系统管理员",
                    "role_code": "admin",
                    "permissions_json": encode_json_list(sorted(PERMISSIONS)),
                    "department_scope_json": encode_json_list([]),
                },
            )
            conn.execute(text("UPDATE erp_user SET account_type='super_admin',role_code='super_admin',scope_mode='all',log_scope='all',authorization_version=1,must_change_password=1 WHERE username='admin'"))
        migrate_ledger_import_permission(conn)


def user_from_row(conn, row) -> CurrentUser:
    if not row.get('authorization_version'):
        raise HTTPException(403, '账号权限尚未迁移，请由管理员核对账号映射后切换')
    kind = row['account_type']
    ids = list(conn.execute(text('SELECT department_id FROM user_department WHERE user_id=:id'), {'id': row['id']}).scalars())
    aliases = list(conn.execute(text('SELECT a.name FROM department_alias a JOIN user_department ud ON ud.department_id=a.department_id JOIN department d ON d.id=a.department_id WHERE ud.user_id=:id AND d.is_active=1'), {'id': row['id']}).scalars())
    return CurrentUser(avatar_data=row.get('avatar_data'), id=int(row['id']), username=row['username'], display_name=row['display_name'], role_code=kind,
        account_type=kind, permissions=sorted(PERMISSIONS) if kind == 'super_admin' else normalize_permissions(kind, parse_json_list(row['permissions_json'])),
        department_scope=aliases, department_can_view=True, department_can_entry=True,
        scope_mode=row['scope_mode'], department_ids=ids, home_department_id=row['home_department_id'],
        log_scope=row['log_scope'], must_change_password=bool(row['must_change_password']),
        auth_version=int(row['auth_version']), authorization_version=int(row['authorization_version']))


def current_user_from_token(token: str) -> CurrentUser:
    payload = decode_access_token(token)
    with db() as conn:
        row = conn.execute(text('SELECT * FROM erp_user WHERE id=:id AND is_active=1'), {'id': payload.get('uid')}).mappings().first()
        if row is None or payload.get('av') != row['auth_version'] or payload.get('sub') != row['username']:
            raise HTTPException(401, '登录已失效，请重新登录')
        return user_from_row(conn, row)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = current_user_from_token(credentials.credentials)
    request.state.current_user = user
    if user.must_change_password and request.url.path not in {'/api/auth/me', '/api/auth/change-password', '/api/auth/logout'}:
        raise HTTPException(403, detail={'code': 'PASSWORD_CHANGE_REQUIRED', 'message': '请先修改临时密码'})
    for permission in route_permissions(request.url.path, request.method):
        if not has_permission(user.role_code, permission, user.permissions):
            raise HTTPException(403, '没有该模块权限')
    return user


def require_permission(permission: Permission) -> Callable[[CurrentUser], CurrentUser]:
    def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not has_permission(user.role_code, permission, user.permissions):
            raise HTTPException(status_code=403, detail="Permission denied")
        if permission in {'data_replace', 'backups_restore'} and user.scope_mode != 'all' and user.account_type != 'super_admin':
            raise HTTPException(403, '此操作要求明确授权全部门')
        return user

    return dependency


def current_user_payload(user: CurrentUser) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "avatar_data": user.avatar_data,
        "role_code": user.role_code,
        "role_label": ROLE_LABELS.get(user.role_code, user.role_code),
        "permissions": user.permissions,
        "department_scope": user.department_scope,
        "department_can_view": user.department_can_view,
        "department_can_entry": user.department_can_entry,
        "account_type": user.account_type, "scope_mode": user.scope_mode,
        "department_ids": user.department_ids, "home_department_id": user.home_department_id,
        "log_scope": user.log_scope, "must_change_password": user.must_change_password,
    }


def _ensure_user_permission_columns(conn) -> None:
    columns = {
        row["COLUMN_NAME"]
        for row in conn.execute(
            text(
                """
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'erp_user'
                """
            )
        ).mappings()
    }
    column_sql = {
        "permissions_json": "ALTER TABLE erp_user ADD COLUMN permissions_json JSON NULL AFTER role_code",
        "department_scope_json": "ALTER TABLE erp_user ADD COLUMN department_scope_json JSON NULL AFTER permissions_json",
        "department_can_view": "ALTER TABLE erp_user ADD COLUMN department_can_view TINYINT(1) NOT NULL DEFAULT 0 AFTER department_scope_json",
        "department_can_entry": "ALTER TABLE erp_user ADD COLUMN department_can_entry TINYINT(1) NOT NULL DEFAULT 0 AFTER department_can_view",
    }
    for column, ddl in column_sql.items():
        if column not in columns:
            conn.execute(text(ddl))


def _sign(value: bytes) -> str:
    signature = hmac.new(settings.auth_secret.encode("utf-8"), value, hashlib.sha256).digest()
    return _b64encode(signature)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
