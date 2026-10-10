# 平台/供应商与套餐目录整理

日期：2026-10-10。状态：本地候选已实现并验证；未连接生产、未提交推送或部署，真实目录整理和人工业务验收仍待执行。

工作区：C:/Users/MSI/Documents/Codex/work/asset-center-service-catalog  
分支：codex/service-catalog-unification  
基线：ec12e1d66406b32acf977f28a52788663942cf0a，已纳入 b6a2260 的环境入口收口。原正式工作区未被覆盖。

## 用户可看到的变化

- “平台与账号”中的平台目录、供应商合并为“平台/供应商与套餐”。统一登记、维护资料、服务套餐和审核。
- 登记订阅先选服务，再选其套餐。例如 OpenAI → ChatGPT → Plus/Pro，Anthropic → Claude → Pro。切换服务会清空套餐，防止串选。
- 公司“服务实例”也从已审核目录选择服务和套餐；特殊订单可明确选择“其他套餐”并补实际名称。
- “订阅与用量”和旧平台详情的维护操作都进入统一目录。旧 bookmarks 的 tab=providers、tab=platforms、mode=provider 仍兼容。
- 一个平台对应一个提供方时，维护目录同步其名称和官网；已有多平台提供方关系保留，不凭名称强行合并。

## 本地核对的官方目录事实

下表是可供整理的公开服务目录，不是公司的采购、付款、账号权限或使用记录。价格和配额未登记；批量脚本仅整理已有对应品牌的条目，不创建未出现品牌。

