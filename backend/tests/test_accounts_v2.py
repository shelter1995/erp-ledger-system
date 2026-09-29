import pytest
from sqlalchemy import text
from app.db import db
from app.auth import hash_password
from conftest import TEST_PASSWORD


@pytest.fixture
def admin_v2(client):
    with db() as conn:
        conn.execute(text("UPDATE erp_user SET account_type='super_admin',role_code='super_admin',scope_mode='all',log_scope='all',authorization_version=1,must_change_password=0,is_active=1,password_hash=:p WHERE username='admin'"), {'p':hash_password(TEST_PASSWORD)})
    response = client.post('/api/auth/login', json={'username':'admin','password':TEST_PASSWORD})
    assert response.status_code == 200, response.text
    return {'Authorization': 'Bearer ' + response.json()['access_token']}


def test_password_reset_forces_change_and_revokes_tokens(client, admin_v2):
    username='v2_password'
    with db() as conn:
        conn.execute(text('DELETE FROM erp_user WHERE username=:u'), {'u':username})
    payload = dict(username=username,display_name='测试账号',password='Temporary-Pass-123',account_type='ledger_admin',scope_mode='all',permissions=['ledger_view'])
    created=client.post('/api/auth/users',json=payload,headers=admin_v2)
    assert created.status_code == 200, created.text
    login=client.post('/api/auth/login',json={'username':username,'password':payload['password']})
    token={'Authorization':'Bearer '+login.json()['access_token']}
    assert login.json()['user']['must_change_password'] is True
    assert client.get('/api/ledgers/summary',headers=token).status_code == 403
    changed=client.post('/api/auth/change-password',json={'old_password':payload['password'],'new_password':'Personal-Pass-123','confirm_password':'Personal-Pass-123'},headers=token)
    assert changed.status_code == 200, changed.text
    assert client.get('/api/auth/me',headers=token).status_code == 401
    login=client.post('/api/auth/login',json={'username':username,'password':'Personal-Pass-123'})
    token={'Authorization':'Bearer '+login.json()['access_token']}
    assert client.get('/api/ledgers/summary',headers=token).status_code == 200
    assert client.get('/api/purchases',headers=token).status_code == 403
    reset=client.post(f'/api/auth/users/{login.json()["user"]["id"]}/reset-password',json={'password':'Reset-Password-123'},headers=admin_v2)
    assert reset.status_code == 200, reset.text
    assert client.get('/api/auth/me',headers=token).status_code == 401


def test_management_pages_and_super_admin_protection(client, admin_v2):
    me=client.get('/api/auth/me',headers=admin_v2).json()['user']
    assert client.delete(f'/api/auth/users/{me["id"]}',headers=admin_v2).status_code == 409
    for path in ('/api/departments','/api/logs','/api/backups','/api/dashboard/data'):
        response=client.get(path,headers=admin_v2)
        assert response.status_code == 200, (path,response.text)


def test_concurrent_demotions_keep_one_super_admin(client,admin_v2):
    from concurrent.futures import ThreadPoolExecutor
    from fastapi.testclient import TestClient
    from app.main import app
    from app.auth import create_access_token,user_from_row
    with db() as conn:
        # Keep the usual test administrator, and introduce one second administrator.
        result=conn.execute(text("INSERT INTO erp_user(username,password_hash,display_name,role_code,account_type,scope_mode,log_scope,authorization_version) VALUES('concurrent_super','unused','test','super_admin','super_admin','all','all',1)"))
        ids=[conn.execute(text("SELECT id FROM erp_user WHERE username='admin'")).scalar_one(),result.lastrowid]
        actors=[user_from_row(conn,conn.execute(text('SELECT * FROM erp_user WHERE id=:id'),{'id':uid}).mappings().one()) for uid in ids]
    policy={'account_type':'ledger_admin','scope_mode':'all','permissions':[],'log_scope':'self'}
    def demote(user):
        session=TestClient(app,raise_server_exceptions=False)
        return session.put('/api/auth/users/'+str(user.id),json=policy,headers={'Authorization':'Bearer '+create_access_token(user)}).status_code
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(demote,actors))
        assert sorted(results)==[200,409],results
        with db() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM erp_user WHERE account_type='super_admin' AND is_active=1")).scalar_one()==1
    finally:
        with db() as conn:
            conn.execute(text("UPDATE erp_user SET account_type='super_admin',role_code='super_admin',scope_mode='all',log_scope='all' WHERE username='admin'"))
            conn.execute(text('DELETE FROM operation_log WHERE user_id=:id'),{'id':ids[1]})
            conn.execute(text('DELETE FROM erp_user WHERE id=:id'),{'id':ids[1]})
