import json
from io import BytesIO
from openpyxl import load_workbook
from sqlalchemy import text
from app.auth import hash_password, user_from_row, create_access_token
from app.db import db
from test_accounts_v2 import admin_v2


def directory(conn, name):
    found=conn.execute(text('SELECT department_id FROM department_alias WHERE name=:n'), {'n':name}).scalar()
    if found:
        return found
    result=conn.execute(text('INSERT INTO department(name) VALUES(:n)'), {'n':name})
    conn.execute(text('INSERT INTO department_alias(name,department_id) VALUES(:n,:d)'), {'n':name,'d':result.lastrowid})
    return result.lastrowid


def actor(conn, name, permissions, departments, *, scope='selected', log_scope='self'):
    # Unique per test; mapped identities exercise the production auth path.
    result=conn.execute(text("INSERT INTO erp_user(username,password_hash,display_name,role_code,account_type,scope_mode,permissions_json,home_department_id,log_scope,authorization_version) VALUES(:u,:p,:u,'department_user','department_user',:s,:permissions,:home,:logs,1)"),
                        {'u':name,'p':hash_password('Permission-Test-123'),'s':scope,'permissions':json.dumps(permissions),'home':departments[0] if departments else None,'logs':log_scope})
    uid=result.lastrowid
    for d in departments:
        conn.execute(text('INSERT INTO user_department VALUES(:u,:d)'), {'u':uid,'d':d})
    user=user_from_row(conn,conn.execute(text('SELECT * FROM erp_user WHERE id=:id'),{'id':uid}).mappings().one())
    return uid, {'Authorization':'Bearer '+create_access_token(user)}


def seed_mixed(conn):
    a=directory(conn,'权限甲部');b=directory(conn,'权限乙部')
    p=conn.execute(text("INSERT INTO project(project_code,department) VALUES('AUTH-MIX','权限甲部')")).lastrowid
    so=conn.execute(text("INSERT INTO sales_order(project_id,order_no) VALUES(:p,'AUTH-ORDER')"),{'p':p}).lastrowid
    ids=[]
    for department,amount in [('权限甲部',100),('权限乙部',900),(None,700)]:
        lid=conn.execute(text('INSERT INTO order_line(sales_order_id,source_preserved,line_department,order_value,line_order_date,goods_name) VALUES(:o,1,:d,:v,\'2026-09-29\',\'测试货物\')'),{'o':so,'d':department,'v':amount}).lastrowid
        conn.execute(text('INSERT INTO purchase_info(order_line_id,purchase_amount) VALUES(:id,:v)'),{'id':lid,'v':amount/2})
        ids.append(lid)
    return a,b,ids


def test_department_summary_and_exports_do_not_leak_details(client,admin_v2):
    with db() as conn:
        a,b,ids=seed_mixed(conn)
        _,headers=actor(conn,'summary_reader',['ledger_view','dashboard_view'],[a])
    response=client.get('/api/ledgers/summary',headers=headers)
    assert response.status_code==200,response.text
    data=response.json()
    assert data['metrics']['totalOrderAmount']=='100.00'
    assert data['items'][0]['purchase_amount']=='50.00'
    assert '权限乙部' not in response.text
    assert 'order_line_id' not in response.text
    assert 'supplier_name' not in response.text
    assert client.get('/api/dashboard/data',headers=headers).json()['metrics']['orderCount']==1
    for path in ['/api/purchases','/api/purchases/'+str(ids[0]),'/api/orders/export','/api/history/export','/api/purchases/order-options']:
        assert client.get(path,headers=headers).status_code==403,path
    exported=client.get('/api/ledgers/export-summary',headers=headers)
    assert exported.status_code==200,exported.text
    book=load_workbook(BytesIO(exported.content),data_only=True)
    values=list(book.active.values)
    assert len(values)==2
    assert '50.00' in values[1]
    assert '900.00' not in values[1]