| 平台/供应商品牌 | 服务 | 可选套餐或计费方式 | 核验来源 |
| --- | --- | --- | --- |
| OpenAI | ChatGPT | Free、Go、Plus、Pro、Business、Enterprise；Team 保留为历史名称 | [官方套餐](https://chatgpt.com/pricing/)、[Team 更名说明](https://help.openai.com/en/articles/8542115-chatgpt-business-general-faq) |
| Anthropic | Claude | Free、Pro、Max 5x、Max 20x、Team、Enterprise | [官方套餐](https://claude.com/pricing) |
| Google | Gemini | 免费、Google AI Plus、Google AI Pro、Google AI Ultra | [Google AI 套餐](https://one.google.com/about/google-ai-plans/) |
| DeepSeek | DeepSeek API | 按量计费 | [官方计费说明](https://api-docs.deepseek.com/quick_start/pricing/) |
| MiniMax | MiniMax API；MiniMax M Plan | API 按量计费；M Plan：Go、Explore、Build | [当前 M Plan](https://www.minimax.io/m-plan) |
| xAI（历史品牌目录名） | Grok | SuperGrok、SuperGrok Heavy | [官方 Grok 页](https://x.ai/grok)、[近期发布记录](https://grok.com/release-notes/sep-05-2026) |

ChatGPT 的历史 Team 记录不被改写为 Business。MiniMax 旧 Token Plan 的 Plus/Max/Ultra 不自动改成 M Plan 的新档位。xAI 官网页面当前标识 SpaceXAI，现有品牌目录名保留；不据网页品牌变化修改合同公司主体。其他未核验产品仍需自己的依据。

VPN（供应商待确认）、yishangcloud、云仓等简称，以及截图未展开的其余条目，尚无本次真实完整清单与提供方证据，不能报告全部审核完成。

## 登记与审核规则

1. 登记和补资料默认待审核；Plus、Team、Pro 及已知完整套餐名称不能作为平台或服务名称。
2. 管理员维护服务及可选套餐；同一目录下不能重复新增同名服务。保存资料或套餐后重新待审核。
3. 审核绑定确切目录修订摘要；需有效提供方、官网、核验来源链接和审核说明。过期版本返回 409，供重新读取。
4. 已审核且归属一致的服务才出现在新订阅选项中；后台再次校验套餐和状态，界面隐藏不能代替权限校验。
5. 新目录写操作沿用现有全局资产管理权限、会话与 CSRF；请求编号绑定内容、操作人及目标，重试不重复创建或审核。保留操作人和前后事实审计。
6. 审核是服务目录核验。公司的采购、账号权利、报销以及具体成果审核仍按对应流程确认。

## 旧目录整理

新增 maintenance CLI 默认预览并回滚；应用必须使用真实有效资产管理员 ID 和本次预览摘要。执行时锁定目录及相关引用表，使摘要与应用处于一致事务。

- 只对明确品牌别名归并。如 ChatGPT Plus/Team/Pro 回到 OpenAI → ChatGPT，Claude Pro 回到 Anthropic → Claude。
- 第三方提供方名下的同名服务不按官方品牌自动改归属。
- 保留旧 Provider、Platform 和 ServiceProduct 行，归档作为历史，不物理删除。
- 重新关联订阅、购买渠道、公司账号、资产平台关系和导入匹配引用；不改资产 ID、名称、付款人、资金来源或日期。
- 只有套餐缺失或误填为完整旧服务名时，才从明确别名补回 Plus/Team/Pro；已有实际套餐原文保留。
- 公司账号标识或服务编码冲突时事务失败，交人工核对；不静默覆盖。
- 历史“已批准”缺少带来源的目录审核凭证时转为待审核；含额外未核验服务的目录不能批量通过。
- 旧供应商按已存在的名称与官网补齐统一目录关联，未知身份、重名所有权和多平台未归属服务仍留待核验。
- --review-known 只对资料范围与官方参考完全一致的目录保存审核，预览列出 sources、revision 和审核说明，摘要包含这些审核事实。

CLI 命令模板（须在获准环境配置后执行；此处没有执行生产命令）：

```powershell
Set-Location 'C:\Users\MSI\Documents\Codex\work\asset-center-service-catalog\backend'
python -m app.cli.normalize_service_catalog --actor-id '<经服务端核对的管理员UUID>' --review-known

# 阅读全部 changes、reviews、pending 和 unlinked_services 后，使用原预览摘要。
python -m app.cli.normalize_service_catalog --actor-id '<同一管理员UUID>' --review-known --apply --expected-digest '<本次预览的digest>'
```

管理员 UUID 参数不能代替本人授权；上线时还需独立核对当前认证身份和真实目录。

## 验证证据

| 检查 | 结果与边界 |
| --- | --- |
| 后端目标检查 | 59 项通过：目录登记、重试、权限、修订冲突、套餐选择、审核撤销、私有订阅、旧库存接口、资产中心及资产空间回归 |
| 最终定向复核 | 官方引用、单一登记同步和旧批准核验证据调整后，重跑 cleanup/cli/orphan 4 项通过；不是额外 4 个不同测试 |
| PostgreSQL | 自建 loopback 55439，一次性数据库 dam_v13_tests_b53e288bb3；测试结束已停止本任务集群，既有 55433 未复用 |
| 增量迁移 | 空库升级；f13e 旧服务所有原字段保持；新增 platform_id=NULL、plan_options=[] |
| 回退与恢复 | 无新事实可降级后重升；已有目录事实的降级被守卫阻止；pg_dump/独立库 pg_restore 后套餐读回一致 |
| 后端静态检查 | 所有本次后端变更与新增演练脚本的定向 Ruff 通过 |
| 前端 | npm run typecheck、npm run build；仓库根 node scripts/test-workspace-navigation.mjs 的 11 条断言通过 |
| 本地合成浏览器 | 套餐下拉、切换服务清空、特殊套餐、订阅保存反馈、目录筛选空结果与审核弹窗/保存、旧入口、公司实例下拉和统一维护入口已回读 |
| 窄屏 | 390px 合成目录检查，页面内容宽 375px；临时 viewport 已恢复 |
| 最终构建 | index-DTC-EYeq.js；index-db5dkouk.css；无 error 控制台记录（本地合成页面） |

证据目录：.local/service-catalog/b53e288bb3/RESULT.md、targeted-tests.log、final-targeted-recheck.log 与迁移/备份/恢复日志。这些是本地技术验证，不是线上持久化、真实供应商全量审核、钉钉登录或人工 UAT。

首次导航检查误从 frontend 目录寻找根目录脚本，改在仓库根执行后通过；没有因该路径错误修改业务代码。旧会员单测夹具缺少新增读取字段已精确补齐，不改原测试行为。

可复现完整隔离演练：

```powershell
Set-Location 'C:\Users\MSI\Documents\Codex\work\asset-center-service-catalog'
& 'C:\Users\MSI\Documents\Codex\work\asset-center-registrar-completion\backend\.venv\Scripts\python.exe' 'scripts/rehearse-service-catalog.py' --pg-bin 'C:\Users\MSI\Documents\Codex\work\dam-alignment-v13\.runtime\replacement-postgres\pgsql\bin'
```

## 迁移与后续上线

增量版本 f13f20261010，只增加服务的目录关联和套餐 JSON 字段。保留 Provider/Platform 内部表与原读接口，以兼容历史对象和引用；管理入口已统一。

尚待明确授权后执行：提交推送 → 核对在线代码/schema 和真实管理员身份 → 测试环境备份、迁移、预览与应用 → 独立回读和保留 schema 的代码回退演练 → 正式环境相同步骤 → 逐条核验其余实际条目与人工业务验收。不能由本地截图推定线上 22/40 数量仍然成立。

代码回退保留增量 schema。已有目录/套餐事实时不降级删列；数据回退需依据实际备份和审计另行受控执行，不能覆盖上线后的新业务记录。知识平台、权限授予、真实采购与成果发布不在本次变更中。

## 文件清单与候选身份

以下 25 个实现/验证文件的规范化文本内容合成 SHA-256：  
`633cabab6e369fa7f675ae674d3e0eeaf1dae66b33db14c59462b4af85979664`

算法：按相对路径排序，以 UTF-8 文本读取（换行规范化）；各文件 SHA-256 与路径组成 JSON 数组，sort_keys=True、separators=(',',':')，再 SHA-256。文档本身和已忽略的临时预览/验证数据不计入。

- backend/alembic/versions/f13f20261010_service_catalog.py
- backend/app/api/router.py
- backend/app/api/v1/asset_space.py
- backend/app/api/v1/inventory.py
- backend/app/api/v1/service_catalog.py
- backend/app/cli/normalize_service_catalog.py
- backend/app/models/domain.py
- backend/app/schemas/inventory.py
- backend/app/schemas/service_catalog.py
- backend/app/services/catalog_cleanup.py
- backend/app/services/catalog_reference.py
- backend/app/services/service_catalog.py
- backend/tests/test_asset_center_integration.py
- backend/tests/test_asset_space.py
- backend/tests/test_service_catalog.py
- frontend/src/components/PlatformDirectoryPanel.vue
- frontend/src/lib/api.ts
- frontend/src/lib/assetStructure.ts
- frontend/src/lib/managementWorkspace.ts
- frontend/src/pages/AccountsPage.vue
- frontend/src/pages/DirectoryDetailPage.vue
- frontend/src/pages/IntakePage.vue
- frontend/src/pages/MembershipRegisterPage.vue
- frontend/src/pages/ServicesPage.vue
- scripts/rehearse-service-catalog.py

另新增本说明。规格仓仅追加 docs/TODO.md；全局任务日志、INDEX、项目摘要与既定后续 TODO 分别记录状态，不进入正式应用包。
