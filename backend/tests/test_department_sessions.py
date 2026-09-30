from uuid import uuid4

import pytest
from sqlalchemy import text

from app.db import db
from test_accounts_v2 import admin_v2
from test_permission_routes_v2 import actor, directory


def test_create_departments_keeps_existing_sessions(client, admin_v2):
    suffix = uuid4().hex[:8]
    with db() as conn:
        dept = directory(conn, '现有部门' + suffix)
        _, selected = actor(conn, 'selected_' + suffix, ['ledger_view'], [dept])
        _, all_scope = actor(conn, 'all_' + suffix, ['ledger_view'], [], scope='all')
    for index in range(2):
        response = client.post('/api/departments', headers=admin_v2,
                               json={'name': f'新增部门{suffix}-{index}'})
        assert response.status_code == 200, response.text
        for headers in (admin_v2, selected, all_scope):
            assert client.get('/api/auth/me', headers=headers).status_code == 200
    response = client.get('/api/departments', headers=admin_v2)
    assert any(d['name'] == f'新增部门{suffix}-1' for d in response.json()['items'])


def test_unchanged_department_keeps_sessions(client, admin_v2):
    suffix = uuid4().hex[:8]
    name = '原样保存' + suffix
    with db() as conn:
        dept = directory(conn, name)
        _, member = actor(conn, 'unchanged_' + suffix, ['ledger_view'], [dept])
    response = client.put(f'/api/departments/{dept}', headers=admin_v2,
                          json={'name': name, 'is_active': True})
    assert response.status_code == 200, response.text
    for headers in (admin_v2, member):
        assert client.get('/api/auth/me', headers=headers).status_code == 200


@pytest.mark.parametrize('change', ['rename', 'disable', 'enable'])
def test_department_change_revokes_only_related_non_admin_sessions(client, admin_v2, change):
    suffix = uuid4().hex[:8]
    name = '会话部门' + suffix
    with db() as conn:
        dept = directory(conn, name)
        other = directory(conn, '无关部门' + suffix)
        if change == 'enable':
            conn.execute(text('UPDATE department SET is_active=0 WHERE id=:d'), {'d': dept})
        _, affected = actor(conn, 'affected_' + suffix, ['ledger_view'], [dept])
        _, unaffected = actor(conn, 'unaffected_' + suffix, ['ledger_view'], [other])
        _, all_scope = actor(conn, 'all_' + suffix, ['ledger_view'], [], scope='all')
    response = client.put(f'/api/departments/{dept}', headers=admin_v2,
                          json={'name': name + '新名' if change == 'rename' else name,
                                'is_active': change != 'disable'})
    assert response.status_code == 200, response.text
    assert client.get('/api/auth/me', headers=affected).status_code == 401
    for headers in (admin_v2, unaffected, all_scope):
        assert client.get('/api/auth/me', headers=headers).status_code == 200
    refreshed = client.post('/api/auth/login', json={
        'username': 'affected_' + suffix, 'password': 'Permission-Test-123'})
    assert refreshed.status_code == 200, refreshed.text
    headers = {'Authorization': 'Bearer ' + refreshed.json()['access_token']}
    visible = client.get('/api/departments', headers=headers).json()['items']
    assert any(d['id'] == dept for d in visible) == (change != 'disable')


def test_rejected_department_create_keeps_sessions(client, admin_v2):
    suffix = uuid4().hex[:8]
    name = '重名部门' + suffix
    with db() as conn:
        dept = directory(conn, name)
        _, member = actor(conn, 'rejected_' + suffix, ['ledger_view'], [dept])
    assert client.post('/api/departments', headers=admin_v2,
                       json={'name': name}).status_code == 409
    assert client.post('/api/departments', headers=member,
                       json={'name': name + '无权新增'}).status_code == 403
    for headers in (admin_v2, member):
        assert client.get('/api/auth/me', headers=headers).status_code == 200
