from fastapi import HTTPException
from sqlalchemy import text


def department_filter(column, parameter='department'):
    """Match canonical names and their historical aliases without rewriting source rows."""
    return (f"({column}=:{parameter} OR {column} IN ("
            "SELECT aliases.name FROM department_alias aliases "
            "JOIN department_alias selected ON selected.department_id=aliases.department_id "
            f"WHERE selected.name=:{parameter}))")


def validate_name(conn, name, *, canonical=False):
    if not name:
        return name
    row = conn.execute(text('SELECT d.name,d.is_active FROM department_alias a JOIN department d ON d.id=a.department_id WHERE a.name=:n'), {'n': name}).mappings().first()
    if not row or not row['is_active']:
        raise HTTPException(422, f'部门“{name}”未登记或已停用，请先维护部门目录')
    if canonical and row['name'] != name:
        raise HTTPException(422, f'请使用部门当前名称“{row["name"]}”')
    return row['name']


def validate_restore_departments(conn, tables):
    known = set(conn.execute(text('SELECT name FROM department_alias')).scalars())
    names = {r.get('department') for r in tables.get('project', [])} | {r.get('line_department') for r in tables.get('order_line', [])}
    missing = {str(n) for n in names if n} - known
    if missing:
        raise HTTPException(422, '备份包含未登记部门，请先核对目录：' + '、'.join(sorted(missing)))
