# 部门与账号权限 Implementation Plan

> **For agentic workers:** Implementation is authorized. Execute inline using executing-plans; no delegation, commit, push or deployment is implied. Track verification below.

**Goal:** 实现已确认的部门隔离、模块授权、管理页面和密码生命周期。
**Architecture:** 在现有 FastAPI/React 上增加显式授权模型，复用业务写入和汇总口径；旧账号通过离线核对映射切换，禁止启动自动扩权。
**Tech Stack:** FastAPI、SQLAlchemy/MySQL、React/TypeScript、pytest、Node test/tsx。

## 1. 授权模型和迁移
- [x] 新建 backend/app/authorization.py 与 backend/app/authorization_migration.py，定义权限目录、范围、委派规则、DDL 与显式映射。
- [x] 新建 backend/tests/test_authorization_v2.py：验证空范围拒绝、super_admin 全权、仅日志不绕过部门、委派不能提权。
- [x] 修改 backend/app/auth.py：映射新账号、令牌版本、强制改密、未迁移账号拒绝登录；不改变旧迁移撤权语义。
- [x] 新建 tools/account_permissions.py：report 只读、prepare 建结构、apply 校验摘要和超级管理员后事务映射；不输出密码材料。
- [x] 验证：backend/.venv/Scripts/python.exe -m pytest backend/tests/test_authorization_v2.py -q。

## 2. 账号、部门和密码
- [x] 修改 backend/app/routers/auth.py 转向 accounts.py，建立 12–128 字符密码、自助改密、超级管理员重置、账号生命周期与授权约束。
- [x] 新建 backend/app/routers/departments.py 与 backend/app/account_service.py；稳定部门 ID、别名、选项范围、最后超级管理员锁。
- [x] 新建 backend/tests/test_accounts_v2.py，覆盖临时会话、撤权、停用恢复、部门改名、账号委派反例。
- [x] 使用 erp_ledger_test_ 前缀库与临时备份根运行 MySQL 测试；没有可用服务时记录阻塞并完成纯测试。

## 3. 全接口授权与汇总
- [x] 核对 routers/orders.py、sales.py、purchases.py、ledgers.py、dashboard.py、history.py、system.py、import_batches.py 的全部路由，统一拦截模块与高权限操作。
- [x] 修改 backend/app/db.py、write_guard.py：事务内复验身份版本并保持一致锁顺序；业务转移校验所有有效来源部门。
- [x] 新增台账汇总导出、仪表盘 DTO，移除前端跨模块预加载依赖；完整导出需全部明细读取权限。
- [x] 修改 audit.py：结构化部门快照；日志范围不明只允许 all。备份恢复核对目录，维护替换只允许 all。
- [x] 新建 backend/tests/test_permission_routes_v2.py，验证采购关闭仍有汇总、越权详情 404、跨部门批量全回滚、写事务前撤权拒绝提交。

## 4. 前端权限与页面
- [x] 修改 src/lib/permissions.ts、src/api.ts，提供账号类型、目录、范围和模块能力。
- [x] 新增 src/components/AccountPermissionsScreen.tsx、ProfileScreen.tsx；账号矩阵和自助改密。
- [x] 拆分系统导航为 maintenance/accounts/logs/backups；src/App.tsx 按权限/页面加载，失效令牌清空数据。
- [x] 用 SummaryLedgerScreen.tsx 替换原台账页面，并修改 DashboardScreen.tsx：汇总独立读取、明细按模块授权、汇总导出独立。
- [x] 增加 tests/account-permissions.test.ts 和页面测试，执行 node --import tsx --test tests/*.test.ts、npm run lint、npm run build。

## 5. 回归与交付
- [x] 跑授权/迁移/导入/财务/历史/备份相关后端回归，修复本次引入的问题；明确旧规则变更导致的测试更新。
- [x] 完成浏览器多账号验证，记录真实运行与模拟测试的不同范围。
- [x] 在 docs/账号权限本地实施与上线步骤.md 写当前结果、账号 report/prepare/apply 手动步骤、备份和回滚要求；不执行真实账号映射。
- [x] git diff --check；逐项对照设计 14 条反例，不把未验证步骤标成完成。

## 执行记录

- 2026-09-29：用户确认书面设计并授权实施，执行方法为当前会话逐项实现。开始基线 e510e50，已跟踪文件干净；保留所有原有未跟踪产物。

- 已完成：重点后端 78 项、前端 50 项通过；TypeScript 与前端构建通过。新增最后管理员并发降级、写入前撤权和业务恢复不回退授权的反例。
- 浏览器使用独立 erp_ledger_test_auth_browser_20260929：管理员页面、部门汇总隔离、关闭采购入口、强制改密入口均已核对；真实账号与服务器未操作。
- 回归适配：旧账号夹具改用显式 v2 配置并通过 API 完成初次改密；目录加入测试样例部门；越权对象返回 404；旧重置密码后立即导出的预期改为必须先改密。没有增加生产旧权限回退。

- 最终：全量 459 通过、1 个新增恢复测试夹具失败、2 个未配置真实 Excel 输入的可选用例跳过；修正夹具后最终专项 10/10 通过，覆盖最后订单选项响应修正及 3 个新增/修正边界。当前 465 个测试中，合并去重有 463 个通过证据、2 个跳过；不是单次全量全绿结果。
- 设计反例 6、14 已补充实测：预览成功后撤权提交返回 401 且零业务写入；未知部门恢复返回 422 且保留当前业务；业务恢复不更改已撤销权限、auth_version 或部门关联。
- 路由盘点 95 项，没有漏认证或漏模块分类的 API；最终类型检查、构建、diff 空白检查通过。真实账号清单/生产切换按交付手册单独执行。
