"""Resolve historical source rows that predate mandatory project codes.

The source workbook remains authoritative: this module only supplies the
relational project identity required by the current schema.  The caller keeps
the original blank cell in the raw source archive.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Connection


TEMPORARY_PROJECT_PREFIX = "临时待补-"
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]+")


@dataclass(frozen=True)
class ProjectResolution:
    project_code: str
    message: str | None = None


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _readable_goods_name(value: object) -> str:
    value = _CONTROL_CHARACTERS.sub(" ", _clean_text(value))
    return " ".join(value.split()) or "未命名设备"


def _order_digest(order_no: str) -> str:
    return hashlib.sha256(order_no.encode("utf-8")).hexdigest().upper()


def _temporary_code(order_no: str, goods_name: object, digest_length: int = 8) -> str:
    suffix = _order_digest(order_no)[:digest_length]
    fixed = f"{TEMPORARY_PROJECT_PREFIX}等项目-{suffix}"
    readable = _readable_goods_name(goods_name)
    readable = readable[: max(1, 64 - len(fixed))]
    return f"{TEMPORARY_PROJECT_PREFIX}{readable}等项目-{suffix}"


def _project_code_exists(conn: Connection, project_code: str) -> bool:
    return bool(
        conn.execute(
            text("SELECT 1 FROM project WHERE project_code=:project_code LIMIT 1"),
            {"project_code": project_code},
        ).scalar()
    )


def _new_temporary_code(
    conn: Connection,
    order_no: str,
    goods_name: object,
    reserved_codes: set[str],
) -> str:
    for digest_length in range(8, 65, 4):
        candidate = _temporary_code(order_no, goods_name, digest_length)
        if candidate not in reserved_codes and not _project_code_exists(conn, candidate):
            reserved_codes.add(candidate)
            return candidate
    raise ValueError(f"订单号 {order_no} 无法生成唯一的临时项目编号")


def _current_order_projects(conn: Connection, order_no: str) -> list[dict]:
    return [
        dict(row)
        for row in conn.execute(
            text(
                """
                SELECT DISTINCT p.id, p.project_code
                FROM sales_order so
                JOIN project p ON p.id=so.project_id
                WHERE so.order_no=:order_no
                  AND so.deleted_at IS NULL
                  AND p.deleted_at IS NULL
                ORDER BY p.id
                """
            ),
            {"order_no": order_no},
        ).mappings()
    ]


def _historical_order_projects(conn: Connection, order_no: str) -> list[dict]:
    return [
        dict(row)
        for row in conn.execute(
            text(
                """
                SELECT DISTINCT p.id, p.project_code, so.id AS sales_order_id, so.order_no AS current_order_no
                FROM sales_order_number_history h
                JOIN sales_order so ON so.id=h.sales_order_id
                JOIN project p ON p.id=so.project_id
                WHERE h.order_no=:order_no
                  AND so.deleted_at IS NULL
                  AND p.deleted_at IS NULL
                ORDER BY p.id, so.id
                """
            ),
            {"order_no": order_no},
        ).mappings()
    ]


def _is_generated_temporary_code(project_code: str, order_no: str) -> bool:
    if not project_code.startswith(TEMPORARY_PROJECT_PREFIX):
        return False
    digest = _order_digest(order_no)
    return any(project_code.endswith(f"-{digest[:length]}") for length in range(8, 65, 4))


def _temporary_order_id(conn: Connection, project_id: int, order_no: str) -> int:
    orders = conn.execute(
        text(
            """
            SELECT id, order_no, deleted_at
            FROM sales_order
            WHERE project_id=:project_id
            ORDER BY id
            """
        ),
        {"project_id": project_id},
    ).mappings().all()
    if len(orders) != 1 or orders[0]["deleted_at"] is not None or orders[0]["order_no"] != order_no:
        raise ValueError(
            f"订单号 {order_no} 对应的临时项目已经包含其他订单或历史记录，不能自动归入正式项目"
        )
    order_id = int(orders[0]["id"])
    if conn.execute(
        text("SELECT 1 FROM sales_order_number_history WHERE sales_order_id=:order_id LIMIT 1"),
        {"order_id": order_id},
    ).scalar():
        raise ValueError(f"订单号 {order_no} 已有改号历史，不能自动归入正式项目")
    if conn.execute(
        text("SELECT 1 FROM project_manager_history WHERE project_id=:project_id LIMIT 1"),
        {"project_id": project_id},
    ).scalar():
        raise ValueError(f"订单号 {order_no} 对应的临时项目已有负责人历史，不能自动归入正式项目")
    return order_id


def _rewrite_derived_project_code(conn: Connection, project_id: int, project_code: str) -> None:
    conn.execute(
        text(
            """
            UPDATE ledger_raw_row r
            JOIN order_line ol ON ol.raw_row_id=r.id
            JOIN sales_order so ON so.id=ol.sales_order_id
            SET r.project_code=:project_code
            WHERE so.project_id=:project_id
            """
        ),
        {"project_id": project_id, "project_code": project_code},
    )


def _reconcile_official_code(conn: Connection, official_code: str, order_no: str) -> str | None:
    matches = _current_order_projects(conn, order_no)
    official = conn.execute(
        text("SELECT id, deleted_at FROM project WHERE project_code=:project_code LIMIT 1"),
        {"project_code": official_code},
    ).mappings().first()
    if official and official["deleted_at"] is not None:
        raise ValueError(f"正式项目编号 {official_code} 已被停用，不能自动恢复或合并")
    official_id = int(official["id"]) if official else None
    temporary_matches = [
        row for row in matches
        if int(row["id"]) != official_id
        and _is_generated_temporary_code(row["project_code"], order_no)
    ]
    # A supplied B column remains authoritative.  The same order number may
    # legitimately exist under multiple formal framework projects; only a
    # system-generated temporary project is eligible for reconciliation.
    if not temporary_matches:
        return None
    if len(temporary_matches) != 1:
        codes = "、".join(row["project_code"] for row in temporary_matches)
        raise ValueError(f"订单号 {order_no} 对应多个临时项目（{codes}），不能自动改归属")

    temporary = temporary_matches[0]
    temporary_id = int(temporary["id"])
    order_id = _temporary_order_id(conn, temporary_id, order_no)
    historical = _historical_order_projects(conn, order_no)
    if any(int(row["sales_order_id"]) != order_id for row in historical):
        raise ValueError(f"订单号 {order_no} 已被其他订单作为历史编号占用，不能自动归入正式项目")

    if official_id is None:
        _rewrite_derived_project_code(conn, temporary_id, official_code)
        conn.execute(
            text("UPDATE project SET project_code=:official_code WHERE id=:project_id"),
            {"official_code": official_code, "project_id": temporary_id},
        )
        return f"订单号 {order_no} 的临时项目已升级为正式项目 {official_code}"

    if any(int(row["id"]) == official_id for row in matches):
        raise ValueError(f"正式项目 {official_code} 已存在订单号 {order_no}，不能自动合并重复订单")
    if conn.execute(
        text(
            """
            SELECT 1 FROM sales_order_number_history h
            JOIN sales_order so ON so.id=h.sales_order_id
            WHERE so.project_id=:project_id AND h.order_no=:order_no
            LIMIT 1
            """
        ),
        {"project_id": official_id, "order_no": order_no},
    ).scalar():
        raise ValueError(f"订单号 {order_no} 已是正式项目 {official_code} 中其他订单的历史编号")

    _rewrite_derived_project_code(conn, temporary_id, official_code)
    conn.execute(
        text("UPDATE sales_order SET project_id=:official_id WHERE id=:order_id"),
        {"official_id": official_id, "order_id": order_id},
    )
    conn.execute(text("DELETE FROM project WHERE id=:project_id"), {"project_id": temporary_id})
    return f"订单号 {order_no} 的临时项目已安全归入正式项目 {official_code}"


def resolve_project_code(
    conn: Connection,
    *,
    project_code: object,
    order_no: object,
    first_goods_name: object,
    reserved_codes: set[str],
    reconcile_temporary: bool = True,
) -> ProjectResolution:
    """Return the effective project code for one M-column order group."""
    official_code = _clean_text(project_code)
    normalized_order_no = _clean_text(order_no)
    if not normalized_order_no:
        raise ValueError("缺少销售订单号")

    if official_code:
        if not reconcile_temporary:
            temporary_matches = [
                row for row in _current_order_projects(conn, normalized_order_no)
                if _is_generated_temporary_code(row["project_code"], normalized_order_no)
            ]
            if temporary_matches:
                raise ValueError(
                    f"订单号 {normalized_order_no} 在本次文件中对应多个正式项目，"
                    "且已有临时项目，不能判断应归入哪个正式项目"
                )
            return ProjectResolution(official_code)
        message = _reconcile_official_code(conn, official_code, normalized_order_no)
        return ProjectResolution(official_code, message)

    matches = _current_order_projects(conn, normalized_order_no)
    historical = _historical_order_projects(conn, normalized_order_no)
    if any(row["current_order_no"] != normalized_order_no for row in historical):
        codes = "、".join(sorted({row["project_code"] for row in historical}))
        raise ValueError(
            f"订单号 {normalized_order_no} 已作为历史编号存在于项目 {codes}，不能按 M 列自动归并"
        )
    if len(matches) > 1:
        codes = "、".join(row["project_code"] for row in matches)
        raise ValueError(f"订单号 {normalized_order_no} 已分布在多个项目（{codes}），无法按 M 列自动归并")
    if matches:
        code = matches[0]["project_code"]
        return ProjectResolution(code, f"B列为空：订单号 {normalized_order_no} 归入现有项目 {code}")

    code = _new_temporary_code(conn, normalized_order_no, first_goods_name, reserved_codes)
    return ProjectResolution(code, f"B列为空：订单号 {normalized_order_no} 使用临时项目编号 {code}")
