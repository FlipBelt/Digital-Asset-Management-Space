# AI 资产中心远程 MCP

状态：2026-10-16 已完成测试→正式技术发布与独立公网核验，当前应用提交 `ed0c4039fb23ad33c5796f0dbeb8afb25af4b792`，正式入口 `https://jtzhzt.flipbeltchina.com/mcp`。关联任务 FBC-222。

| 范围 | 当前证据与边界 |
| --- | --- |
| 技术发布 | `ed0c403` scope兼容热修已依次发布测试与正式，99项OAuth定向回归通过，schema保持 `f13g20261016`。测试真实回退再应用，75张旧业务表保持；本轮未迁移schema、未改配置或代理。`210b85f` 首次发布与 `a160657` 扩展参数热修保留为历史证据。 |
| ChatGPT 本人连接 | 新App已本人OAuth连接；从“在聊天中试用”打开的ChatGPT Work新对话中，一次只读 get_capabilities 成功。宿主可见摘要为 remote_tool_count=13、四个业务scope、streamable_http/OAuth2及最终确认web_only；未导出原始服务tool trace，不将宿主摘要或“已连接”推断伪称原始日志/connected字段。本轮无业务写入，wrapper专门新对话验证另记。 |
| 团队 Workspace | 已确认当前操作者为FB GPT Owner；新资产App `asdk_app_6ad1de5fb8788191b73c1aaab021a067` 从FB GPT管理入口创建，目录归属FB GPT。用户已本人OAuth连接并确认发布及恢复团队可用；独立reload显示已启用、可用范围适用于FB GPT所有人、可用已勾选、13工具，禁用新增工具且站点访客开关关闭，第二tab重载保持。App版本1.0.0与内置插件版本0.2.0独立；组织可用不代替每位成员授权。 |
| 团队市场 | 新App依赖修订 `da7ab28` 已推送main、CI成功并实际同步FB GPT；wrapper已启用、适用于所有FB GPT成员，两项Skill和必需App链接正确，访客开关关闭并重载持久化。成员端wrapper新对话的一次只读能力回读成功，与直接App是两个独立新对话各一次，团队技术接入验证通过；插件仍0.2.0，其他成员各自OAuth及真实业务UAT未逐人实测。 |
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

本轮ChatGPT故障根因为授权请求完全省略scope，而客户端已通过DCR登记业务scope；此前服务端将其一律拒绝。`ed0c403` 仅在客户端注册的redirect_uris恰为单个精确 `https://chatgpt.com/connector_platform_oauth_redirect`、本次callback精确匹配、resource显式正确且scope字段完全缺省时，使用该客户端已登记的业务scope；已登记较小范围时不扩成四项。显式空scope、未知或超出登记范围的scope、重复参数、非精确或多个callback、缺失/错误resource均不因此放行。state、PKCE S256、本人预览与明确同意保持必需，不增加OIDC或自动批准。

## 部署与回执

本轮已按用户授权完成发布。后续发布仍需对应环境授权；正式与测试分别使用各自数据库、配置、会话 Cookie 和资源地址，不得以测试 token 调用正式资源。以下保留操作边界。

1. 记录当前运行提交、前端哈希、schema 和服务配置，备份数据库并核验备份。比较当前线上版本与候选，保留已有变更。首次远程发布从已核实的线上 `1b216a8` / f13f 升至 `210b85f` / f13g；扩展参数热修升至 `a160657`，本轮scope兼容热修再升至 `ed0c403`。开发基线 fa56c38 不能替代运行基线；pg_restore --list 也不等于本次线上备份已完成恢复演练。
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

4. 技术 readback：ready 为 200；匿名 MCP 返回 401 及 resource_metadata challenge；元数据 resource/issuer 指向测试；GET/DELETE 使用有效 token 后为 405；普通 REST 地址不得被当成 MCP。ChatGPT本人授权、直接App与wrapper各一次独立新对话只读能力查询已完成；真实撤销、草稿与最终登记流程仍按业务验收记录，千问本轮暂不测试。
5. 正式部署在测试证据和对应授权后进行。将上面两地址换为正式 `/` 和 `/mcp`，保留其他受管设置；不要覆盖身份凭据。正式 Nginx 代理为 8100，测试为 8200。代理重置 X-Forwarded-For 为真实 peer，避免伪造和全员共享限流桶；同意页禁止 iframe、关闭 query access log、no-referrer/no-store。
6. 服务单 Uvicorn worker 使用内存限流；如扩大到多进程/多实例，必须先安排集中限流，不以本轮单进程限流宣称跨实例防护。

首次远程发布已在实际服务器完成 nginx -t 与代理安装；后续两次OAuth热修均未改代理。Windows 本地没有 nginx 的限制不替代目标服务器校验。

