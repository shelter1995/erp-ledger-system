"""Disposable local acceptance server. Synthetic identities only."""
import os
import sys
import tempfile
from pathlib import Path
os.environ['MYSQL_DATABASE']='erp_ledger_test_auth_browser_20260929'
os.environ['BACKUP_ROOT']=str(Path(tempfile.gettempdir())/'erp-auth-browser-20260929')
os.environ['AUTH_SECRET']='local-acceptance-only-auth-secret-20260929'
os.environ['DEFAULT_ADMIN_PASSWORD']='Local-Review-20260929!'
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
from app.db import initialize_schema, db, engine, server_engine
from app.auth import ensure_default_admin, hash_password
from sqlalchemy import text
# Repair only this script's synthetic rows before runtime archive recovery.
# Never apply this repair to imported rows or another database.
assert engine.url.database == 'erp_ledger_test_auth_browser_20260929'
with server_engine.connect() as conn:
    existing = conn.execute(text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=:db AND table_name='order_line'"), {'db': engine.url.database}).scalar()
if existing:
    with engine.begin() as conn:
        demo_filter = """ol.raw_row_id IS NULL AND ol.source_preserved=1
            AND p.project_code='演示框架-001' AND p.project_name='权限验收演示'
            AND so.order_no='演示订单-001' AND ol.goods_name='演示商品'
            AND ol.line_department IN ('市场部','采购部')"""
        conn.execute(text(f"""UPDATE order_line ol
            JOIN sales_order so ON so.id=ol.sales_order_id
            JOIN project p ON p.id=so.project_id
            SET ol.line_order_date_initialized=1
            WHERE {demo_filter} AND ol.line_order_date_initialized=0
              AND ol.line_order_date='2026-09-29'"""))
        conn.execute(text(f"""UPDATE order_line ol
            JOIN sales_order so ON so.id=ol.sales_order_id
            JOIN project p ON p.id=so.project_id
            LEFT JOIN purchase_info pi ON pi.order_line_id=ol.id AND pi.deleted_at IS NULL
            SET ol.source_order_value_precise=ol.order_value,
                ol.source_purchase_amount_precise=pi.purchase_amount,
                ol.profit_tax_amount=0, ol.profit_tax_refund=0,
                ol.profit_inputs_initialized=1
            WHERE {demo_filter} AND ol.profit_inputs_initialized=0"""))
initialize_schema()
ensure_default_admin()
with db() as conn:
    conn.execute(text("UPDATE erp_user SET must_change_password=0 WHERE username='admin'"))
    for name in ('市场部','采购部'):
        conn.execute(text('INSERT IGNORE INTO department(name) VALUES(:n)'),{'n':name})
        conn.execute(text('INSERT IGNORE INTO department_alias(name,department_id) SELECT name,id FROM department WHERE name=:n'),{'n':name})
    import json
    market=conn.execute(text("SELECT id FROM department WHERE name='市场部'")).scalar_one()
    for username,force in [('review_reader',0),('review_temporary',1)]:
        if not conn.execute(text('SELECT id FROM erp_user WHERE username=:u'),{'u':username}).scalar():
            result=conn.execute(text("INSERT INTO erp_user(username,password_hash,display_name,role_code,account_type,scope_mode,home_department_id,permissions_json,authorization_version,must_change_password) VALUES(:u,:p,:u,'department_user','department_user','selected',:d,:perms,1,:force)"),{'u':username,'p':hash_password('Local-Reader-20260929!'),'d':market,'perms':json.dumps(['dashboard_view','ledger_view']),'force':force})
            conn.execute(text('INSERT INTO user_department VALUES(:u,:d)'),{'u':result.lastrowid,'d':market})
    if not conn.execute(text("SELECT id FROM project WHERE project_code='演示框架-001'")).scalar():
        pid=conn.execute(text("INSERT INTO project(project_code,project_name,department) VALUES('演示框架-001','权限验收演示','市场部')")).lastrowid
        oid=conn.execute(text("INSERT INTO sales_order(project_id,order_no) VALUES(:p,'演示订单-001')"),{'p':pid}).lastrowid
        for name,amount in [('市场部',100),('采购部',900)]:
            lid=conn.execute(text("INSERT INTO order_line(sales_order_id,source_preserved,line_department,goods_name,order_value,line_order_date,line_order_date_initialized,profit_inputs_initialized,source_order_value_precise,source_purchase_amount_precise,profit_tax_amount,profit_tax_refund) VALUES(:o,1,:d,'演示商品',:v,'2026-09-29',1,1,:v,:purchase,0,0)"),{'o':oid,'d':name,'v':amount,'purchase':amount/2}).lastrowid
            conn.execute(text('INSERT INTO purchase_info(order_line_id,purchase_amount) VALUES(:l,:v)'),{'l':lid,'v':amount/2})
import uvicorn
uvicorn.run('app.main:app',host='127.0.0.1',port=8019,log_level='warning')