def test_object_scope_batch_rollback_and_transfer_guard(client,admin_v2):
    with db() as conn:
        a,b,ids=seed_mixed(conn)
        uid,headers=actor(conn,'department_editor',['ledger_view','order_view','order_edit','order_delete','purchase_view','department_transfer'],[a])
    assert client.get('/api/purchases/'+str(ids[1]),headers=headers).status_code==404
    assert client.get('/api/history/lines/'+str(ids[1]),headers=headers).status_code==404
    assert client.get('/api/history/lines/'+str(ids[0]),headers=headers).json()['affected_lines']==1
    attempt=client.post('/api/history/transfer-project',headers=headers,json={'order_line_id':ids[0],'expected':{'account_manager':None,'department':'权限甲部','branch_company':None,'team_level3_name':None},'account_manager':'甲','department':'权限甲部','reason':'测试禁止越权'})
    assert attempt.status_code==404,attempt.text
    selected=client.post('/api/orders/batch-editor/rows',json={'order_line_ids':ids[:2]},headers=headers)
    assert selected.status_code==404,selected.text
    with db() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM order_line WHERE deleted_at IS NULL')).scalar()==3
    update=client.put(f'/api/auth/users/{uid}',headers=admin_v2,json={'account_type':'department_user','home_department_id':a,'scope_mode':'selected','department_ids':[a],'permissions':['ledger_view'],'log_scope':'self'})
    assert update.status_code==200,update.text
    assert client.get('/api/ledgers/summary',headers=headers).status_code==401


def test_delegated_account_manager_cannot_escalate_or_reset(client,admin_v2):
    with db() as conn:
        a=directory(conn,'委派甲部');b=directory(conn,'委派乙部')
        uid,headers=actor(conn,'delegate',['accounts_view','accounts_create','accounts_update','accounts_disable','ledger_view'],[a])
    base={'username':'delegated_child','display_name':'子账号','password':'Temporary-Pass-123','account_type':'department_user','home_department_id':a,'scope_mode':'selected','department_ids':[a],'permissions':['ledger_view'],'log_scope':'self'}
    assert client.post('/api/auth/users',json=base,headers=headers).status_code==200
    for changes in [{'username':'escalate_all','scope_mode':'all','department_ids':[]},{'username':'escalate_dept','department_ids':[b]},{'username':'escalate_admin','account_type':'super_admin','scope_mode':'all','department_ids':[]},{'username':'escalate_permission','permissions':['accounts_view']}]:
        assert client.post('/api/auth/users',json={**base,**changes},headers=headers).status_code==403
    assert client.post(f'/api/auth/users/{uid}/reset-password',json={'password':'Reset-Password-123'},headers=headers).status_code==403
    policy={k:v for k,v in base.items() if k not in {'username','display_name','password'}}
    assert client.put(f'/api/auth/users/{uid}',json=policy,headers=headers).status_code==403


def test_renamed_department_matches_historical_rows(client,admin_v2):
    with db() as conn:
        a,b,ids=seed_mixed(conn)
        conn.execute(text("UPDATE department SET name='权限甲部新名' WHERE id=:id"),{'id':a})
        conn.execute(text("INSERT INTO department_alias VALUES('权限甲部新名',:id)"),{'id':a})
        _,headers=actor(conn,'renamed_reader',['ledger_view','purchase_view','sales_view'],[a])
    for endpoint in ['/api/ledgers/summary','/api/ledgers','/api/purchases','/api/sales']:
        result=client.get(endpoint,headers=headers,params={'department':'权限甲部新名'})
        assert result.status_code==200,result.text
        assert len(result.json()['items'])==1,(endpoint,result.text)


def test_log_scope_filters_before_pagination(client,admin_v2):
    from app.audit import write_operation_log
    from app.auth import user_from_row
    with db() as conn:
        a=directory(conn,'日志甲部');b=directory(conn,'日志乙部')
        uid,self_headers=actor(conn,'logs_self',['logs_view'],[a])
        _,dept_headers=actor(conn,'logs_department',['logs_view'],[a],log_scope='department')
        _,all_headers=actor(conn,'logs_all',['logs_view'],[],scope='all',log_scope='all')
        user=user_from_row(conn,conn.execute(text('SELECT * FROM erp_user WHERE id=:id'),{'id':uid}).mappings().one())
        for action,detail in [('own_a',{'department':'日志甲部'}),('own_b',{'department':'日志乙部'}),('cross',{'items':[{'department':'日志甲部'},{'department':'日志乙部'}]}),('unknown',{})]:
            write_operation_log(conn,user,'订单管理',action,action,after=detail)
        write_operation_log(conn,user,'账号安全','password_event','修改密码')
    def names(headers):
        result=client.get('/api/logs',headers=headers,params={'limit':100})
        assert result.status_code==200,result.text
        assert result.json()['total']==len(result.json()['items'])
        return {r['action_name'] for r in result.json()['items']}
    assert names(self_headers)=={'own_a','own_b','password_event'}
    assert names(dept_headers)=={'own_a'}
    assert names(all_headers)=={'own_a','own_b','cross','unknown','password_event'}


