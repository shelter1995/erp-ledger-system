import json
from sqlalchemy import text
from app.db import db
from test_accounts_v2 import admin_v2


def test_profile_self_only_and_audit_without_image(client, admin_v2):
    before = client.get('/api/auth/me', headers=admin_v2).json()['user']
    name = '本地资料测试'
    response = client.put('/api/auth/profile', headers=admin_v2, json={'display_name':name, 'avatar_data':None})
    assert response.status_code == 200, response.text
    after = response.json()['user']
    assert after['display_name'] == name
    assert after['permissions'] == before['permissions']
    assert client.get('/api/auth/me', headers=admin_v2).json()['user']['display_name'] == name
    for extra in ({'id':999}, {'permissions':['accounts_update']}, {'account_type':'super_admin'}):
        assert client.put('/api/auth/profile',headers=admin_v2,json={'display_name':name,**extra}).status_code == 422
    assert client.put('/api/auth/profile',headers=admin_v2,json={'display_name':'  '}).status_code == 422
    for avatar in ('data:image/svg+xml;base64,PHN2Zz4=', 'data:image/png;base64,bm90YW5pbWFnZQ=='):
        assert client.put('/api/auth/profile',headers=admin_v2,json={'display_name':name,'avatar_data':avatar}).status_code==422
    with db() as conn:
        detail=json.loads(conn.execute(text("SELECT detail FROM operation_log WHERE action_name='update_profile' ORDER BY id DESC LIMIT 1")).scalar_one())
    assert detail['after']['display_name']==name
    assert 'avatar_data' not in detail['after']
    avatar='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6b9sAAAAASUVORK5CYII='
    response=client.put('/api/auth/profile',headers=admin_v2,json={'display_name':name,'avatar_data':avatar})
    assert response.status_code==200,response.text
    assert client.get('/api/auth/me',headers=admin_v2).json()['user']['avatar_data']==avatar
    response=client.put('/api/auth/profile',headers=admin_v2,json={'display_name':name,'avatar_data':None})
    assert response.status_code==200
    assert client.get('/api/auth/me',headers=admin_v2).json()['user']['avatar_data'] is None
    # An established temporary-password account must change password first.
    with db() as conn:
        conn.execute(text('UPDATE erp_user SET must_change_password=1 WHERE id=:id'),{'id':before['id']})
    assert client.put('/api/auth/profile',headers=admin_v2,json={'display_name':name}).status_code==403
    with db() as conn:
        conn.execute(text('UPDATE erp_user SET must_change_password=0,display_name=:n WHERE id=:id'),{'n':before['display_name'],'id':before['id']})


def test_permission_audit_has_symmetric_named_snapshots(client,admin_v2):
    departments=client.get('/api/departments',headers=admin_v2).json()['items']
    dept=departments[0]
    policy={'account_type':'department_user','scope_mode':'selected','home_department_id':dept['id'],'department_ids':[dept['id']],'permissions':['ledger_view'],'log_scope':'self'}
    response=client.post('/api/auth/users',headers=admin_v2,json={**policy,'username':'audit_ui_reader','display_name':'日志验收','password':'Temporary-Test-123!'})
    assert response.status_code==200,response.text
    target=next(u for u in client.get('/api/auth/users',headers=admin_v2).json()['items'] if u['username']=='audit_ui_reader')
    response=client.put('/api/auth/users/'+str(target['id']),headers=admin_v2,json={**policy,'permissions':['ledger_view','logs_view'],'log_scope':'department'})
    assert response.status_code==200,response.text
    with db() as conn:
        detail=json.loads(conn.execute(text("SELECT detail FROM operation_log WHERE action_name='update_user_permissions' ORDER BY id DESC LIMIT 1")).scalar_one())
    assert detail['before'].keys()==detail['after'].keys()
    assert detail['before']['department_names']==[dept['name']]
    assert detail['after']['home_department']==dept['name']
    assert detail['before']['username']==detail['after']['username']=='audit_ui_reader'
    assert detail['after']['permissions']==['ledger_view','logs_view']
