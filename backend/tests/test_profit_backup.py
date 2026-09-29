from decimal import Decimal
import gzip
import json

from app.db import db
from app.profit_calculations import PROFIT_COLUMNS
from sqlalchemy import text
from test_profit_formula import import_profit_rows
from test_backup_integrity import backup_file, rewrite


def test_old_backup_recovers_profit_inputs_and_new_backup_preserves_corrections(client, headers):
    import_profit_rows(client, headers, [(100, 40, 8, 3, 999999)])
    backup_id, path = backup_file(client, headers)
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        payload = json.load(stream)
    for row in payload['tables']['order_line']:
        for column in PROFIT_COLUMNS:
            row.pop(column)
    rewrite(path, payload)
    response = client.post(f'/api/backups/{backup_id}/restore', headers=headers)
    assert response.status_code == 200, response.text
    assert client.get('/api/dashboard/summary', headers=headers).json()['grossProfit'] == '55.00'
    with db() as conn:
        conn.execute(text('UPDATE order_line SET profit_tax_amount=10'))
    backup_id, _ = backup_file(client, headers)
    response = client.post(f'/api/backups/{backup_id}/restore', headers=headers)
    assert response.status_code == 200, response.text
    assert client.get('/api/dashboard/summary', headers=headers).json()['grossProfit'] == '53.00'


def test_blank_source_taxes_are_zero_and_negative_refunds_are_retained(client, headers):
    rows = import_profit_rows(client, headers, [(100, 40, None, None, 999), (100, 40, -8, -3, 999)])
    assert sorted(Decimal(row['gross_profit']) for row in rows) == [Decimal('60'), Decimal('65')]
