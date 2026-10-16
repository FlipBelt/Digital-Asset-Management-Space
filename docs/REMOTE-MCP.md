# AI 资产中心远程 MCP

状态：2026-10-16 已完成测试→正式技术发布与独立公网核验，当前应用提交 `a160657200a93f05050d5c69d31ff7d0f966a448`，正式入口 `https://jtzhzt.flipbeltchina.com/mcp`。关联任务 FBC-222。

| 范围 | 当前证据与边界 |
| --- | --- |
| 技术发布 | `210b85f` 首次远程 MCP 发布完成；`a160657` OAuth 扩展参数热修已依次发布测试与正式，schema 保持 `f13g20261016`。测试执行真实应用回退再应用，75 张旧业务表保持；热修未迁移 schema、未改配置或代理。 |
| ChatGPT 本人连接 | 用户已点击允许并确认已连接；在 ChatGPT Work 的 FB GPT 新对话中，一次只读 get_capabilities 调用成功，返回 remote_tool_count=13、四个业务 scope 及本人身份。响应没有 role 或 connected 字段；本次能力查询不代表13个工具均已实测或登记闭环已验收。 |
| 团队 Workspace | 真实资产 App `asdk_app_6ad1a995522c819197dd69e6aca6f71f` 已创建，此前当前账号的本人OAuth与一次能力查询成功。用户反馈App已发布，但随后独立刷新及新tab的WORKSPACE范围回读仍为草稿、共享设置加载失败，发布后报工作空间插件权限错误；团队插件在工作空间列表显示禁用/不可用，原因未确定。管理员发布及恢复团队可用性仍待处理。App版本1.0.0与内置插件版本0.2.0独立。 |
| 团队市场 | `aaa3c4a` 已推送main，绑定真实资产App；[CI 38856116286](https://github.com/J21NIANYI/flipbelt-plugin-marketplace/actions/runs/38856116286) success，155个tracked blob路径/模式/Git SHA匹配，15个变更文件远端字节回读一致。FB GPT市场已同步确切revision `aaa3c4a`，重载后成果助手显示已导入，详情中的真实资产App为必需；随后工作空间列表显示该团队插件禁用/不可用，不能据市场同步报告组织可用。 |
| 个人市场 | `b34d776` 已发布，CI成功并完成78个远端 blob 回读；具体入口见[分发说明](AI-ASSET-PLUGIN-DISTRIBUTION.md)。 |
| 千问办公 | 企业 OAuth DCR 连接器已创建并 enabled，最终 ZIP 已交付。用户明确暂不测试千问，本人授权、工具发现和业务验收保持未验证。 |

## 问题与接入方式

0.1.0 插件只分发登记器与孵化器技能；团队云端没有 Windows Python/DPAPI 运行环境，因此看不到业务工具。此前的安装成功不代表 MCP 已接通。本轮在资产中心自身的域名、数据库、员工会话与权限上提供远程 MCP，只参考知识库协议，不改知识库或复用其凭据。

| 运行端 | 传输与授权 | 实际工具 |
| --- | --- | --- |
| 千问办公、Codex HTTP、团队云端 | `/mcp`，Streamable HTTP JSON response，宿主管理 OAuth | 13 个业务工具；无 start_connection、complete_connection、disconnect |
| 既有 Windows 本机 | Python stdio，设备码与本人网页批准，DPAPI 保存本人凭据 | 16 个工具，保留设备授权与本机附件入口 |

远程工具：get_capabilities、search_assets、get_asset、create_asset_draft、update_asset_draft、get_my_incubations、get_incubation、save_snapshot、operation_status、get_asset_details、save_asset_details、search_people、upload_asset_attachment。以实际 tools/list 和 get_capabilities 回执为准。认证失败由宿主发现 OAuth 并打开网页，无需在远程工具中寻找本机授权函数。

接口是无会话的 POST JSON；GET/DELETE 认证后返回 405，未实现 SSE。官方 MCP SDK 允许服务选择 JSON response；反向代理关闭缓冲。仅暴露受限业务操作，不提供发布、最终确认、管理员或数据库工具。

## 身份与授权边界

- 受保护资源发现：`/.well-known/oauth-protected-resource/mcp`；授权服务元数据：`/.well-known/oauth-authorization-server/mcp-oauth`。
- 独立授权服务 `/mcp-oauth/` 支持动态客户端注册、authorization_code/S256、轮换 refresh_token 和撤销。每个请求绑定 client、确切 callback、resource、issuer 与 scopes。
- authorize 与 token 按 RFC 6749 忽略未识别的扩展参数：先执行严格编码、长度、数量与重复校验，再仅传递已识别字段。扩展不持久化、不反射到响应；resource、scope、state、PKCE、callback 及本人同意校验保持。
- 本人网页 `/agent/oauth` 使用既有登录和 cookie CSRF。先读取并绑定本人预览，再由本人明确允许或拒绝。客户端名称为自报信息；页面提示未经企业认证。
- 默认 access token 1 小时，refresh family 固定 30 天；刷新不延长 family 生命周期。DCR client/secret 在连接存续期间不自动过期。数据库只保存 secret、code 和 token 的哈希；日志不得记录这些值或待同意 handle。
- 重放旧 refresh 或人工撤销会撤销整个 family。稳定的 PostgreSQL advisory 事务锁统一采用 family → grant 行的顺序，防止并发刷新逃过撤销。
- 每次工具调用重新核实在职员工、用户有效性与权限；管理员通过远程连接也不获得额外管理员可见性。OAuth scope 只能进一步收窄权限。
- 四个 scope 为 asset:read、asset:draft、incubation:read、incubation:write。列表按 scope 过滤，调用前再次检查。草稿及孵化摘要保持本人私有，每次变更使用 request_id。
- 远程附件只接受用户指定文件的 content_base64，解码最大 1,000,000 字节，仍执行既有图片/ZIP 内容校验；不接受 file_path。不要把服务器路径当成用户本机路径。旧 stdio 的附件能力与上限独立保留。
- 最终登记仍由本人打开 confirmation_url 核对确切草稿版本和共享范围；机器连接不能代点确认，待审核不等于业务验收。

千问兼容只对精确形态启用：自报 QwenWork/QoderWork、public none、sole callback `qwenwork-cn://mcp-oauth`、code、authorization_code+refresh_token、application_type 缺省或 native。只有该形态完全缺失 resource/scope 时补默认值；显式空值、重复、错误受众等仍拒绝。此规则须在目标企业客户端实测。

## 部署与回执

本轮已按用户授权完成发布。后续发布仍需对应环境授权；正式与测试分别使用各自数据库、配置、会话 Cookie 和资源地址，不得以测试 token 调用正式资源。以下保留操作边界。

1. 记录当前运行提交、前端哈希、schema 和服务配置，备份数据库并核验备份。比较当前线上版本与候选，保留已有变更。首次远程发布从已核实的线上 `1b216a8` / f13f 升至 `210b85f` / f13g；本次热修从 `210b85f` 升至 `a160657`。开发基线 fa56c38 不能替代运行基线；pg_restore --list 也不等于本次线上备份已完成恢复演练。
2. 首次远程发布先在测试环境部署后端和前端，迁移到 `f13g20261016`，安装本轮 Nginx 配置并在服务器执行 `nginx -t` 后 reload。开启前先用无效凭据验证认证边界与元数据。本次 OAuth 热修仅替换对应后端文件并生成独立静态发布副本，配置、代理与 schema 保持；测试先真实回退应用再重新应用，正式发布依赖测试服务器及公网 PASS 回执。
3. 测试环境设置：

```dotenv
AGENT_CONNECTOR_ENABLED=true
AGENT_FRONTEND_URL=https://jtzhzt.flipbeltchina.com/test/
AGENT_MCP_ENABLED=true
AGENT_MCP_PUBLIC_URL=https://jtzhzt.flipbeltchina.com/test-api/mcp
AGENT_MCP_ALLOWED_ORIGINS=["https://chatgpt.com"]
AGENT_MCP_ALLOWED_REDIRECT_URIS=[]
AGENT_MCP_ACCESS_TOKEN_TTL_SECONDS=3600
AGENT_MCP_REFRESH_TOKEN_TTL_DAYS=30
```

4. 技术 readback：ready 为 200；匿名 MCP 返回 401 及 resource_metadata challenge；元数据 resource/issuer 指向测试；GET/DELETE 使用有效 token 后为 405；普通 REST 地址不得被当成 MCP。ChatGPT 本人授权及一次只读能力查询已完成；真实撤销、草稿与最终登记流程仍按业务验收记录，千问本轮暂不测试。
5. 正式部署在测试证据和对应授权后进行。将上面两地址换为正式 `/` 和 `/mcp`，保留其他受管设置；不要覆盖身份凭据。正式 Nginx 代理为 8100，测试为 8200。代理重置 X-Forwarded-For 为真实 peer，避免伪造和全员共享限流桶；同意页禁止 iframe、关闭 query access log、no-referrer/no-store。
6. 服务单 Uvicorn worker 使用内存限流；如扩大到多进程/多实例，必须先安排集中限流，不以本轮单进程限流宣称跨实例防护。

首次远程发布已在实际服务器完成 nginx -t 与代理安装；本次热修未改代理。Windows 本地没有 nginx 的限制不替代目标服务器校验。

`a160657` 四份原始回执位于 `.deploy-artifacts/remote-mcp-oauth-extension/a160657200a9/`：`test-server-PASS.json`、`test-public-PASS.json`、`production-server-PASS.json`、`production-public-PASS.json`。正式发布于2026-10-16 12:57:33（北京时间）完成；测试与正式的最终公网核验分别于12:58:16、12:58:20完成。两环境独立核验各26个静态文件、ready、resource/issuer、OAuth元数据、匿名认证边界与同意页安全头。服务器自动回执中的人工UAT字段保留false；之后发生的本人连接以用户确认及宿主调用另记，不篡改历史回执。测试已演练保留 schema 的应用回退，正式回退未执行，数据库备份仅完成生成与目录核验，未进行线上恢复演练。

ChatGPT本人连接以用户确认及可见宿主调用为证，本地截图为 `.local/connection-proof/chatgpt-connected-a160657.png`；原始工具响应未完整导出，不能将截图或宿主转述标成原始服务日志。后续浏览器会话失效不改写这次已记录的调用结果，组织发布状态仍须重新回读。

## 团队与个人分发

本地直接 HTTP MCP 可在宿主配置 URL，并选择 OAuth 2.1/DCR。新候选包需要显式远程配置，不能把旧本机启动器当成云端连接器。

ChatGPT 真实资产 App 与本人连接已完成，团队0.2.0 App绑定包已推送市场main（`aaa3c4a`）。FB GPT市场已同步确切revision `aaa3c4a27e0388048c927e8f95882d8fc1f61f25` 并重载回读：0添加、1更新、4未变、0源删除、0失败，成果助手显示已导入；本地截图为 `.local/connection-proof/team-market-synced-aaa3c4a.png`。知识库 App ID 不能用于资产中心。可用 HTTPS MCP、真实 App 注册、插件绑定、成员开放范围和本人业务授权是不同步骤；App 1.0.0不表示内置插件也应改为1.0.0。

导入插件详情已显示FB GPT目录、版本0.2.0和两项Skill，应用区链接指向真实资产App并标记“必需”；截图为 `.local/connection-proof/team-plugin-0.2.0-required-app.png`。导入绑定的验证不改变来源清单中生成时的默认验证标记。

App的Workspace批准与发布仍未获得平台成功回执。先前Shared弹窗明确要求“此应用必须先获得工作空间管理员的批准，其他用户才能使用”；直接App设置显示草稿、共享设置加载失败，点击发布后返回“插件不可用，你没有权限访问此工作空间中的插件”。用户随后反馈“App已发布”，但独立刷新及新tab的WORKSPACE范围回读仍得到上述草稿与权限结果，不能把用户反馈当作平台发布成功回执。工作空间列表还显示团队插件“飞比特AI成果助手”禁用/不可用；其原因未确定，不归因于代码或用户操作。管理员发布及恢复团队可用性仍待处理，未绕过权限。截图为 `.local/connection-proof/team-app-admin-approval-required.png` 与 `.local/connection-proof/app-workspace-publish-permission.png`。这些后续状态不改写此前当前账号已完成OAuth和一次能力调用的事实。

千问办公企业后台的连接器与专家套件分别管理：已创建并 enabled 的连接器使用正式 `/mcp` 与 OAuth 2.1 DCR。用户决定暂不测试千问，保留现有技术配置和最终 ZIP；今后实际导入、成员授权与工具发现另行确认。不能仅凭后台启用或两项技能存在报告接通。

## 迁移与回退

`f13g20261016` 仅新增 mcp_oauth_clients、mcp_oauth_requests、mcp_oauth_grants 及相关索引；旧设备授权和业务表不改。优先回退应用并关闭 AGENT_MCP_ENABLED，保留增量表及审计，旧 stdio 仍使用原链路。

空的三个新增表可 downgrade 到 f13f；任一表有数据时迁移主动拒绝降级，防止删除已登记客户端或授权状态。不能为通过回退而清空授权表。若确需移除 schema，须另行确认导出、撤销和保留方案。

## 验证记录（2026-10-16）

- 本次热修完整 OAuth 定向回归85/85通过，涵盖合成 prompt、id_token_hint 与不透明扩展的完整授权码交换、不落库/不反射、已知字段负向、重复与解析限制。证据 `.local/subscription-verification/7a800225a9/pytest.log`；隔离PG已停止，55439端口已关闭。85项包含此前OAuth用例，不能与历史运行简单相加。
- 首次实现阶段101个 OAuth、远程工具与旧 stdio 回归通过：49个 OAuth（含真实 PostgreSQL 双连接刷新/撤销竞态）、28个远程 MCP、24个旧连接器兼容。证据 `.local/subscription-verification/e0768e5332`。这一轮 SDK 夹具 setup error 单独记录，未计为通过；修复后在下一轮实际运行。
- 真实 MCP SDK 1.30.0 的 HTTP 初始化、13 工具发现和 get_capabilities 调用通过；同时完成既有资产可见性与会话安全回归，共 10 项，证据目录 `.local/subscription-verification/eb52edc8d3`。两轮合计 111 个不同目标检查通过。
- 独立新集群迁移 f13f → f13g → f13f → f13g 通过，75 张既有业务表 schema 和种子数据摘要保持。依次加入合成 client、request、grant 后，每次 downgrade 均拒绝，revision、全部授权记录及旧表保持。关闭开关后 GET/POST MCP 为 404。证据 `.local/remote-mcp-rehearsal/81b705162f/REHEARSAL.md`；集群已停止。
- 后端新增模块及相关文件 Ruff F/I、差异检查通过。测试使用本工作区 `uv sync --frozen --extra dev` 创建的独立环境，无新增后端依赖或锁文件修改。
- 两项 Skill 校验通过，App绑定打包回归20/20通过。旧候选摘要仅保留历史；当前0.2.0下载包、两市场发布和Workspace开放状态见[分发说明](AI-ASSET-PLUGIN-DISTRIBUTION.md)。
- 前端同意页与登录跳转共 17 项执行回归通过，包含 13 个组件用例和 4 个真实 helper 用例；npm run build（含类型检查）通过。登录返回 URL 不带 request_token；页内采用同源 sessionStorage 短时恢复，顶栏等全局入口由统一过滤处理。
- 独立收口已复核 family 锁、本人权限、代理 IP、防 iframe、登录 URL 脱敏和分发来源摘要。双环境发布及ChatGPT本人连接已完成；用户反馈App已发布，但独立回读尚未生效，App管理员发布及恢复团队可用性仍待处理。全部工具及真实登记业务验收保持独立，千问本轮暂不测试。

本地复现（在本工作区根目录执行，PG 路径替换为已安装的本机 PostgreSQL bin；脚本拒绝复用已占用的 55439 端口）：

```powershell
$env:MCP_SDK_PYTHON='<已安装 MCP 1.30.0 的 Python 绝对路径>'
.\backend\.venv\Scripts\python.exe -B scripts/rehearse-subscription-verification.py --pg-bin '<本机 PostgreSQL bin>' --tests tests/test_mcp_oauth.py tests/test_agent_mcp.py tests/test_mcp_sdk_interop.py tests/test_agent_connector.py
.\backend\.venv\Scripts\python.exe -B scripts/rehearse-remote-mcp.py --pg-bin '<本机 PostgreSQL bin>'
```

修改入口：后端 `api/v1/{agent_mcp,mcp_oauth}.py`、`core/mcp_oauth.py` 与独立 models/schemas/migration；前端 `AgentOAuthPage.vue`、路由与登录跳转过滤；代理 `deploy/account-center.https.nginx.conf` 及环境示例；已有 DeviceStart 仅增加 QwenWork/QoderWork 兼容标签。测试、说明和候选打包为配套变更。

## 验证与依据

自动验证、目标环境技术发布、本人连接、组织开放和真人业务验收分别记录。运行命令、隔离证据与尚未执行项见同任务交付记录；一次能力查询不能替代全部工具或登记闭环验收。

- [MCP OAuth 规范](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization)
- [OpenAI 插件认证](https://developers.openai.com/plugins/build/auth)
- [OpenAI 插件结构](https://developers.openai.com/plugins/build/plugins)
- [千问办公企业连接器](https://help.aliyun.com/zh/qwenwork/enterprise-ultimate-ai-assets-connectors)