def test_revocation_between_request_check_and_write_rejects_commit(client,admin_v2,monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from app import account_service
    from app.edit_versions import request_context
    from test_financial_integration import _payload
    with db() as conn:
        a=directory(conn,'QA')
        uid,headers=actor(conn,'revocation_writer',['order_view','order_entry'],[a])
    reached=threading.Event();resume=threading.Event()
    original=account_service.revalidate_write
    def pause(conn):
        request=request_context.get(None)
        if request and request.url.path=='/api/orders' and getattr(request.state,'current_user',None):
            reached.set()
            assert resume.wait(10)
        return original(conn)
    monkeypatch.setattr(account_service,'revalidate_write',pause)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending=pool.submit(client.post,'/api/orders',json=_payload('AUTH-RACE'),headers=headers)
        try:
            assert reached.wait(10)
            with db() as conn:
                conn.execute(text("UPDATE erp_user SET permissions_json='[]',auth_version=auth_version+1 WHERE id=:id"),{'id':uid})
        finally:
            resume.set()
        response=pending.result(timeout=20)
    assert response.status_code==401,response.text
    with db() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM project WHERE project_code='QA-AUTH-RACE'")).scalar_one()==0


def test_business_restore_keeps_current_authorization(client,admin_v2):
    from app.backup import BACKUP_TABLES
    assert not {'erp_user','department','department_alias','user_department','operation_log'} & set(BACKUP_TABLES)
    with db() as conn:
        a,b,ids=seed_mixed(conn)
        uid,headers=actor(conn,'restore_reader',['ledger_view'],[a])
    # Synthetic source rows already have effective dates and amounts; mark their
    # inputs initialized exactly as a completed real source import does.
    with db() as conn:
        conn.execute(text('UPDATE order_line SET line_order_date_initialized=1,profit_inputs_initialized=1,source_order_value_precise=order_value,source_purchase_amount_precise=order_value/2'))
    backup=client.post('/api/backups',headers=admin_v2)
    assert backup.status_code==200,backup.text
    with db() as conn:
        conn.execute(text("UPDATE erp_user SET permissions_json='[]',auth_version=auth_version+1 WHERE id=:id"),{'id':uid})
        version=conn.execute(text('SELECT auth_version FROM erp_user WHERE id=:id'),{'id':uid}).scalar_one()
    from fastapi.testclient import TestClient
    from app.main import app
    restored=TestClient(app).post('/api/backups/'+str(backup.json()['id'])+'/restore',headers=admin_v2)
    assert restored.status_code==200,restored.text
    with db() as conn:
        row=conn.execute(text('SELECT auth_version,permissions_json FROM erp_user WHERE id=:id'),{'id':uid}).mappings().one()
        assert row['auth_version']==version and row['permissions_json']=='[]'
        assert conn.execute(text('SELECT department_id FROM user_department WHERE user_id=:id'),{'id':uid}).scalar_one()==a
    assert client.get('/api/ledgers/summary',headers=headers).status_code==401


def test_module_order_options_are_scoped_and_do_not_duplicate_all_versions(client,admin_v2):
    with db() as conn:
        a,b,ids=seed_mixed(conn)
        pid=conn.execute(text("INSERT INTO project(project_code,department) VALUES('AUTH-OPTIONS-2','权限甲部')")).lastrowid
        oid=conn.execute(text("INSERT INTO sales_order(project_id,order_no) VALUES(:p,'OPTIONS-2')"),{'p':pid}).lastrowid
        conn.execute(text("INSERT INTO order_line(sales_order_id,goods_name) VALUES(:o,'第二框架')"),{'o':oid})
        _,headers=actor(conn,'options_reader',['sales_view'],[a])
    assert client.get('/api/orders',headers=headers).status_code==403
    response=client.get('/api/sales/order-options',headers=headers)
    assert response.status_code==200,response.text
    assert len(response.json()['items'])==2
    for item in response.json()['items']:
        assert len(item['edit_context']['projects'])==1
        assert str(item['project_id']) in item['edit_context']['projects']
    assert '权限乙部' not in response.text