本轮 `ed0c403` 四份原始回执位于 `.deploy-artifacts/remote-mcp-oauth-scope/ed0c4039fb23/`：`test-server-PASS.json`、`test-public-PASS.json`、`production-server-PASS.json`、`production-public-PASS.json`。测试与正式服务发布分别于2026-10-16 17:01:06、17:06:25（北京时间）完成，最终公网核验分别于17:07:43、17:07:48完成；每环境各26个静态文件及协议/认证边界检查通过。本轮两环境均未迁移schema、未改配置或代理，75张业务表保持；测试真实回退再应用，正式回退与线上备份恢复未执行。

以下为此前 `a160657` 扩展参数热修及旧App连接的历史证据，不代表当前运行版本或新团队App的发布状态。

`a160657` 四份原始回执位于 `.deploy-artifacts/remote-mcp-oauth-extension/a160657200a9/`：`test-server-PASS.json`、`test-public-PASS.json`、`production-server-PASS.json`、`production-public-PASS.json`。正式发布于2026-10-16 12:57:33（北京时间）完成；测试与正式的最终公网核验分别于12:58:16、12:58:20完成。两环境独立核验各26个静态文件、ready、resource/issuer、OAuth元数据、匿名认证边界与同意页安全头。服务器自动回执中的人工UAT字段保留false；之后发生的本人连接以用户确认及宿主调用另记，不篡改历史回执。测试已演练保留 schema 的应用回退，正式回退未执行，数据库备份仅完成生成与目录核验，未进行线上恢复演练。

ChatGPT本人连接以用户确认及可见宿主调用为证，本地截图为 `.local/connection-proof/chatgpt-connected-a160657.png`；原始工具响应未完整导出，不能将截图或宿主转述标成原始服务日志。后续浏览器会话失效不改写这次已记录的调用结果，组织发布状态仍须重新回读。

## 团队与个人分发

本地直接 HTTP MCP 可在宿主配置 URL，并选择 OAuth 2.1/DCR。新候选包需要显式远程配置，不能把旧本机启动器当成云端连接器。

当前团队App为 `asdk_app_6ad1de5fb8788191b73c1aaab021a067`，目录归属FB GPT，已本人OAuth连接、发布并启用。证据为 `.local/connection-proof/team-app-connected-ed0c403.png` 与 `.local/connection-proof/team-app-published-enabled-13tools.png`；后者及第二tab独立重载确认FB GPT全员可用、13工具、禁用新增工具、站点访客关闭。已核对操作者为FB GPT Owner，证据 `.local/connection-proof/fb-gpt-owner-confirmed.png`；不能再把先前失败归因于操作者缺少Owner身份。成员仍需各自完成OAuth，App可用不授予业务数据权限。

新App直接宿主的一次只读能力回读截图为 `.local/connection-proof/team-app-host-capabilities-ed0c403.png`。宿主摘要显示13工具、四个业务scope、streamable_http/OAuth2及最终确认web_only，本轮无业务写入；未导出原始服务tool trace，不将宿主摘要写成原始响应日志。直接App验证与wrapper新对话验证分别记录。

成员端“飞比特AI成果助手”wrapper（`Plugin_98ded03801bc8191a0a2bc10dbdff428`）详情中的“在聊天中试用”也已在独立新对话完成单次只读 get_capabilities。宿主可见回读为remote_tool_count=13，四个scope为asset:draft、asset:read、incubation:read、incubation:write，确认字段为 `confirmation=web_only`，没有 `final_confirmation_mode` 字段。截图 `.local/connection-proof/team-wrapper-host-capabilities-da7ab28.png`；未导出原始服务tool trace，不将宿主回读摘要写成原始日志。直接App与wrapper各一次、共两个独立新对话，均无业务写入。wrapper Admin重载确认已启用、全员可用、两项Skill、必需新App及访客开关关闭持久化，截图 `.local/connection-proof/team-wrapper-enabled-new-app-da7ab28.png`。

