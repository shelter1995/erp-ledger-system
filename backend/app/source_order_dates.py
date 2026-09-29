"""Restore per-line order dates from the immutable source-import archive."""
from datetime import datetime
import json

from sqlalchemy import text


def backfill_source_order_dates(conn):
    # A separate marker distinguishes an intentionally blank date from a row
    # awaiting upgrade, and makes retries safe after MySQL's implicit DDL commit.
    from .importer import _as_date

    restored = 0
    while True:
        rows = conn.execute(text('''
            SELECT ol.id, r.raw_json
            FROM order_line ol LEFT JOIN ledger_raw_row r ON r.id=ol.raw_row_id
            WHERE ol.source_preserved=1 AND ol.line_order_date_initialized=0
            ORDER BY ol.id LIMIT 1000
        ''')).mappings().all()
        if not rows:
            return restored
        updates = []
        for row in rows:
            raw = json.loads(row['raw_json']) if row['raw_json'] else {}
            values = raw.get('values', [])
            if len(values) < 6:
                raise ValueError(f"明细 {row['id']} 缺少原表日期归档，不能自动恢复日期")
            value = values[5]
            if isinstance(value, str) and 'T' in value:
                value = datetime.fromisoformat(value)
            updates.append({'id': row['id'], 'order_date': _as_date(value)})
        conn.execute(text('''
            UPDATE order_line SET line_order_date=:order_date,
                line_order_date_initialized=1, updated_at=updated_at
            WHERE id=:id AND line_order_date_initialized=0
        '''), updates)
        restored += len(updates)
