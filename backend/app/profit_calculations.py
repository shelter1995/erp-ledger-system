"""Inputs for W - AC - BL + BM; BN is retained only as source evidence."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import json

from sqlalchemy import bindparam, text


PROFIT_COLUMNS = {
    'source_order_value_precise': 'DECIMAL(38,18) NULL',
    'source_purchase_amount_precise': 'DECIMAL(38,18) NULL',
    'profit_tax_amount': 'DECIMAL(38,18) NULL',
    'profit_tax_refund': 'DECIMAL(38,18) NULL',
    'profit_inputs_initialized': 'TINYINT NOT NULL DEFAULT 0',
}


def _amount(value, label):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or abs(amount) >= Decimal('1e16'):
            raise ValueError
        with localcontext() as context:
            context.prec = 50
            return amount.quantize(Decimal('1e-18'), rounding=ROUND_HALF_UP)
    except (ValueError, InvalidOperation):
        raise ValueError(f'{label}必须是有效金额，不能包含公式错误或非数字内容') from None


def profit_inputs_from_archive(raw, *, source_preserved):
    if isinstance(raw, str):
        raw = json.loads(raw)
    raw = raw or {}
    values = raw.get('values')
    if source_preserved and (not isinstance(values, list) or len(values) < 65):
        raise ValueError('原表毛利润计算缺少 W、AC、BL、BM 归档，不能自动升级')

    def get(labels, index):
        if isinstance(values, list):
            return values[index] if index < len(values) else None
        return next((raw[label] for label in labels if label in raw), None)

    tax = _amount(get(('税金',), 63), '税金（BL）')
    refund = _amount(get(('退税',), 64), '退税（BM）')
    return {
        'source_order_value_precise': _amount(values[22], '订单价值（W）') if source_preserved else None,
        'source_purchase_amount_precise': _amount(values[28], '采购金额（AC）') if source_preserved else None,
        # An empty source cell contributes zero. For ordinary rows without an
        # explicit imported BL, retain the existing calculated tax difference.
        'profit_tax_amount': (tax or Decimal(0)) if source_preserved else tax,
        'profit_tax_refund': refund or Decimal(0),
        'profit_inputs_initialized': 1,
    }


def sync_source_profit_amounts(conn, line_ids):
    """After edits, retire the old raw precision rather than reviving it later."""
    ids = sorted(set(line_ids))
    for start in range(0, len(ids), 1000):
        conn.execute(text('''
            UPDATE order_line ol LEFT JOIN purchase_info pi
              ON pi.order_line_id=ol.id AND pi.deleted_at IS NULL
            SET ol.source_order_value_precise=CASE
                  WHEN ROUND(ol.source_order_value_precise,2) <=> ol.order_value
                  THEN ol.source_order_value_precise ELSE ol.order_value END,
                ol.source_purchase_amount_precise=CASE
                  WHEN ROUND(ol.source_purchase_amount_precise,2) <=> pi.purchase_amount
                  THEN ol.source_purchase_amount_precise ELSE pi.purchase_amount END,
                ol.updated_at=ol.updated_at
            WHERE ol.source_preserved=1 AND ol.profit_inputs_initialized=1
              AND ol.id IN :ids
              AND (NOT (ROUND(ol.source_order_value_precise,2) <=> ol.order_value)
                OR NOT (ROUND(ol.source_purchase_amount_precise,2) <=> pi.purchase_amount))
        ''').bindparams(bindparam('ids', expanding=True)), {'ids':ids[start:start+1000]})


def backfill_profit_inputs(conn):
    count = 0
    while True:
        rows = conn.execute(text('''
            SELECT ol.id,ol.source_preserved,r.raw_json FROM order_line ol
            LEFT JOIN ledger_raw_row r ON r.id=ol.raw_row_id
            WHERE ol.profit_inputs_initialized=0 ORDER BY ol.id LIMIT 1000
        ''')).mappings().all()
        if not rows:
            return count
        updates = [{'id':row['id'], **profit_inputs_from_archive(
            row['raw_json'], source_preserved=bool(row['source_preserved']))} for row in rows]
        assignments = ','.join(f'{key}=:{key}' for key in PROFIT_COLUMNS)
        conn.execute(text(f'UPDATE order_line SET {assignments},updated_at=updated_at '
                          'WHERE id=:id AND profit_inputs_initialized=0'), updates)
        sync_source_profit_amounts(conn, [row['id'] for row in rows])
        count += len(rows)
