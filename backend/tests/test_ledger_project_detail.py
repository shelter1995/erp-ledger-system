from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text

from app.routers import summaries
from app.authorization import route_permissions
from app.db import db
from test_accounts_v2 import admin_v2
from test_permission_routes_v2 import actor, seed_mixed


@pytest.fixture
def detail_db(monkeypatch):
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        metadata = 'project_code,project_name,order_no,department,account_manager,customer_unit_name,team_level3_name,order_date,close_status,last_modified_at,order_line_id,goods_name,specification_model,quantity,unit_name,supplier_name'
        conn.execute(text('CREATE TABLE v_order_line_finance (' + ','.join(f'{c} TEXT' for c in metadata.split(',') + list(summaries.AMOUNTS)) + ')'))
        for index, (code, order, department, amount, date) in enumerate([
            ('P_1', 'SO-1', 'A', 100, '2026-01-01'),
            ('P_1', 'SO-2', 'A', 200, '2026-09-01'),
            ('P_1', 'SO-3', 'B', 900, '2026-09-02'),
            ('PX1', 'OTHER', 'A', 800, '2026-09-03'),
        ]):
            conn.execute(text("INSERT INTO v_order_line_finance(project_code,project_name,order_no,department,order_value,order_date,accounts_receivable,gross_profit,order_line_id,goods_name,specification_model,quantity,unit_name,supplier_name) VALUES(:code,'项目',:order,:department,:amount,:date,10,7,:index,:order,'型号甲','1.234567','套','厂商甲')"), locals())
    @contextmanager
    def fake_db():
        with engine.connect() as conn:
            yield conn
    monkeypatch.setattr(summaries, 'db', fake_db)
    yield
    engine.dispose()


def reader(scope='selected', permissions=None):
    return SimpleNamespace(role_code='viewer', permissions=permissions or ['ledger_view'], account_type='department_user', scope_mode=scope, department_scope=['A'], department_can_view=True)


def test_detail_material_lines_stay_with_order_and_department(detail_db):
    item = summaries.ledger_project_detail('P_1', reader(permissions=['ledger_view', 'order_view']))
    assert [o['lines'][0]['goods_name'] for o in item['orders']] == ['SO-1', 'SO-2']
    line = item['orders'][0]['lines'][0]
    assert line['specification_model'] == '型号甲'
    assert line['quantity'] == '1.234567'
    assert line['unit_name'] == '套'
    assert line['supplier_name'] == '厂商甲'
    assert line['order_value'] == '100.00'
    assert 'order_line_id' not in line
    assert all('lines' not in o for o in summaries.ledger_project_detail('P_1', reader())['orders'])


def test_detail_gets_all_project_orders_with_exact_code_and_department_scope(detail_db):
    item = summaries.ledger_project_detail('P_1', reader())
    assert [o['order_no'] for o in item['orders']] == ['SO-1', 'SO-2']
    assert item['order_value'] == '300.00'
    assert item['order_date'] == '2026-09-01'
    assert item['orders'][0]['order_date'] == '2026-01-01'
    assert item['gross_profit'] == '14.00'
    assert item['order_count'] == 2
    assert 'order_line_id' not in str(item)
    assert route_permissions('/api/ledgers/project-detail', 'GET') == {'ledger_view'}


def test_detail_missing_or_outside_scope_is_404(detail_db):
    for code, user in [('missing', reader()), ('P_1', reader('none'))]:
        with pytest.raises(HTTPException) as exc:
            summaries.ledger_project_detail(code, user)
        assert exc.value.status_code == 404


def test_list_filters_still_apply_and_list_dto_is_unchanged(detail_db):
    with summaries.db() as conn:
        item = summaries.read_summary(conn, reader(), {'order_id': '', 'start_date': '2026-08-01', 'project_code_exact': 'P_1'})['items'][0]
    assert item['order_count'] == 1
    assert 'order_date' not in item


def test_detail_http_mysql_all_orders_scope_and_permission(client, admin_v2):
    with db() as conn:
        a, b, ids = seed_mixed(conn)
        _, headers = actor(conn, 'detail_reader', ['ledger_view'], [a])
        _, line_headers = actor(conn, 'detail_line_reader', ['ledger_view', 'order_view'], [a])
        _, denied = actor(conn, 'detail_without_ledger', ['order_view'], [a])
        project = conn.execute(text("SELECT id FROM project WHERE project_code='AUTH-MIX'")).scalar_one()
        order = conn.execute(text("INSERT INTO sales_order(project_id,order_no) VALUES(:p,'SECOND-ORDER')"), {'p': project}).lastrowid
        conn.execute(text("INSERT INTO order_line(sales_order_id,source_preserved,line_department,order_value,line_order_date,goods_name) VALUES(:o,1,'权限甲部',200,'2026-01-01','第二订单货物')"), {'o': order})
    filtered = client.get('/api/ledgers/summary', params={'order_id': 'SECOND-ORDER'}, headers=headers)
    assert filtered.status_code == 200
    assert filtered.json()['items'][0]['order_count'] == 1
    response = client.get('/api/ledgers/project-detail', params={'project_code': 'AUTH-MIX'}, headers=headers)
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail['order_count'] == 2
    assert detail['order_value'] == '300.00'
    assert {o['order_no'] for o in detail['orders']} == {'AUTH-ORDER', 'SECOND-ORDER'}
    assert detail['order_date'] == '2026-09-29'
    assert '权限乙部' not in response.text
    assert all('lines' not in o for o in detail['orders'])
    expanded = client.get('/api/ledgers/project-detail', params={'project_code': 'AUTH-MIX'}, headers=line_headers)
    assert expanded.status_code == 200, expanded.text
    assert [o['lines'][0]['goods_name'] for o in expanded.json()['orders']] == ['测试货物', '第二订单货物']
    assert [len(o['lines']) for o in expanded.json()['orders']] == [1, 1]
    assert client.get('/api/ledgers/project-detail', params={'project_code': 'AUTH-MIX'}, headers=denied).status_code == 403
    assert client.get('/api/ledgers/project-detail', params={'project_code': 'AUTH'}, headers=headers).status_code == 404
