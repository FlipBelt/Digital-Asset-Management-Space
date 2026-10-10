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

内部浏览器合成资料检查已完成平台逐级导航、新建员工自动带入、现有绑定保存回读、子账号树、离职交接链接/登记表单、个人订阅免审和平台套餐选择、只读员工及读取失败重试；弹窗 Tab/Escape 焦点恢复通过。390px 文档宽375px、离职弹窗325px无整页横向溢出；窄屏全页截图能力不可用，不能将 DOM 尺寸检查称为人工视觉验收。Vue 类型检查通过，最终双路径构建与冻结发布记录待追加。

## 发布与人工验收

当前实现已本地完成，尚未冻结提交或更新测试/正式站点。发布从两环境实际 acf10fb 运行时基线对账，测试备份/切换/旧代码回退/再应用后，独立公网字节和真实管理员只读界面检查通过才更新正式站点。保留数据库备份、旧代码与回退清单。

真实员工离职名单、账号登录标识、外部平台权限回收及责任交接由管理员根据实际依据操作；自动检查、合成交互、技术发布和人工业务验收分别记录。
