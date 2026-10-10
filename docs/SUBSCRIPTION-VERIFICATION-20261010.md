# 个人订阅登记与公司账号核验

日期：2026-10-10。状态：本地实现及验证完成，候选待推送发布。基线为 `0175501a4e7b17f1768ffaab88050a44743c942b`，包含已发布的管理页布局补修；本次不新增数据库迁移。

## 最终行为

- 个人空间提交的订阅直接完成登记：`active / not_required / personal / private`。个人登记与付款来源分开，保留 company、department、personal、free、trial 的原含义；公司采购、准入和使用授权仍由对应流程记录。
- 订阅卡片、资产库和详情页明确显示“个人订阅”“无需审核”“已登记”；个人订阅使用登记说明，不显示 AI 成果版本。仅 AI 成果显示成果审核入口。
- 历史个人订阅通过 AssetRead/Hudu 的统一读取政策标注无需审核，个人草稿列表及计数排除这类登记；不在读取请求中批量改写旧存储状态。以后修改说明、补附件、恢复记录或使用原有确认回执，也不会重回待审核。
- 免审标识同时校验 `membership-registration` 来源和 `saas_subscription` 类型。AI 草稿即使自填相同来源仍须审核；已审核的目录和套餐仍是订阅登记的前置条件。
- 入口为“公司资产管理 → 平台与账号 → 公司平台账号 → 核验账号”；账号名称可进入资料详情，详情页也提供“查看账号核验”。
- 核验表单展示平台、公司、注册身份和当前状态，要求核对实际平台、公司/账号归属、编号或替代核对方式，并填写依据。资料不足可保存待补充内容。平台确实不提供编号时，需显式选择并写明核对方式。
- 核验仅由资产管理员/系统管理员操作。`POST /api/v1/platform-tenants/{id}/verification` 使用服务端身份、CSRF、资产版本、账号行锁、同请求幂等与审计；过期版本、改内容重用请求、无效公司/平台、重复 UID 均拒绝。
- 核验完成更新原账号事实及核验时间；原草稿账号转为在用。核验不改变目录审核、不创建人员访问授权；实际 DeepSeek/MiniMax 账号仍须由管理员依据真实资料核验。

## 修改文件

| 范围 | 文件 |
|---|---|
| 个人订阅规则与兼容读取 | `backend/app/models/domain.py`、`schemas/assets.py`、`api/v1/asset_space.py`、`api/v1/hudu.py` |
| 编辑、附件、确认、恢复与责任配置 | `backend/app/services/assets.py`、`services/registrar_details.py`、`api/v1/asset_activity.py`、`api/v1/asset_attachments.py`、`api/v1/assets.py` |
| 账号核验 API | `backend/app/api/v1/account_verification.py`、`api/router.py` |
| 页面与共用标识 | `frontend/src/components/AssetCard.vue`、`components/PlatformAccountVerification.vue`、`lib/api.ts`、`lib/labels.ts`、`lib/personalSubscriptions.ts`、`pages/AccountsPage.vue`、`pages/AssetsPage.vue`、`pages/AssetSpacePage.vue`、`pages/AssetOverviewPage.vue`、`pages/AssetDetailPage.vue`、`pages/MembershipRegisterPage.vue` |
| 验证 | `backend/tests/test_subscription_verification.py`、`tests/test_asset_space.py`、`tests/test_asset_center_integration.py`、`scripts/rehearse-subscription-verification.py` |

## 实际验证

- 82 项隔离 PostgreSQL 检查全部通过：新/旧订阅、五种资金来源、私有访问、AI 免审伪造负向路径、编辑和恢复、目录套餐约束、确认兼容、账号核验、CSRF、权限、唯一性、版本冲突、重试及并发。一度发现核验时间时区造成重试误判，已统一为 UTC；最终全目标集重跑通过。一次中间测试运行器停滞已终止，仅停止自己的隔离集群，最终新集群正常执行并停止。
- 定向 Ruff 及 `git diff --check` 通过；新接口/测试执行完整 Ruff，既有改动文件保留原 E501 基线并检查其他规则。
- 最终 `npm run build`（Vue 类型检查 + Vite）通过。
- 内部浏览器本地合成预览通过：卡片和资产库标识、订阅详情、核验入口、未勾选反馈、成功读回、深链接、保存失败保留内容、员工无核验按钮、空列表、读取失败及重试入口。
- 桌面 1280px/1920px 与 390px 窄屏无整页横向溢出，核验复选框为 16px，Tab 循环回到关闭按钮；临时视口已重置。
- 证据位于 `.local/subscription-verification/ea69015ddb`，合成预览截图 `.local/subscription-library-preview-20261010.jpg`、`.local/account-verification-preview-20261010.jpg`。合成保存与实际隔离数据库持久化检查分别完成；尚未执行新版本上线或真实业务人工验收。

复现命令（在本工作区运行；脚本拒绝复用已占用的隔离端口）：

```powershell
& 'C:\Users\MSI\Documents\Codex\work\asset-center-registrar-completion\backend\.venv\Scripts\python.exe' scripts/rehearse-subscription-verification.py --pg-bin 'C:\Users\MSI\Documents\Codex\work\dam-alignment-v13\.runtime\replacement-postgres\pgsql\bin'
Set-Location frontend
npm run build
```

## 发布与回退边界

候选需同时发布前后端，schema 保持 `f13f20261010`。当前公开线上元数据仍为前端 `bd1f342`、后端 `cbef316`；本次尚未对线上账号或资产写入。

授权后先在测试入口备份并发布，验证新 API、静态文件、会话隔离、已有记录标识和核验入口；测试保留数据库的代码回退再应用通过后，再备份并发布正式入口。保留旧前后端包、业务表指纹和服务状态。新状态都是既有字符串字段，代码回退不需撤销 schema，但旧界面可能不认识“无需审核”展示；不得用旧快照覆盖上线后的新登记或核验事实。

技术发布与管理员页面回读不替代用户或指定验收人的真实登记/核验业务验收。
