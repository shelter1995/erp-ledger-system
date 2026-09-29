from sqlalchemy import text
from app.db import db
from test_accounts_v2 import admin_v2
from test_permission_routes_v2 import actor,directory
from test_legacy_import_flow import _preview,_row,_workbook


def test_preview_token_cannot_commit_after_permission_revocation(client,admin_v2):
    with db() as conn:
        department=directory(conn,'销售部')
        uid,headers=actor(conn,'preview_revoke',['maintenance_view','ledger_import'],[department])
    rows=[_row()]
    preview=_preview(client,headers,rows)
    assert preview.status_code==200,preview.text
    with db() as conn:
        conn.execute(text("UPDATE erp_user SET permissions_json='[]',auth_version=auth_version+1 WHERE id=:id"),{'id':uid})
    response=client.post('/api/orders/import-preview/'+preview.json()['session_id']+'/commit',content=_workbook(rows),headers=headers)
    assert response.status_code==401,response.text
    with db() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM order_line')).scalar_one()==0
        assert conn.execute(text('SELECT COUNT(*) FROM project')).scalar_one()==0


def test_unknown_backup_department_blocks_restore_before_deletion(client,admin_v2):
    with db() as conn:
        conn.execute(text("INSERT INTO project(project_code,department) VALUES('UNKNOWN-BACKUP','未登记备份部门')"))
    backup=client.post('/api/backups',headers=admin_v2)
    assert backup.status_code==200,backup.text
    with db() as conn:
        conn.execute(text("DELETE FROM project WHERE project_code='UNKNOWN-BACKUP'"))
        conn.execute(text("INSERT INTO project(project_code,department) VALUES('KEEP-CURRENT','QA')"))
    response=client.post('/api/backups/'+str(backup.json()['id'])+'/restore',headers=admin_v2)
    assert response.status_code==422,response.text
    assert '未登记部门' in response.json()['detail']
    with db() as conn:
        assert list(conn.execute(text('SELECT project_code FROM project')).scalars())==['KEEP-CURRENT']
