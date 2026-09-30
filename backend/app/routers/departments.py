from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from ..auth import CurrentUser, get_current_user
from ..db import db
from ..authorization_migration import lock_authorization
from ..audit import write_operation_log

router = APIRouter(prefix='/api/departments', tags=['departments'])


class DepartmentInput(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    is_active: bool = True


@router.get('')
def departments(user: CurrentUser = Depends(get_current_user)):
    with db() as conn:
        rows = conn.execute(text('SELECT id,name,is_active FROM department ORDER BY name')).mappings().all()
        return {'items': [dict(r) for r in rows if user.account_type == 'super_admin' or (r['is_active'] and (user.scope_mode == 'all' or r['id'] in user.department_ids or r['id'] == user.home_department_id))]}


def _save(payload, user, department_id=None):
    if user.account_type != 'super_admin':
        raise HTTPException(403, '仅超级管理员可以管理部门目录')
    name = payload.name.strip()
    if not name:
        raise HTTPException(422, '部门名称不能为空')
    with db() as conn:
        lock_authorization(conn)
        owner = conn.execute(text('SELECT department_id FROM department_alias WHERE name=:n'), {'n': name}).scalar()
        if owner is not None and owner != department_id:
            raise HTTPException(409, '部门名称或历史名称已被使用')
        before = None
        if department_id is None:
            result = conn.execute(text('INSERT INTO department(name,is_active) VALUES(:n,:a)'), {'n': name, 'a': int(payload.is_active)})
            department_id = result.lastrowid
        else:
            row = conn.execute(text('SELECT * FROM department WHERE id=:id FOR UPDATE'), {'id': department_id}).mappings().first()
            if not row:
                raise HTTPException(404, '部门不存在')
            before = dict(row)
            conn.execute(text('UPDATE department SET name=:n,is_active=:a WHERE id=:id'), {'n': name, 'a': int(payload.is_active), 'id': department_id})
        if owner is None:
            conn.execute(text('INSERT INTO department_alias(name,department_id) VALUES(:n,:id)'), {'n': name, 'id': department_id})
        # New departments have no existing memberships. A no-op save must not
        # invalidate sessions either. For real changes, refresh only accounts
        # tied to this department; super admins remain able to manage the catalog.
        if before is not None and (before['name'] != name or bool(before['is_active']) != payload.is_active):
            conn.execute(text('''UPDATE erp_user SET auth_version=auth_version+1
                WHERE authorization_version=1 AND account_type<>'super_admin'
                  AND (home_department_id=:department_id OR id IN (
                      SELECT user_id FROM user_department WHERE department_id=:department_id
                  ))'''), {'department_id': department_id})
        write_operation_log(conn, user, '账号管理', 'update_department', f'维护部门“{name}”', before=before, after={'id': department_id, 'name': name, 'is_active': payload.is_active})
    return {'message': '部门已保存'}


@router.post('')
def create_department(payload: DepartmentInput, user: CurrentUser = Depends(get_current_user)):
    return _save(payload, user)


@router.put('/{department_id}')
def update_department(department_id: int, payload: DepartmentInput, user: CurrentUser = Depends(get_current_user)):
    return _save(payload, user, department_id)
