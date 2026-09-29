"""Explicit operator workflow. Never prints password hashes or credentials."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.db import engine
from app.config import settings
from app.authorization_migration import account_inventory, prepare_schema, apply_mapping


def main():
    parser = argparse.ArgumentParser(description='账号权限迁移：report 只读盘点，prepare 增加结构，apply 使用已核对映射')
    parser.add_argument('action', choices=['report', 'prepare', 'apply'])
    parser.add_argument('--file', type=Path)
    parser.add_argument('--database', required=True, help='必须与连接配置数据库名一致，防止误操作')
    args = parser.parse_args()
    if args.database != settings.mysql_database:
        parser.error('目标数据库名与环境配置不一致')
    if args.action in {'report', 'apply'} and not args.file:
        parser.error('report/apply 必须指定 --file')
    with engine.begin() as conn:
        if args.action == 'report':
            report = account_inventory(conn)
            # Never overwrite an operator-reviewed mapping.
            with args.file.open('x', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        elif args.action == 'prepare':
            prepare_schema(conn)
        else:
            apply_mapping(conn, json.loads(args.file.read_text(encoding='utf-8')))
    print(f'{args.action} 完成；目标数据库：{args.database}')


if __name__ == '__main__':
    main()
