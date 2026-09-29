import copy
import json
import pytest
from sqlalchemy import text
from app.db import engine
from app.authorization_migration import account_inventory,apply_mapping,prepare_schema
from app.auth import user_from_row


def test_reviewed_migration_preserves_denials_and_cannot_reapply(mysql_test_database):
    # Roll back the synthetic legacy setup and migration together, including the marker.
    with engine.connect() as conn:
        tx=conn.begin()
        try:
            conn.execute(text("DELETE FROM schema_migration WHERE migration_key='20260929_authorization_v2'"))
            conn.execute(text("UPDATE erp_user SET authorization_version=0,role_code='admin',permissions_json='[\"system_admin\"]'"))
            conn.execute(text("INSERT INTO erp_user(username,password_hash,display_name,role_code,permissions_json,department_scope_json,department_can_view,department_can_entry) VALUES('migration_legacy','private-hash','legacy','viewer','[\"order_entry\",\"ledger_import\"]','[\"旧迁移部\"]',1,0)"))
            report=account_inventory(conn)
            assert 'private-hash' not in json.dumps(report)
            legacy=next(r for r in report['accounts'] if r['username']=='migration_legacy')
            assert 'order_entry' not in legacy['candidate']['permissions']
            assert 'ledger_import' not in legacy['candidate']['permissions']
            with pytest.raises(ValueError,match='逐一核对'):
                apply_mapping(conn,report)
            for row in report['accounts']:
                row['reviewed']=True
            stale=copy.deepcopy(report);stale['source_digest']='wrong'
            with pytest.raises(ValueError,match='已变化'):
                apply_mapping(conn,stale)
            report['department_mapping']['旧迁移部']='规范迁移部'
            apply_mapping(conn,report)
            row=conn.execute(text("SELECT * FROM erp_user WHERE username='migration_legacy'")).mappings().one()
            user=user_from_row(conn,row)
            assert user.scope_mode=='selected'
            assert set(user.department_scope)=={'旧迁移部','规范迁移部'}
            conn.execute(text("UPDATE erp_user SET permissions_json='[]' WHERE username='migration_legacy'"))
            with pytest.raises(ValueError,match='已执行'):
                apply_mapping(conn,report)
            assert conn.execute(text("SELECT permissions_json FROM erp_user WHERE username='migration_legacy'")).scalar()=='[]'
        finally:
            tx.rollback()


def test_mapping_refuses_already_initialized_accounts(mysql_test_database):
    with engine.begin() as conn:
        with pytest.raises(ValueError,match='已有新权限账号'):
            apply_mapping(conn,account_inventory(conn))
