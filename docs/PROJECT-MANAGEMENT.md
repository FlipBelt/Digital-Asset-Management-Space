# 项目管理与 GitHub 协作

生效日期：2026-10-15。

本项目统一在 [Linear：数字中心｜AI 资产中心](https://linear.app/j21nianyi/project/数字中心ai-资产中心-d8ccb7e5469f) 管理。[GitHub 正式工程](https://github.com/FlipBelt/Digital-Asset-Management-Space) 保存代码、Pull Request 与版本证据。

## 状态与证据规则

- Linear 是活动任务、优先级、依赖和验收状态真源；旧 TODO、启动方案和预览记录保留为历史证据。
- 技术实现、测试、技术发布、真实业务验收分别记录。代码合并或部署成功不能自动关闭人工 UAT。
- Backlog 表示尚未开始或等待业务资料/验收人；Todo 表示已准备执行；In Progress 表示执行中；In Review 表示等待审查；Done 必须满足该任务的可核验验收标准。
- 不虚构负责人、截止时间、贡献、使用量或验收结论。验收人和环境明确后再更新相关字段。
- 旧独立工程方案已被现行 Vue / FastAPI / PostgreSQL、统一 Asset 方向替代；历史未勾选清单不等于现行未开发功能。
- 公开仓库只同步任务编号、必要摘要和链接；详细业务依据按原权限查阅。不要复制员工或账号明细、内部导入、日志、备份、凭据和原始聊天。

## 迁移索引

以下是首次迁移时的映射，后续状态以 Linear 为准。历史重复的 PILOT-HUMAN-001 已合并为一项。

| 原任务 ID | Linear |
|---|---|
| `PILOT-HUMAN-001` | [FBC-21](https://linear.app/j21nianyi/issue/FBC-21/待人工验收-双-skill-真人试用与跨会话恢复) |
| `DINGTALK-WEB-UAT-001` | [FBC-22](https://linear.app/j21nianyi/issue/FBC-22/待人工验收-钉钉浏览器登录与角色业务验收) |
| `TEST-ORG-DATA-001` | [FBC-23](https://linear.app/j21nianyi/issue/FBC-23/待人工验收-组织归属异常与法定主体依据核验) |
| `AGENT-CONNECTOR-UAT-001` | [FBC-24](https://linear.app/j21nianyi/issue/FBC-24/待人工验收-connector-真实客户端授权及登记闭环) |
| `REGISTRAR-COMPLETION-UAT-001` | [FBC-25](https://linear.app/j21nianyi/issue/FBC-25/待人工验收-登记器资料截图责任与审核验收) |
| `GOVERNANCE-USABILITY-UAT-20261009` | [FBC-26](https://linear.app/j21nianyi/issue/FBC-26/待人工验收-治理填写与审核易用性验收) |
| `ASSET-UNIFIED-FRAMEWORK-UAT-20261009` | [FBC-27](https://linear.app/j21nianyi/issue/FBC-27/待人工验收-统一框架分类管理和任务导航验收) |
| `LOGIN-IDENTITY-UAT-20261010` | [FBC-28](https://linear.app/j21nianyi/issue/FBC-28/待人工验收-新登录界面扫码与手机体验验收) |
| `ORG-COMPANY-FULL-20261009` | [FBC-29](https://linear.app/j21nianyi/issue/FBC-29/待人工验收-全员公司关系逐人对照) |
| `SERVICE-CATALOG-DATA-UAT-20261010` | [FBC-30](https://linear.app/j21nianyi/issue/FBC-30/待人工验收-服务目录合同套餐与员工登记验收) |
| `SUB-VERIFY-UAT-20261010` | [FBC-31](https://linear.app/j21nianyi/issue/FBC-31/待人工验收-个人订阅登记与公司账号核验验收) |

16 个旧 P0、Sites 预览和替换前置事项统一在 [FBC-38：历史范围复核](https://linear.app/j21nianyi/issue/FBC-38) 映射为已替代、已有技术证据但待 UAT、仍有能力缺口。原历史勾选不由迁移动作更改。

## 全局任务日志补充迁移

核对全局任务日志后，补充 [FBC-41：历史发布包清理](https://linear.app/j21nianyi/issue/FBC-41)。该项仅保留原有等待专项授权的承诺，不执行生产删除。

全局旧 ID 的活动入口统一映射：AI-PILOT-HUMANS-001 → FBC-21；FB-AIAC-WEB-LOGIN-20260928 → FBC-22；AI-CONNECTOR-UAT-001 → FBC-24；FB-AIAC-ORG-DATA-20260929 → FBC-23 / FBC-29；ASSET-LOGIN-UAT-20261010 → FBC-28；ASSET-SERVICE-CATALOG-UAT-20261010 → FBC-30。早期 START、Sites UX 和 V1.3 预览承诺统一由 FBC-38 做历史范围复核，不据旧方案重新启动开发。

## 现有 Pull Request

2026-10-15 回读：以下六个 PR 均为 Draft / Open / 未合并。早期 PR 是阶段快照，不能据此推断当前线上版本。各阶段分支为累积堆叠；审查和主线收敛单独进行。

| GitHub | Linear 跟踪 |
|---|---|
| [PR #1](https://github.com/FlipBelt/Digital-Asset-Management-Space/pull/1) | [FBC-32](https://linear.app/j21nianyi/issue/FBC-32/github-pr-1-融合-v13-资产中心ai-成果登记分类发现与扁平管理) |
| [PR #2](https://github.com/FlipBelt/Digital-Asset-Management-Space/pull/2) | [FBC-33](https://linear.app/j21nianyi/issue/FBC-33/github-pr-2-接入孵化器与登记器的受限-ai-连接器) |
| [PR #3](https://github.com/FlipBelt/Digital-Asset-Management-Space/pull/3) | [FBC-34](https://linear.app/j21nianyi/issue/FBC-34/github-pr-3-feat-完善成果登记与资产治理统一管理界面) |
| [PR #4](https://github.com/FlipBelt/Digital-Asset-Management-Space/pull/4) | [FBC-35](https://linear.app/j21nianyi/issue/FBC-35/github-pr-4-修复管理页等宽布局与账号图标居中) |
| [PR #5](https://github.com/FlipBelt/Digital-Asset-Management-Space/pull/5) | [FBC-36](https://linear.app/j21nianyi/issue/FBC-36/github-pr-5-个人订阅免审与公司账号核验入口) |
| [PR #6](https://github.com/FlipBelt/Digital-Asset-Management-Space/pull/6) | [FBC-37](https://linear.app/j21nianyi/issue/FBC-37/github-pr-6-完善数字中心账号治理员工分组与权限管理) |

本次管理文档分支从已核实的 main 基线创建，不包含上述业务分支的累积代码。

## 新任务与 PR 工作方式

1. 在本 Linear 项目查重或创建任务，写清范围、验收标准和所需证据。
2. 使用 `codex/fbc-编号-简短主题` 分支；PR 标题或描述引用对应 FBC 编号。
3. 实现任务确实随合并完成时才使用 `Fixes FBC-编号`；人工 UAT、资料核验或范围复核使用 `Related to FBC-编号`，避免随合并自动关闭。
4. 验证后在任务中记录实际命令、结果、提交和 PR；未经执行的检查不标记通过。
5. 真实业务验收由用户或指定验收人确认，发布继续遵守现有授权和先测试后正式流程。

## 原生 GitHub 集成与验收

2026-10-15 已由本人完成 Linear Code 的组织授权，仓库范围仅为 `FlipBelt/Digital-Asset-Management-Space`。Linear 设置已显示 FlipBelt 连接，仓库映射已保存至 Flipbelt China（FBC）。

- **新建方向**：GitHub → Linear。本仓库新建 Issue 自动进入 FBC；同团队其他项目的新 Linear 事项不会因此自动发布到本公开仓库。
- **已有同步事项**：同一 Issue 的字段更新可双向同步。本轮已实际核验 GitHub → Linear 的标题、描述和关闭状态，以及 Linear → GitHub 的描述更新。
- **项目归属**：原生映射只指定团队。验证 Issue #8 初次进入 FBC 时没有项目，另行人工归入“数字中心｜AI 资产中心”。本仓库自动归类由 [FBC-43](https://linear.app/j21nianyi/issue/FBC-43) 单独跟踪，启用与真实事件验收完成前仍需人工分流。
- **讨论范围**：同步线程用于两端共同可见的信息；内部资料留在内部讨论和受控证据中。不要把凭据、员工或账号明细写入同步描述或评论。
- **PR 原生关联**：现有 PR #1–#6 已分别关联 FBC-32–FBC-37；已读回 Linear 的原生 PR 对象、对应 linkedIssues 和 Draft 状态。
- **真实验证回执**：[GitHub Issue #8](https://github.com/FlipBelt/Digital-Asset-Management-Space/issues/8) 自动生成 [FBC-42](https://linear.app/j21nianyi/issue/FBC-42)。创建、更新、反向描述更新及关闭状态核对通过；GitHub 为 closed/completed，Linear 为 Done，保留记录。
- **权限边界**：用户批准的 Linear Code 权限包含代码、Actions、工作流等读写；不以安装授权替代后续代码执行、发布或业务审批授权。没有另建同步凭据、Webhook 服务或定时器。

[原生集成验收 FBC-40](https://linear.app/j21nianyi/issue/FBC-40) 与 [管理迁移验收 FBC-39](https://linear.app/j21nianyi/issue/FBC-39) 分别记录自动同步和管理入口的证据。管理文档 PR #7 已合并 main；历史业务 PR 与人工 UAT 仍按各自关口处理。

## 本仓库自动项目归类（FBC-43，已授权，真实验收中）

现有工作区的 Loops 需要 Business / Enterprise 方案。本仓库准备 GitHub Actions 工作流 `linear-project-routing.yml`，仅补充项目归属，不替代原生 Issue Sync。

- 只响应 `FlipBelt/Digital-Asset-Management-Space` 的新建 Issue。原生同步可能晚到，脚本有限等待；超时或 API 错误会明确失败，支持在 main 上用 Issue 编号手动重试。
- 通过 GitHub 事件限定仓库和编号，以精确 Issue URL 查找 Linear 附件，并校验 `syncedWith` 中唯一 GitHub 条目的全局 node ID。两端 ID 字符串不同时，向 GitHub 只读 GraphQL 解析双方 ID，统一格式后必须为同一 Issue，并同时核对仓库、URL 与编号；无法核验则不写入。官方定义为可选的补充 metadata 不作为必填身份字段。普通手工链接、多个匹配、归档/回收站事项、其他团队和已有任意项目均不写入。
- 目标固定为 FBC 团队中的“数字中心｜AI 资产中心”（`77af2f8a-8f02-4816-abdd-ce59f3d747a2`）。写前复查、仅修改 `projectId`、写后回读；标题、描述、状态、负责人和标签不由此脚本修改。
- CIS 与 FBC 共用团队，但脚本不扫描团队、不处理 CIS 仓库、不改 FBC 默认值；已有 CIS 项目归属会跳过。Linear 的更新接口没有项目条件写入，写前复查只能缩小人工同时分配项目的竞争窗口，不能保证原子条件更新。

### 启用、验收与停用

1. 用户创建专用 Linear API Key，仅勾选 Read / Create issues（该权限包含 issueUpdate）、仅允许 FBC 团队，关闭通用 Write、Admin 和 Create comments。Linear 的 Key 权限只能限制到团队，因 FBC 包含 CIS，凭据本身仍有 FBC 内其他事项的读写能力；代码护栏限制本工作流的实际操作。
2. 用户将 Key 直接存入**本仓库** Actions Secret `LINEAR_PROJECT_ROUTING_API_KEY`，不在聊天、Issue、PR、代码或日志中粘贴。新凭据权限与存储须单独确认，既有 Linear Code 安装授权不替代这一步。
3. 授权后合并工作流，在 GitHub 新建无业务数据的验证 Issue；独立读回原生同步对象、自动项目归属及 Actions 运行结果，并比较 CIS 事项的项目/团队/状态/更新时间。仅 mock 测试通过不等于已启用。
4. 停用时禁用本仓库该工作流或撤回对应提交，再移除专用 Secret 并撤销 Key。原生 Issue Sync 与已归类事项可以保留；CIS 和团队默认配置不变。

接口依据：[Linear Attachments](https://linear.app/developers/attachments)、[API Key 权限](https://linear.app/docs/api-and-webhooks)、[issues:create 支持 issueUpdate 的官方变更](https://linear.app/changelog/2025-12-04-openai-codex-agent)、[官方固定 GraphQL schema](https://github.com/linear/linear/blob/4789abd2d1458ec739030ddf017199def1ec8623/packages/sdk/src/schema.graphql)、[GitHub 节点 ID 迁移与服务端解析](https://docs.github.com/en/graphql/guides/migrating-graphql-global-node-ids)。
