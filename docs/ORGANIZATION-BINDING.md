# 钉钉组织主体绑定与页面范围

组织架构原先使用名称排序后的法人首项作为表头、树根和同步目标，并合计所有公司的部门/成员。现以服务端可信绑定确定组织范围，法人档案编辑的下拉选择与组织绑定独立。

## 绑定规则

- 优先使用现有 `organization_bootstrap.legal_entity_code` 对应的有效法人；只有没有代码时才使用精确名称。
- 未配置代码/名称的旧环境，仅当未归档的钉钉部门全部关联唯一法人时兼容读取该主体。
- 配置主体不存在、停用或归档时不回退选择另一公司；名称重复、部门链接指向其他主体或多个主体时返回明确问题并关闭同步。
- 已认证 `GET /api/v1/dingtalk/organization` 返回状态、主体 ID/名称/代码及提示，不读取外部钉钉或暴露凭据。
- 现有 `POST /api/v1/dingtalk/sync` 仍需管理员权限；错误或未确定的同步目标在上游调用及写入之前以409拒绝。不存在的请求主体仍404。

组织表头、组织树、部门和成员统计、主管岗位数及成员列表均按同一主体过滤，只有同时归属该主体的部门和人员的活跃部门成员关系纳入展示。法人档案下拉只改变档案查看/编辑目标，不改变组织表头或同步目标。

## 验证与发布

定向后端测试使用回环 PostgreSQL 的隔离合成演练库，事务回退保护既有测试资料；包含名称顺序、兼容绑定、未配置/歧义/停用、错误目标、认证/管理员门槛及 mock 正向同步。前端纯函数验证跨公司、无绑定、活跃关系及输入不变，再运行正式 Vue 类型检查和构建。

本次不需要数据库迁移、真实组织同步或角色调整。测试发布前保存原后端受影响文件和静态版本，核对旧文件哈希及组织数据指纹；只部署 `/test/`。真实钉钉同步与完整角色/业务UAT不由这些自动检查代替。

当前实现和服务器核验结果以配套任务与发布记录为准；未执行的验证不能计为通过。

## 2026-09-29 本地验证证据

- `pytest tests/test_dingtalk_organization.py tests/test_pm_session_security.py`：22项通过；回环55433合成库，schema f13b20260928，本次不依赖新增Schema。
- `node scripts/test-organization-scope.mjs`：9条断言通过。
- 受影响Python文件定向Ruff及 `git diff --check` 通过；`npm --prefix frontend run build` 包含Vue类型检查及正式构建，通过。
- 保留既有构建大块警告与Starlette/httpx弃用警告；没有因本项改动无关依赖或分包。
- Mock同步只验证正向归属及错误目标拒绝；没有执行真实组织同步。

## 2026-09-29 隔离测试交付

fa37442已推送现有融合分支并部署 `/test/`，schema保持f13c20260928。云助手部署t-hz06yhedzziwgzk退出0，6份公网文件与冻结构建哈希一致；健康200，新组织与原资产接口匿名401。受影响旧源码备份已保存，11张组织/档案/配置/角色表指纹、测试环境配置哈希及生产进程/首页基线不变。没有迁移、真实同步或角色变更。

真实会话页面显示杭州飞途行远企业管理有限公司/HZFTXY、40部门、67成员及19主管岗位；树根一致。法人档案切换京跑后组织范围不变，恢复飞途档案；信息技术部5名成员/1名主管和表格行数一致，无页面错误。完整角色/钉钉真机/业务UAT继续单列，本项只关闭组织显示及同步目标保护。

回退文件位于测试服务器 `/opt/account-center-test/releases/fa37442-org-20260929/backup`；原前端a44ac57-web-20260928保留，测试专用operator保存代码回退及生产/当前版本检查。回退未执行，不恢复数据库或修改权限。

## 涉及文件

- 后端：`backend/app/services/dingtalk.py`、`backend/app/api/v1/dingtalk.py`、`backend/app/schemas/dingtalk.py`。
- 前端：`frontend/src/pages/OrganizationPage.vue`、`frontend/src/lib/api.ts`、`frontend/src/lib/organizationScope.ts`。
- 验证/文档：`backend/tests/test_dingtalk_organization.py`、`scripts/test-organization-scope.mjs`、`docs/ORGANIZATION-BINDING.md`。


## 公司与部门的后续分离

上述40个部门是旧页面对钉钉目录节点的计数，包含公司名节点。本次主体绑定修复不等同于所有组织资料核验。公司字段读取、职能部门分类及待核验状态的后续实现见 [公司与部门分离](ORGANIZATION-STRUCTURE.md)。原绑定保护、组织范围与权限边界继续保持。