团队市场新App依赖发布revision为 `da7ab2884e77b1003f1b801eea39305f0431df3e`，[CI 38879959551](https://github.com/J21NIANYI/flipbelt-plugin-marketplace/actions/runs/38879959551) success。155个tracked路径/模式/Git SHA匹配，4个变更blob完整字节一致，其余151个不变。本轮实际“立即同步”回读exact revision，统计0添加、1更新、4未变、0源删除、0失败，截图 `.local/connection-proof/team-market-synced-da7ab28.png`。wrapper详情与专门新对话只读验证均通过，必需App准确指向新App。插件保持0.2.0，以市场revision区分这次仅App依赖、provenance、根README及CHANGELOG四文件修订；App目录版本1.0.0独立。知识库App不能用于资产中心。

最终团队main及后台已同步revision为文档收口 `67816e8d3a29531f4870225cf8345b7280f1aafb`，[CI 38880809304](https://github.com/J21NIANYI/flipbelt-plugin-marketplace/actions/runs/38880809304) success。该提交只补根README与CHANGELOG，137个插件blob与da7ab28完全一致；155个远端文件模式与SHA及两份文档字节已核对。后台再次同步回读0添加、0更新、5未变、0删除、0失败，截图 `.local/connection-proof/team-market-final-synced-67816e8.png`；不把文档同步重复计为插件变更或重新执行工具验收。

旧绑定revision `aaa3c4a27e0388048c927e8f95882d8fc1f61f25` 及截图 `.local/connection-proof/team-market-synced-aaa3c4a.png` 仅保留历史，不代表当前新App依赖。

旧revision导入详情曾显示FB GPT目录、版本0.2.0和两项Skill，旧App标记“必需”；截图 `.local/connection-proof/team-plugin-0.2.0-required-app.png` 仅证明当时绑定，不能证明当前新App依赖已同步。导入验证不改变来源清单中生成时的默认验证标记。

旧App `asdk_app_6ad1a995522c819197dd69e6aca6f71f` 曾出现草稿、共享设置加载失败及Workspace插件权限错误，当时的批准/发布失败截图为 `.local/connection-proof/team-app-admin-approval-required.png` 与 `.local/connection-proof/app-workspace-publish-permission.png`。这是旧App历史，不改写此前本人连接和能力调用，也不再作为当前新App的阻塞状态。旧App归属问题不靠猜测下结论；本轮从FB GPT管理入口新建并回读了新App的目录、发布及启用状态，未绕过权限。

千问办公企业后台的连接器与专家套件分别管理：已创建并 enabled 的连接器使用正式 `/mcp` 与 OAuth 2.1 DCR。用户决定暂不测试千问，保留现有技术配置和最终 ZIP；今后实际导入、成员授权与工具发现另行确认。不能仅凭后台启用或两项技能存在报告接通。

## 迁移与回退

`f13g20261016` 仅新增 mcp_oauth_clients、mcp_oauth_requests、mcp_oauth_grants 及相关索引；旧设备授权和业务表不改。优先回退应用并关闭 AGENT_MCP_ENABLED，保留增量表及审计，旧 stdio 仍使用原链路。

空的三个新增表可 downgrade 到 f13f；任一表有数据时迁移主动拒绝降级，防止删除已登记客户端或授权状态。不能为通过回退而清空授权表。若确需移除 schema，须另行确认导出、撤销和保留方案。

## 验证记录（2026-10-16）

- 本轮scope兼容热修OAuth定向回归99/99通过，证据 `.local/subscription-verification/cca00ef564/pytest.log`。覆盖精确ChatGPT callback缺scope时沿用已注册范围、较小范围不扩权、本人预览/同意、显式错误scope/resource及callback变体拒绝，并保留此前扩展参数、重复与解析限制回归。99项包含此前用例，不能与历史运行简单相加。
- 此前 `a160657` 扩展参数热修OAuth回归85/85通过，涵盖合成 prompt、id_token_hint 与不透明扩展的完整授权码交换及不落库/不反射。历史证据 `.local/subscription-verification/7a800225a9/pytest.log`；该隔离PG已停止，55439端口已关闭。
- 首次实现阶段101个 OAuth、远程工具与旧 stdio 回归通过：49个 OAuth（含真实 PostgreSQL 双连接刷新/撤销竞态）、28个远程 MCP、24个旧连接器兼容。证据 `.local/subscription-verification/e0768e5332`。这一轮 SDK 夹具 setup error 单独记录，未计为通过；修复后在下一轮实际运行。
- 真实 MCP SDK 1.30.0 的 HTTP 初始化、13 工具发现和 get_capabilities 调用通过；同时完成既有资产可见性与会话安全回归，共 10 项，证据目录 `.local/subscription-verification/eb52edc8d3`。两轮合计 111 个不同目标检查通过。
- 独立新集群迁移 f13f → f13g → f13f → f13g 通过，75 张既有业务表 schema 和种子数据摘要保持。依次加入合成 client、request、grant 后，每次 downgrade 均拒绝，revision、全部授权记录及旧表保持。关闭开关后 GET/POST MCP 为 404。证据 `.local/remote-mcp-rehearsal/81b705162f/REHEARSAL.md`；集群已停止。
- 后端新增模块及相关文件 Ruff F/I、差异检查通过。测试使用本工作区 `uv sync --frozen --extra dev` 创建的独立环境，无新增后端依赖或锁文件修改。
- 两项 Skill 校验通过，App绑定打包回归20/20通过。旧候选摘要仅保留历史；当前0.2.0下载包、两市场发布和Workspace开放状态见[分发说明](AI-ASSET-PLUGIN-DISTRIBUTION.md)。
- 前端同意页与登录跳转共 17 项执行回归通过，包含 13 个组件用例和 4 个真实 helper 用例；npm run build（含类型检查）通过。登录返回 URL 不带 request_token；页内采用同源 sessionStorage 短时恢复，顶栏等全局入口由统一过滤处理。
- 独立收口已复核 family 锁、本人权限、代理 IP、防 iframe、登录 URL 脱敏和分发来源摘要。双环境发布、新App本人连接、Admin发现13工具、发布启用持久化回读及团队市场da7ab28同步已完成；直接App与成员端wrapper在两个独立新对话各一次只读能力回读成功，技术接入验证通过。其他成员各自OAuth、全部工具逐项调用及真实业务UAT未逐人实测，千问本轮暂不测试。

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
