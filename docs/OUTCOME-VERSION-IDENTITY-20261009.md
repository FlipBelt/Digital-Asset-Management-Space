# 成果版本与登记身份解耦

日期：2026-10-09；状态：本地实现与验证完成，待确切候选上线授权。

## 最终行为

- 用户明确选择：首次确认登记为 V1；以后只有主动勾选“发布新成果版本（功能或交付内容更新）”并核对确认，才发布 V2、V3。
- 保存资料、补截图、改派负责人、重新确认资料、审核、归档或删除仍保留内部修订和审计，不自动产生新的成果版本。
- 内部 `version` 继续用于乐观锁、并发冲突和确切内容确认；新增 `outcome_version` 表达已明确发布的成果版本。草稿为 0，页面显示“待首次登记”。卡片、详情和审核使用成果版本；删除确认中明确标注资料修订号。
- 名称、说明和成果资料修改进入私有待确认草稿；默认重新确认更新当前成果版本的资料。审核不会代替登记人确认或发布。
- 空内容变更及完全相同的责任配置不会增加修订，也不会重置审核。
- AI/网页新成果登记由服务端认证身份确定登记人，同时在同一事务创建真实默认负责人。幂等重试不重复创建，不接受客户端自报身份或版本。
- 管理员（含既有部门治理范围）可改派负责人，登记人不变。真正的负责人可以维护已获分配的私有成果资料，其他成员或责任建议不会获得维护权限。确认登记及发布仍由登记人完成。
- 详情、台账和确认预览分别展示登记人、负责人；AI 提议其他负责人继续等待管理员采纳，不覆盖当前实际责任。
- 默认责任只适用于新登记；不批量覆盖旧资产责任、不修改实际人员或权限配置。

## 迁移与兼容

Alembic `f13d20261008 → f13e20261009` 新增 `assets.outcome_version` 和 `asset_confirmations.outcome_version`。

历史已确认登记统一从成果 V1 延续。未确认新草稿为 0；普通旧公司资源保持原修订展示。旧内部 `version`、创建人、负责人、确认记录及审计不重新编号、不删除。历史修订次数不能证明多个成果发布，因此不将原修订 5/12/13 等转换为成果 V5/V12/V13。

新确认凭证绑定目标成果版本、资料修订、内容摘要、用户及共享范围。同一请求切换目标版本拒绝；取消、过期、草稿变化或伪造目标版本不能发布。机器令牌仍不能调用网页确认路由。

旧的未消费预览在升级后需要重新读取和预览；旧确认回执只有当前结果完全匹配时才能安全重试。迁移不代任何人确认、指派或审核。

代码回退可保留新增字段并回退后端与前端。Schema 降级若发现 V2 以上或有效的新预览则拒绝，避免丢失新成果版本。正式发布应先隔离测试，再生产；备份数据和旧代码/静态目录。当前未执行服务器升级或回退。

## 验证

风险 T3：身份/对象权限、版本状态与 Schema 兼容。

- 一次性本地 PostgreSQL `127.0.0.1:55433/dam_v13_tests_registrar_*` 升级到 f13e 成功；未使用生产数据库。
- 后端 114 项通过（86 + 28）：新版本与身份、迁移、登记器、私有可见性、确认、角色、删除与机器认证回归。7 项新增检查覆盖默认责任、认证身份不可自报、改派、私有维护、新版本明确发布/幂等、取消与过期修订、迁移与安全降级。
- 迁移用独立事务 Schema 演练历史 backfill、旧列读取兼容、阻止有新发布/新预览的降级、允许无新事实的降级。原始修订与确认行保留；事务回滚清除合成 Schema。
- 前端 17 项通过（3 新增 + 14 回归），Vue 类型检查与 Vite 正式构建通过。既有主包超过 500 kB 提示保留，不称性能验收。
- 定向 Ruff 与 `git diff --check` 通过。对既有 `assets.py/hudu.py` 等历史长行只豁免 E501，未格式化整文件。
- 本地浏览器真实组件：登记人/默认负责人独立显示；补资料默认预览 V1；取消后明确选新版本预览 V2；勾选核对后确认并回读“待审核 · 成果 V2”，页面 error 日志为空。全部为合成数据，不代表真人业务验收。
- 预览截图：`.local/outcome-version-identity-preview-20261009.jpg`，1265×712，74094 bytes，SHA-256 `efd3f2ccd9fe08de79f42d40b17f6a4e9cf05cf2e7598b099b607884ba040719`。原始截图字节，未编辑；不随 Git 提交。

执行命令（Python 使用 `backend/.venv/Scripts/python.exe`）：

```powershell
python .local/upgrade_outcome.py
python .local/rerun.py tests/test_outcome_versions.py tests/test_outcome_version_migration.py tests/test_asset_space.py tests/test_registrar_completion.py tests/test_asset_center_integration.py tests/test_asset_visibility.py
python .local/rerun.py tests/test_agent_connector.py tests/test_asset_deletion.py tests/test_pm_session_security.py
```

```powershell
# frontend 工作目录
node --test --test-concurrency=1 tests/outcomeVersions.test.mjs tests/assetUsability.test.mjs tests/assetDeletion.test.mjs
npm run build
```

首次验证发现旧 SimpleNamespace 缺在职字段及责任列表按第 0 项判断建议的假设；已补充真实模型字段，并按 role_type 核对责任建议，相关回归复测通过。

## 修改文件

后端：

- `app/api/v1/asset_space.py`：认证登记与默认负责人。
- `app/api/v1/agent_connector.py`：成果版本、认证登记人回读及不变内容重试。
- `app/api/v1/asset_activity.py`：明确发布选项、目标版本凭证及确认。
- `app/api/v1/assets.py`：责任空变更、归档保护与兼容归属比较。
- `app/api/v1/hudu.py`：成果版本、登记人名称投影。
- `app/core/access.py`：真正负责人的私有资产维护与负向权限。
- `app/models/domain.py`、`app/models/asset_space.py`、`app/schemas/assets.py`：分开的成果版本模型。
- `app/services/asset_confirmation.py`：确切版本及身份预览摘要。
- `app/services/assets.py`、`app/services/registrar_details.py`：资料编辑与不变保存。
- `alembic/versions/f13e20261009_outcome_versions.py`：新增字段、历史延续与回退守卫。
- `tests/test_outcome_versions.py`、`tests/test_outcome_version_migration.py`：新增验证。
- `tests/test_asset_space.py`、`tests/test_registrar_completion.py`：更新模型夹具与责任建议断言。

前端：

- `src/lib/assetVersions.ts`、`src/lib/api.ts`：分开成果版本与修订。
- `src/components/AssetCard.vue`、`src/components/AssetConfirmationPanel.vue`：稳定版本展示与明确发布。
- `src/pages/AssetOverviewPage.vue`、`src/pages/AssetReviewPage.vue`：登记人/负责人和成果版本。
- `src/pages/AssetDetailPage.vue`、`src/pages/AssetsPage.vue`：责任说明与修订号文案。
- `tests/outcomeVersions.test.mjs`：展示及明确发布行为。

本文件为修改/验证记录。没有推送、服务器部署、实际资产登记/确认/审核或改派。生产业务验收和本次候选发布仍待执行。
