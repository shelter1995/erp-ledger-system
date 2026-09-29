"""Build explicit v2 accounts for pre-existing business regression scenarios.

This helper is test-only: production never accepts the legacy payload. It completes
initial password change through the real API before a business test logs in.
"""
from sqlalchemy import text
from app.db import db
from app.authorization import READ_PERMISSIONS,WRITE_PERMISSIONS


def create_test_account(client, *, headers, payload):
    names=payload.get('department_scope',[])
    permissions=set(payload.get('permissions',[])) | READ_PERMISSIONS
    if not payload.get('department_can_entry',True):
        permissions-=WRITE_PERMISSIONS | {'ledger_import'}
    if 'ledger_import' in permissions:
        permissions.add('maintenance_view')
    ids=[]
    with db() as conn:
        for name in names:
            conn.execute(text('INSERT IGNORE INTO department(name) VALUES(:n)'),{'n':name})
            conn.execute(text('INSERT IGNORE INTO department_alias(name,department_id) SELECT name,id FROM department WHERE name=:n'),{'n':name})
            ids.append(conn.execute(text('SELECT id FROM department WHERE name=:n'),{'n':name}).scalar_one())
    final_password=payload['password']
    temporary='Initial-'+final_password
    policy={'username':payload['username'],'display_name':payload['display_name'],'password':temporary,
            'account_type':'department_user' if names else 'ledger_admin',
            'home_department_id':ids[0] if ids else None,'department_ids':ids,
            'scope_mode':'selected' if ids else ('all' if payload.get('department_all',True) else 'none'),
            'permissions':sorted(permissions),'log_scope':'self'}
    response=client.post('/api/auth/users',headers=headers,json=policy)
    if response.status_code==200:
        login=client.post('/api/auth/login',json={'username':policy['username'],'password':temporary})
        assert login.status_code==200,login.text
        changed=client.post('/api/auth/change-password',headers={'Authorization':'Bearer '+login.json()['access_token']},json={'old_password':temporary,'new_password':final_password,'confirm_password':final_password})
        assert changed.status_code==200,changed.text
    return response
