# 注册与登录标识：更正原标识内容

日期：2026-10-14。用户反馈已有标识的手机号/邮箱只读。本次业务修改为 T2；部署按 T3 验证。Schema f13f20261010 保持，无迁移。

## 行为

- 平台与账号 → 注册与登录标识 → 修改资料允许更正手机号、邮箱、用户名、微信及其他账号标识；类型可选择，输入只在保存中临时禁用。
- 修改按原 asset_id 保存；资料 UUID、简短编号和平台账号引用保留，不按更正后的值新增记录。外部平台的真实登录资料不会被改写。
- 手机号统一去掉国家前缀、空格及连接符；邮箱忽略大小写。已有有效记录或回收站记录占用相同标识时返回 409，格式错误返回 422，版本过期或改变幂等请求内容返回 409。
- 系统/资产管理员沿用现有管理范围；普通员工及缺少 CSRF 的 Cookie 写请求被拒绝。保存要求资料来源，不声明短信或邮箱验证。
- 自动生成的名称随更正同步；单独设置的显示名称保留。历史资料未登记公司或保管人时可更正标识，不创建空责任记录，不改写既有责任。
- 新增/批量手机号与邮箱登记仍按值核对；用户名等标识的修改入口不再受手机号/邮箱识别条件限制。

## 验证

- 一次性 PostgreSQL 首轮目标回归 28 项：27 项通过，1 项发现历史空保管人记录的责任约束问题；已修正。证据 `.local/subscription-verification/4188e931ca/pytest.log`，集群已停止。
- 修正后更正路径 11 项全部通过，包括手机号/邮箱格式归一、用户名、原编号/资料 ID/平台账号引用及页面上下文回读、幂等与过期版本、有效/回收站重复、格式错误回滚、旧资料与自定义名称、员工越权、CSRF及已删除记录。证据 `.local/subscription-verification/ff4ec25d95/pytest.log`，集群已停止。
- `npm run build`（Vue 类型检查 + Vite 构建）、改动 Python 文件 Ruff F/I 与 `git diff --check` 通过。原有大包与 Starlette TestClient 提示保留。
- 真正修改员工手机号/邮箱等资料由用户操作；自动回归及页面可编辑状态读取独立于人工业务验收。

## 改动文件

`frontend/src/components/ContactResourcesPanel.vue`、`frontend/src/lib/api.ts`；`backend/app/api/v1/workspace.py`、`backend/app/schemas/workspace.py`、`backend/app/services/contact_resources.py`；`backend/tests/test_registration_identity_edit.py`。

## 发布状态

沿用原测试→正式发布授权；冻结候选、服务器代码/静态字节校验、75 张业务表指纹、测试回退再应用和独立公开/认证页面回读将在实际完成后补录。本段准备状态不代表已发布。
