from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from app.authorization import can_manage, route_permissions, validate_policy, scope_contains


def test_empty_selected_scope_is_rejected():
    with pytest.raises(HTTPException):
        validate_policy('department_user', 'selected', [], ['ledger_view'], 'self', 1)
    assert not scope_contains('selected', [1], 'all', [])


def test_global_mutations_require_all_scope():
    with pytest.raises(HTTPException):
        validate_policy('department_user', 'selected', [1], ['maintenance_view', 'data_replace'], 'self', 1)


def test_summary_does_not_require_purchase_details_but_full_export_does():
    assert route_permissions('/api/ledgers', 'GET') == {'ledger_view'}
    assert route_permissions('/api/purchases/12', 'GET') == {'purchase_view'}
    assert 'purchase_view' in route_permissions('/api/orders/export', 'GET')
    assert 'purchase_view' in route_permissions('/api/history/export', 'GET')


def test_account_delegate_cannot_grant_self_or_admin_capability():
    actor = SimpleNamespace(id=1, account_type='department_user', permissions=['ledger_view', 'accounts_view'],
                            scope_mode='selected', department_ids=[1], log_scope='self')
    target = dict(id=2, account_type='department_user', permissions=['ledger_view'], scope_mode='selected', department_ids=[1], log_scope='self')
    assert can_manage(actor, target)
    assert not can_manage(actor, dict(target, id=1))
    assert not can_manage(actor, dict(target, department_ids=[2]))
    assert not can_manage(actor, dict(target, permissions=['accounts_view']))
    assert not can_manage(actor, dict(target, account_type='super_admin'))
