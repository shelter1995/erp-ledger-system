from contextlib import contextmanager
from types import SimpleNamespace

from app.routers import summaries


def user(**changes):
    fields = dict(role_code='viewer', permissions=['order_view'], account_type='department_user',
                  scope_mode='selected', department_scope=['部门A'], department_can_view=True)
    fields.update(changes)
    return SimpleNamespace(**fields)


def test_latest_modified_uses_department_scope_and_explicit_timezone(monkeypatch):
    calls = []
    class Connection:
        def execute(self, sql, params):
            calls.append((str(sql), params))
            return SimpleNamespace(scalar=lambda: '2026-09-30 11:57:14.000000')
    @contextmanager
    def fake_db():
        yield Connection()
    monkeypatch.setattr(summaries, 'db', fake_db)
    assert summaries.latest_modified(user()) == {'latestModifiedAt': '2026-09-30T11:57:14+08:00'}
    assert 'MAX(f.last_modified_at)' in calls[0][0]
    assert 'f.department IN' in calls[0][0]
    assert calls[0][1] == {'scope_department_0': '部门A'}


def test_management_only_user_does_not_query_business_data(monkeypatch):
    monkeypatch.setattr(summaries, 'db', lambda: (_ for _ in ()).throw(AssertionError('must not query')))
    assert summaries.latest_modified(user(permissions=['accounts_view'])) == {'latestModifiedAt': ''}


def test_empty_scope_is_filtered_and_null_timestamp_stays_empty(monkeypatch):
    class Connection:
        def execute(self, sql, params):
            assert '1=0' in str(sql)
            return SimpleNamespace(scalar=lambda: None)
    @contextmanager
    def fake_db():
        yield Connection()
    monkeypatch.setattr(summaries, 'db', fake_db)
    assert summaries.latest_modified(user(scope_mode='none', department_scope=[])) == {'latestModifiedAt': ''}
