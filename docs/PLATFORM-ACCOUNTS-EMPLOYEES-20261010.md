# 平台账号层级、责任同步与离职员工管理

2026-10-10；任务 01a12369-6876-7eb2-9f77-1088f98dd3df。用户要求修复五处账号/责任/员工管理问题，沿用本会话修复、推送与受控发布授权；浏览器操作使用内部浏览器。

## 实现与边界

平台一级入口 → 平台内公司账号、个人账号、待核验/待交接、注册身份、资料与套餐 → 父账号 → 子账号/席位。保持原资产 UUID 与历史关联，不删除业务数据。资产库查询及导出用 library_only 在服务端分页、总数统计前排除平台账号与注册身份；旧分类/账号辅助视图链接转到统一账号入口。

新建与现有子账号均可选择同公司在职员工；服务账号可无员工绑定。绑定只记录员工关系，不新增实际平台权限。创建/绑定保留管理范围、CSRF、版本、请求幂等与审计，员工行锁防止离职登记与新增绑定互相覆盖。

责任跟进读取 AssetResponsibility 中已确认、有效期内且员工在职的责任；部门归属不再冒充负责人。账号子项的未绑定或离职状态汇总到父账号，不生成独立子项跟进记录。个人订阅免审及现有私有可见性保持。

离职入口在“组织与授权 → 离职员工”。登记需实际日期、依据、确切员工版本和全局管理权限；禁止登记本人离职。停用目标员工本系统用户并撤销其会话，保留账号、责任与授权历史，列出交接链接。同步不会覆盖明确离职，旧人员 PATCH 不能绕过登记依据；纠正为在职不自动重新启用本系统登录或外部授权。无法核验/同步缺席/非活跃不会自动归入已离职。

无需 schema 迁移，沿用 f13f20261010。上线不代表任何真实员工已离职，也未自动交接、撤回外部平台权限或核验公司账号。

## 文件

- 后端新模块：account_hierarchy.py、account_binding.py、employee_lifecycle.py；服务 account_structure.py、account_binding.py、audited_requests.py；新回归 test_account_hierarchy_lifecycle.py。
- 现有后端：router、assets、hudu、organizations、transfers、workspace、auth、assets repository、organizations/workspace schemas、dingtalk sync。
- 前端：AccountsPage、ChildAccountsPanel、EmployeeLifecyclePanel、AssetDetailPage、AssetFollowupPage、AssetsPage、OrganizationPage、PlatformDirectoryPanel、api、IntakePage、MembershipRegisterPage。
- 设计约定同步于 ASSET-CENTER-DESIGN-SYSTEM.md。

## 验证

T3 风险验证使用一次性 loopback PostgreSQL 55439，数据库 dam_v13_tests_subscription_d532501c85；升级、种子与下列 111 项检查通过，集群已正常停止：

```powershell
& 'C:/Users/MSI/Documents/Codex/work/asset-center-registrar-completion/backend/.venv/Scripts/python.exe' scripts/rehearse-subscription-verification.py --pg-bin 'C:/Users/MSI/Documents/Codex/work/dam-alignment-v13/.runtime/replacement-postgres/pgsql/bin' --tests tests/test_account_hierarchy_lifecycle.py tests/test_subscription_verification.py tests/test_workspace_flow.py tests/test_hudu_workspace.py tests/test_asset_category_filter.py tests/test_pm_session_security.py tests/test_dingtalk_organization.py
```

证据 .local/subscription-verification/d532501c85。覆盖账号过滤/计数/导出/历史 UUID、责任有效期/离职/提议负向路径、子账号归并、私有订阅、已核验注册身份保留、员工绑定权限/跨公司/版本/CSRF/幂等、离职证据/本人/权限/版本/会话/同步及交接保留。前一次测试客户端启用后台循环后的退出停滞已改为无 lifespan 的隔离客户端；未修改实际后台任务。

内部浏览器合成资料检查已完成平台逐级导航、新建员工自动带入、现有绑定保存回读、子账号树、离职交接链接/登记表单、个人订阅免审和平台套餐选择、只读员工及读取失败重试；弹窗 Tab/Escape 焦点恢复通过。390px 文档宽375px、离职弹窗325px无整页横向溢出；窄屏全页截图能力不可用，不能将 DOM 尺寸检查称为人工视觉验收。Vue 类型检查、根路径及 /test 双路径构建、改动范围 Ruff（既有 E501 基线保留）及 diff 检查通过。仓库无 GitHub CI 检查，不能将本地检查报告为 CI 通过。

## 发布与人工验收

应用冻结版本 0541db065e51c61ad05e1efd62510f1b1e9b2b26 已推送分支 codex/platform-account-hierarchy-and-offboarding，并先测试、再正式发布。Draft PR #6：https://github.com/FlipBelt/Digital-Asset-Management-Space/pull/6。文档追加提交不改变已发布应用版本。

从两环境实际 acf10fb 运行时和 f13f schema 对账，33 个运行文件的分片包共 160766 字节，SHA-256 为 89155b7b567f94cd8da8a452ba8f242711ddeb5e891c4399ace81d02d01b1200；服务用户下编译和 OpenAPI 探针通过后切换。测试命令 t-hz06zln90me9zi8 成功，包含旧代码/静态回退再应用，并确认正式进程及状态不变；测试公网资源和真实管理员只读页面通过后，正式命令 t-hz06zlo1u2i3tvk 成功。每环境 75 张业务表全行内容指纹一致；无 schema 迁移、业务登记或权限写入。正式环境未执行旧代码回退或数据库恢复演练。

独立公网回读（2026-10-10 08:20:25 UTC）确认每环境 8 个冻结文件逐字节一致、7 条 SPA 路径、5 个匿名读取及离职 POST 均 401，ready/database 正常。现有管理员会话兼容。正式页面回读：OpenAI 公司账号 FB GPT 内含 8 个子账号，现有绑定弹窗可搜索 67 位当前候选员工；平台个人页保留 Plus 免审订阅；资产库 13 项业务资产，分类、清单和导出不包含账号；跟进 12 项且子账号问题汇总于 FB GPT 父账号。MiniMax 已确认负责人正确显示并退出待补负责人清单；FB GPT 当前负责人仍为“建议尚未生效”，需管理员在责任页确认后生效。离职页按实际状态显示尚无明确离职记录，日期/依据表单只读打开后取消。控制台 warning/error 为空。以上数字为此次回读时点快照。

本地证据目录 .deploy-artifacts/platform-hierarchy/0541db065e51，含 PACKAGE.json、DEPLOYMENT.json、local-package-PASS.json、test-server-PASS.json、test-public-PASS.json、test-ui-PASS.json、production-server-PASS.json、final-public-PASS.json、production-ui-PASS.json 及 production-platform-hierarchy.png。服务器备份：/opt/account-center-test/backups/0541db065e51-platform-hierarchy-test-20261010 与 /opt/account-center/backups/0541db065e51-platform-hierarchy-production-20261010，保留旧代码、旧静态、数据库转储与 schema 保留回退清单；发生上线后业务写入时，不能直接用旧数据库覆盖新记录。

真实员工离职名单、账号登录标识、外部平台权限回收及责任交接由管理员根据实际依据操作；自动检查、合成交互、技术发布和人工业务验收分别记录。
