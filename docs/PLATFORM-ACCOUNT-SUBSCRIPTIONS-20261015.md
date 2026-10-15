# 平台账号补充入口与订阅用量收口

关联任务：[FBC-187](https://linear.app/j21nianyi/issue/FBC-187)。用户授权后，应用 `95cf02afacb57096e193bb0ef7b81c18427857c9` 已推送并于2026-10-15按测试→正式发布；[PR #20](https://github.com/FlipBelt/Digital-Asset-Management-Space/pull/20) 保持 Draft/Open，未合并 main。人工业务验收独立。

## 用户可见行为

- 账号概览的“主要注册身份”直接显示“补充/修改注册与登录标识”。点击展开并聚焦本页填写区，支持选择已登记标识；新标识可另页登记后返回刷新。无维护权限时明确联系账号负责人或管理员。
- 平台分为“已有账号 / 暂无账号”，已有组置前；公司账号与个人账号合计数量降序，不重复计入子账号。同数按名称、ID稳定排序，搜索和空态覆盖两组。
- “订阅与用量”并入“平台与账号”的一级页签和平台内页签，管理菜单移除重复入口。旧 `/services`、告警与三平台深链接保留 query/hash 定向兼容。
- 个人订阅保留套餐、日期、付费和可见权限，不再显示公司余额待录入卡片，也不进入余额关联候选。公司服务按平台/供应商筛选，已有余额/额度能力保留。历史指标、连接和独立通知配置不删除。

## 保存与兼容

新增 `PUT /api/v1/assets/{asset_id}/registration-identity`：版本、请求编号和目标标识均必填；按服务器维护权限、有效标识及禁止注册规则校验。使用事务、资产/引用行锁、请求重放和版本冲突保护；主要引用可替换并回读，保留其他引用和历史唯一行。旧关联关系的注册身份“调整”入口转到本页安全填写区，其余关系协议保持。

服务实例新增可选 `scope=company`；默认 `all` 保持兼容。个人订阅按既有 source/type 条件识别，不用资金来源代替分类。不新增迁移，不修改真实账号、标识或订阅。

非系统管理员不再因请求系统审计接口而无法加载账号详情；审计仍仅由系统管理员读取，界面说明权限边界。

## 验证

- 一次性回环 PostgreSQL 74项目标回归通过，证据 `.local/subscription-verification/07eb8d1f71/`；集群随后仅用于隔离合成页面核验，验证结束后已停止。
- 平台分组、稳定排序、搜索和导航 helper 31条断言；真实 Vue 页面及真实 router 的9项前端回归通过，包含旧地址尾斜杠兼容。
- Vue 类型/生产构建、Ruff F/I 和差异检查通过；既有包体积及 Starlette/httpx 弃用提示保留。
- 额外旧管理框架回归8/9通过；未修改的跟进页测试仍以3个页签计数断言实际4个页签，属于既有预期失配。本轮不改无关跟进页，也不声明全套通过。
- 构建产物的本地页面验证：补充入口、焦点、合成账号保存并重载回读、分组倒序、个人余额卡片排除、合并入口及旧深链接通过。使用一次性合成身份/数据，未连接生产或同步外部余额。
- 补充入口5项前端回归通过：非系统管理员加载与审计权限、候选范围、失败重试/请求编号更新、保存后读回、旧调整入口迁入安全保存。

修改涉及 AccountsPage、AssetDetailPage、ServicesPage、PlatformUsageDetailPage、ScenarioWorkspacePage、router、managementWorkspace、platformWorkspace、API客户端，后端 assets/inventory/workspace 及相应目标测试。人工业务验收独立。

## 测试与正式发布证据

- 发布前确认双环境仍运行 `abae102c66a345c26798c51fee5d26117593f20e`；预检 `t-hz0702uetg900zk` exit 0/PREFLIGHT_PASS。冻结包含3个后端文件和双环境共16个静态文件，无迁移。包 SHA-256 为 `305a38d8ecc6472fbf483f4220c236c011926e15a8b5faac51a48f727583cf11`，operator SHA-256 为 `a6d7a7a0be218256f827f2f61117520c220dcdfc6f8c203797b5f4da2c3b8da3`。
- 测试发布 `t-hz0702vc25j9r0g` exit 0/PASS；服务 active，75张业务表完整内容保持，schema `f13f20261010` 不变。实际执行旧应用/静态回退再应用，期间正式进程和版本保持。备份目录 `/opt/account-center-test/backups/95cf02afacb5-platform-workspace-test-20261015`。
- 测试公开字节与新页面通过后，同一应用提交进入正式。正式发布 `t-hz0702vs1fwexa8` exit 0/PASS；服务 active，75张业务表完整内容保持，无迁移。备份目录 `/opt/account-center/backups/95cf02afacb5-platform-workspace-production-20261015`。正式未执行回退或数据库恢复演练。
- 最终独立公开回读 `python .local/verify-platform-workspace-public.py final` PASS：两环境各8个冻结文件逐字节匹配、13个SPA入口可达、13个匿名读取和责任/注册身份/三种标识写入均401，ready/database正常。应用与后端版本均为 `95cf02a`。
- 两环境认证页面均确认平台分组/数量倒序、合并用量页、个人订阅余额卡片排除和本页补充编辑区；正式覆盖原反馈账号，可选标识正常加载。仅打开入口和候选，不保存真实资料，不调用外部余额同步。成功保存与重载由隔离合成数据覆盖，人工业务验收未代做。
- 上传内容曾正确但名称被控制台重复输入破坏，两次前置命令分别 `t-hz0702uwiobi60w`、`t-hz0702v5e1c5reo` exit 1，均在operator运行和服务切换前停止；按六个冻结文件哈希在本次专用上传目录归位后，完整包和operator哈希重新通过。没有改变候选提交。

本地安全回执位于 `.deploy-artifacts/platform-workspace/95cf02afacb5/`：`test-server-PASS.json`、`test-ui-PASS.json`、`test-public-PASS.json`、`production-server-PASS.json`、`production-ui-PASS.json` 和 `final-public-PASS.json`。冻结文件和回执不含凭据。回环API、前端预览和一次性PostgreSQL均已停止。

用户补充路径：平台与账号→进入账号→概览→主要注册身份旁的“补充/修改注册与登录标识”。订阅与用量在平台与账号的同名页签。
