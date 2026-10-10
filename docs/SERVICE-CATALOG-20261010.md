# 平台/供应商与套餐目录整理

日期：2026-10-10。状态：用户授权后已提交推送，先测试再生产发布并完成真实目录整理；线上持久化回读和管理员页面检查通过，人工业务验收独立保留。

工作区：C:/Users/MSI/Documents/Codex/work/asset-center-service-catalog  
分支：codex/service-catalog-unification  
基线：ec12e1d66406b32acf977f28a52788663942cf0a，已纳入 b6a2260 的环境入口收口。原正式工作区未被覆盖。

应用提交：cbef316f8ab3ac1e46e78b7aa7cd1d8eae1f7ac3。

线上入口：[平台与账号 → 平台/供应商与套餐](https://jtzhzt.flipbeltchina.com/accounts?tab=directory)；[登记订阅](https://jtzhzt.flipbeltchina.com/memberships/new)。

整理后目录共 33 条：24 条已审核、8 条待审核、1 条待完善登记。已审核服务有 35 个可选项，会员与 API 分开登记。

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

已读取双环境实际目录并逐项核对公开来源。VPN、云仓等实际提供方不明的条目按用户“自行联网搜索，实在无法确定先跳过”保留；具体范围见下文。

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

基础 CLI 命令模板（默认回滚预览；摘要只对该次计划有效）：

```powershell
Set-Location 'C:\Users\MSI\Documents\Codex\work\asset-center-service-catalog\backend'
python -m app.cli.normalize_service_catalog --actor-id '<经服务端核对的管理员UUID>' --review-known

# 阅读全部 changes、reviews、pending 和 unlinked_services 后，使用原预览摘要。
python -m app.cli.normalize_service_catalog --actor-id '<同一管理员UUID>' --review-known --apply --expected-digest '<本次预览的digest>'
```

管理员 UUID 参数不能代替本人授权；上线时还需独立核对当前认证身份和真实目录。

本次实际治理使用 `scripts/curate_service_catalog_20261010.py`：复用基础清理规则，补齐其余可核实来源、MiniMax 历史拼写以及四种独立 API 服务，再以确切预览摘要审核。只将同一提供方下明确以 ChatGPT API、Claude API、Gemini API、Grok API 命名的历史登记关联到相应 API 服务；原订阅名称和套餐原文保持。该脚本不是新运行时 API。

## 其余目录的核验来源

下表与六品牌资料共同构成本次 24 条审核的来源。官方未提供统一套餐档位的服务保留实际名称和合同补充入口；不虚构价格、套餐权益或公司合同。

| 目录 | 核对的官方依据与处理 |
| --- | --- |
| 12315 | [市场监管总局](https://www.samr.gov.cn/wljys/sjdt/art/2023/art_b3139687c63c4352b474d616c8a37ac6.html)确认全国平台；维权服务单独登记 |
| 中国商标网 | [国家知识产权局](https://www.cnipa.gov.cn/)官方导航；登记查询服务，不推定付费档位 |
| 中国物品编码中心（GS1） | [官方业务大厅通知](https://bizhall.ancc.org.cn/)确认 GS1 服务与新大厅入口，保留合同套餐 |
| 京东 | [供应商平台](https://vc.jd.com/)、[企业购帮助](https://help.jd.com/user/issue/973-4257.html)、[官方知识产权报告](https://ir.jd.com/static-files/99686c72-ffeb-4d82-82b2-cbbe80184104)；VC、企业购、店铺和维权分别保留 |
| 小红书 | [官方知识产权保护平台](https://ipp.xiaohongshu.com/) |
| 影刀 | [官网套餐](https://www.yingdao.com/buy)、[产品](https://www.yingdao.com/product/)；社区版、创业版、企业版，历史“助手服务”保留合同补充 |
| 微博 | [官方社区公约](https://service.account.weibo.com/h5/roles/gongyue)，核对平台与维权范围 |
| 抖音 | [官方侵权投诉指引](https://www.douyin.com/draft/douyin_agreement/infringement_guide.html)指向字节知识产权保护平台 |
| 拼多多 | [官方知识产权平台隐私材料](https://pfile.pddpic.com/galerie-go/mms_file/3a0bdcc8-0b73-4cb4-ae9c-ff34facaed2c.pdf) |
| 搜狐邮箱 | [官方邮箱注册](https://m.mail.sohu.com/app-web1/register.html) |
| 新浪邮箱 | [官方邮箱](https://mail.sina.com.cn/?vt=0)，免费与 VIP 分开 |
| 用友云 | [官方 YonSuite 客户成功服务说明](https://www.yonyou.com/success/yonsuite/pdfFile/standard.pdf)，保留实际合同，不套用其他软件档位 |
| 知蝉网 | [官网介绍](https://www.izhichan.com/about)、[隐私条款](https://www.izhichan.com/terms/privacy) |
| 管易云 | [金蝶官网](https://www.kingdee.com/cn)所属品牌入口，核对 ERP 服务，不采用非官方代理套餐 |
| 聚水潭 | [官网](https://www.jushuitan.com/)、[官方开放平台](https://open.jushuitan.com/) |
| 钉钉 | [官网](https://www.dingtalk.com/?lwfrom=20150130160830727)、[悟空套餐](https://wukong.dingtalk.com/docs/quick-start/pricing-and-plans/)；历史标准/全功能名称与 API 接入备注保留 |
| 阿里云 | [OCR 计费](https://help.aliyun.com/zh/ocr/product-overview/product-billing/)、[OSS 计费](https://help.aliyun.com/zh/oss/billing-method/)；OCR、OSS 和通用服务分开 |
| 阿里知识产权保护平台 | [阿里官方说明](https://activity.alibaba.com/page/ipr_qa_detail01.html)、[官方入口说明](https://survey.alibaba.com/survey/kwlXeGUWS) |

四种 API 的独立依据：[OpenAI](https://developers.openai.com/api/docs/pricing)、[Claude](https://platform.claude.com/docs/en/about-claude/pricing)、[Gemini](https://ai.google.dev/gemini-api/docs/pricing)、[Grok](https://docs.x.ai/developers/models)。

## 按用户要求跳过的 9 条记录

| 名称与数量 | 跳过原因 |
| --- | --- |
| yishangcloud，2 条 | 未找到可与实际记录可靠绑定的官方资料；两个历史提供方的同名记录保持，不强行合并 |
| 安捷云，1 条 | 找到 [TIZdata 官方安捷云资料](https://doc.tizdata.com/af/29/)，但原公司记录无官网或主体依据，无法确认是否同一服务 |
| 预策，1 条 | [候选官网](https://www.yucekj.com/)信息不足，同名品牌与公司实际记录无法绑定 |
| 专利查询系统、著作权登记系统，各 1 条 | 通用名称可对应多个官方或第三方服务，缺少实际入口，不据名称猜提供方 |
| 供应商待确认，1 条 | VPN、云仓服务没有实际提供方资料 |
| 163邮箱、网易企业邮箱，各 1 条 | 本次官方页面未能完成核验，直接浏览器访问 163 邮箱被网站安全检查阻止；未绕过，代理商页面不作为官方审核来源 |

线上状态分别为 8 条待审核、1 条同名历史提供方待完善登记。它们保留在管理目录，暂不进入新订阅的已审核服务选择。以后拿到实际官网、合同或提供方资料再审核。

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

## 发布、真实数据与回退证据

增量版本 f13f20261010，只增加服务的目录关联和套餐 JSON 字段。保留 Provider/Platform 内部表与原读接口，以兼容历史对象和引用；管理入口已统一。

用户明确授权提交推送、先测试再生产上线及备份后的实际目录整理；本人恢复阿里云登录后，依用户要求通过内部浏览器操作。当前实际管理员已验证为有效全局资产管理员；没有新增身份或权限。

| 阶段 | 结果与证据 |
| --- | --- |
| 发布前实时对账 | 两环境原前端 b6a2260、后端 4604859、schema f13e；75 张业务表，40 个供应商、22 个活动平台、42 个活动服务、120 个服务实例。技术计数不代表业务验收 |
| 冻结发布包 | 双路径包 134832 bytes、6 分片、28 文件；SHA-256 `3eaa66b2c4815129321ca4bf0a0e42d3eded6602517b8d1003f9d9717be18452` |
| 测试发布 | 云助手 `t-hz06zkue8ibgvsw`，退出 0；f13f，75 表原字段保持；原代码/静态回退保留 schema 后重新应用通过，生产未受测试切换影响 |
| 测试目录治理 | 基础应用 `t-hz06zkvb0le1vy8`；扩充应用 `t-hz06zkwx2oty800`；最终 33 条、24 已审核、9 待核实，重复预览 changes/reviews 均为 0 |
| 测试管理员 UI | 统一目录、来源、35 个服务选项、会员 Plus 选择、切换清空、公司服务实例下拉和统一维护入口回读通过；未提交虚构公司订阅 |
| 生产发布 | `t-hz06zkxb00ptgjk`，退出 0；应用 cbef316f8ab3、schema f13f20261010，75 表原字段保持 |
| 生产整理摘要守卫 | 首次应用 `t-hz06zkxso2c1kw0` 因 API 查询未固定顺序导致摘要不同而回滚；服务恢复，原 40/22/42 计数保持，未产生应用回执。诊断 `t-hz06zkxxwo3jh1c` 只输出允许的错误和差异路径 |
| 排序修复与核对 | 仅一次性维护脚本增加按服务实例 ID 排序，Ruff/语法通过；`t-hz06zky2oholbls` 两次新预览摘要相同，与原预览的业务事实逐项一致；不修改已部署应用或整理规则 |
| 生产实际应用 | `t-hz06zky5tz7ij28`，退出 0；摘要 `92f250e41b48f93a7d518993bf9de0113aadf71929d2480a749c5f62e1d3c104`，268 项字段/引用改动、33 条目录、24 已审核、9 待核实 |
| 持久化及历史字段 | 独立新进程回读已审核来源全部存在；120 个历史实例除目录关联和更新时间外的完整原字段保持，含套餐原文、付款、日期和资产 ID；重复预览 0 changes / 0 reviews |
| 公开检查 | 两环境各 8 个静态文件逐字节匹配冻结包，ready 数据库正常，两目录 API 匿名 401，SPA 路由匹配；生产整理重启后独立 `/api/v1/health/ready` 为 ready / database ok |
| 生产管理员 UI | 目录筛选实际为 24 已审核、8 待审核、1 待完善；OpenAI 下 ChatGPT 与 OpenAI API 分开，Plus/Pro/Team 下拉可选，35 服务选项，Claude 切换清空套餐并禁用保存 |

一次性维护脚本最终 SHA-256：`1419dbd4bc66a7a4b60fbec33c8d818784b9b75bb958803f81ccb0b2e12377f6`。部署应用的 25 文件摘要保持原值。

生产发布备份：`/opt/account-center/backups/cbef316f8ab3-catalog-production-20261010`，数据库 dump SHA-256 `efee85cfb41400eeace79b0c0991583ca25ffec8c369f5376059c932b71a15f3`。生产治理前另存 `/opt/account-center/releases/catalog-cbef316f8ab3-upload/production-catalog-before-curation-stable.dump`，SHA-256 `10846b8490127865bf0f902665c290ebb23906055b9295318723732e82409af0`；首次被阻止应用前的备份也保留，没有覆盖。

服务器受保护证据目录 `/opt/account-center/releases/catalog-cbef316f8ab3-upload` 保留两环境发布 PASS、目录 PREVIEW/APPLIED/IDEMPOTENT/READBACK/PASS；生产最终预览为 `production-curation-stable-PREVIEW.json`。本地公开读回在 `.deploy-artifacts/service-catalog/cbef316f8ab3/*-public-PASS.json`；生产截图在 `.local/service-catalog-production-20261010.jpg` 与 `.local/service-catalog-plan-production-20261010.jpg`。

仍需用户或指定验收人完成真实员工登记场景的人工业务验收。9 条不确定记录按用户允许的范围跳过，不能报告全量全部批准。

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

另新增本说明与一次性 `scripts/curate_service_catalog_20261010.py`。规格仓仅追加并更新 docs/TODO.md；全局任务日志、INDEX、项目摘要与既定后续 TODO 分别记录状态，不进入正式应用包。
