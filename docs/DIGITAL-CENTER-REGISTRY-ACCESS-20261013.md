# 数字中心：注册标识、集团映射与权限管理

日期：2026-10-13。风险等级 T3。注册标识、员工分组、权限管理与个人订阅隔离已发布测试与正式环境（7463cc53ef2f）。公司映射冲突修正目标回归完成，补丁发布待执行。

## 行为与边界

- 个人订阅从首页排除；服务端只允许登记本人、系统管理员与资产管理员查看。历史共享、负责人、使用人、附件、导出、资产地图、用量连接和规则不能绕过此限制。公司订阅的 NULL 来源兼容保留。
- 原“手机号与邮箱”改为“注册与登录标识”，覆盖手机号、邮箱、用户名等。按实际保管员工分组，显示部门和数量，可展开/收起；没有保管员工的资料归入部门共用/待补保管人。搜索、名称修改与回收站保持分组。
- 管理员可修改标识显示名称，原标识、UUID、平台引用不改写。删除进入可恢复回收站；仍被有效账号或资产引用时阻止删除并说明原因。恢复保留历史档案，不增加审核。
- 归属候选来自已登记主体与当前集团通讯录，排除历史部门与公司节点。选择集团部门保持账号的业务公司，不移动员工或部门的通讯录身份；已生效责任阻止跨公司直接改写。来源明确的公司可通过“映射集团公司”登记，无工商核验或股权层级推断。
- 公司映射逐项保留归档、停用或重复档案，无冲突的公司可正常映射。页面持续列出待核实项；同名归档档案不会被自动恢复，映射结果与冲突均进入幂等审计。
- “组织与授权 → 权限管理”仅系统管理员可用。可管理已登录员工的预置角色、暂停/恢复本系统访问、直接资源查看授权。通讯录派生角色显示来源并保持只读；暂停撤销现有会话，恢复需重新登录；保护最后一位有效系统管理员。
- 授权操作要求原因、当前修订、幂等键与 CSRF；角色撤销不会在下次登录时被启动逻辑重授。本次只实现能力，不操作真实员工权限、访问停用、标识删除或名称表单。

## 验证证据

- 权限/组织领导/会话隔离：一次性 PostgreSQL 32 项通过，`.local/subscription-verification/7fc28f1b9e/pytest.log`；集群已停止。
- 首轮业务回归 119 项：116 通过，3 项测试准备不匹配；资产库断言补清单参数，附件补类型，管理员上下文改用真实服务端解析。
- 修正并增加历史负责人、地图边端点与可见子账号计数后，注册标识/组织映射/个人隐私/可见性 25 项通过，`.local/subscription-verification/6b772eb8c8/pytest.log`；集群已停止。分批结果不表述为单次全量通过。
- Vue 类型检查与 Vite 构建、最终改动 Python Ruff F/I 与 diff 检查通过；保留原有大包提示。
- 发现生产同名归档公司导致整批中止后，新增归档、来源 UUID 已归档、停用、重复档案四种用例；组织与标识目标回归 10 项通过，`.local/subscription-verification/beb1939736/pytest.log`，一次性 PostgreSQL 已停止。补丁 Vue 类型/生产构建及 Python Ruff F/I、diff 检查通过。
- 真实员工授权、名称更改、删除恢复和整体业务 UAT 由用户或指定验收人确认；自动验证与技术页面回读不代替人工业务验收。

## 改动文件

后端 API：`router.py`、`assets.py`、`workspace.py`、`organizations.py`、`permission_management.py`、`asset_space.py`、`asset_activity.py`、`usage.py`、`usage_monitoring.py`、`dingtalk.py`、`employee_lifecycle.py`。

服务/契约：`personal_subscription_policy.py`、`organization_mapping.py`、`permission_management.py`、`organization_leadership.py`、`relationship_choices.py`、`contact_resources.py`、`assets.py`、`core/access.py`，以及 workspace/organizations/permission_management schemas。

前端：`ContactResourcesPanel.vue`、`PermissionManagementPanel.vue`、`api.ts`、`AccountsPage.vue`、`OrganizationPage.vue`、`IntakePage.vue`、`AssetDetailPage.vue`。

回归：`test_registration_organization_management.py`、`test_permission_management.py`、`test_personal_subscription_privacy.py`、`test_asset_visibility.py`。

## 发布与回滚

以线上 `04e43ba48e8a4ae3b6143d9fee21de0c50bdd6f3` 为基线；无 Schema 迁移。沿用已授权的测试→正式发布，冻结增量逐字节验证，75 张业务表发布前后内容指纹、数据库备份、旧代码和静态回退方案保留。测试环境演练回退再应用并核对正式环境未受影响；正式环境回退或数据库恢复没有执行则不声明通过。

实际公司映射作为独立资料操作记录，不能并入代码发布的表内容保持结论。

7463cc53ef2f 测试云助手 t-hz06zvu16iba2v4、正式云助手 t-hz06zvymr7b19mo 均 exit 0/PASS，75 张业务表与 Schema 保持。测试回退再应用通过。独立公开回读核对两个环境元数据、8 个静态文件、7 条 SPA 路径和 11 个匿名 API 拒绝；测试页面 10 项读取检查通过。正式注册标识读取 73 条 / 11 组，姓名搜索、首页排除、权限来源读取通过；未更改真实员工权限。

首次正式“映射集团公司”因同名归档公司返回 409，整批事务回滚，不计为成功；只读云助手 t-hz06zw2421eyqrk 确认唯一冲突为飞将体育科技（宁波）有限公司的 COL-L1-002 旧档案，归档于 2026-08-31。保留历史资料，是否恢复待用户确认；其余映射在补丁发布后执行并独立回读。
