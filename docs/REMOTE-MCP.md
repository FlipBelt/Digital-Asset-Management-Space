# AI 资产中心远程 MCP

状态：2026-10-16 本地实现与隔离验证，尚未部署或完成真实宿主验收。关联任务 FBC-222。候选地址 `https://jtzhzt.flipbeltchina.com/mcp` 只有部署并独立回读后才能作为可用服务分发。

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
- 本人网页 `/agent/oauth` 使用既有登录和 cookie CSRF。先读取并绑定本人预览，再由本人明确允许或拒绝。客户端名称为自报信息；页面提示未经企业认证。
- 默认 access token 1 小时，refresh family 固定 30 天；刷新不延长 family 生命周期。DCR client/secret 在连接存续期间不自动过期。数据库只保存 secret、code 和 token 的哈希；日志不得记录这些值或待同意 handle。
- 重放旧 refresh 或人工撤销会撤销整个 family。稳定的 PostgreSQL advisory 事务锁统一采用 family → grant 行的顺序，防止并发刷新逃过撤销。
- 每次工具调用重新核实在职员工、用户有效性与权限；管理员通过远程连接也不获得额外管理员可见性。OAuth scope 只能进一步收窄权限。
- 四个 scope 为 asset:read、asset:draft、incubation:read、incubation:write。列表按 scope 过滤，调用前再次检查。草稿及孵化摘要保持本人私有，每次变更使用 request_id。
- 远程附件只接受用户指定文件的 content_base64，解码最大 1,000,000 字节，仍执行既有图片/ZIP 内容校验；不接受 file_path。不要把服务器路径当成用户本机路径。旧 stdio 的附件能力与上限独立保留。
- 最终登记仍由本人打开 confirmation_url 核对确切草稿版本和共享范围；机器连接不能代点确认，待审核不等于业务验收。

千问兼容只对精确形态启用：自报 QwenWork/QoderWork、public none、sole callback `qwenwork-cn://mcp-oauth`、code、authorization_code+refresh_token、application_type 缺省或 native。只有该形态完全缺失 resource/scope 时补默认值；显式空值、重复、错误受众等仍拒绝。此规则须在目标企业客户端实测。

## 部署候选

需先获得对应环境部署授权。正式与测试分别使用各自数据库、配置、会话 Cookie 和资源地址；不得以测试 token 调用正式资源。

1. 记录当前运行提交、前端哈希、schema 和服务配置，备份数据库并验证备份可恢复。比较当前线上版本与候选基线，保留线上已有变更。候选开发基线为 fa56c38，不是未验证的部署目标。
2. 先在测试环境部署后端和前端，迁移到 `f13g20261016`，安装本轮 Nginx 配置并在服务器执行 `nginx -t` 后 reload。开启前先用无效凭据验证认证边界与元数据。
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

4. 测试 readback：ready 为 200；匿名 MCP 返回 401 及 resource_metadata challenge；元数据 resource/issuer 指向测试；GET/DELETE 使用有效 token 后为 405；普通 REST 地址不得被当成 MCP。本人完成千问或 ChatGPT OAuth，确认 tools/list、本人身份、scope、撤销、必要草稿流程。
5. 正式部署在测试证据和对应授权后进行。将上面两地址换为正式 `/` 和 `/mcp`，保留其他受管设置；不要覆盖身份凭据。正式 Nginx 代理为 8100，测试为 8200。代理重置 X-Forwarded-For 为真实 peer，避免伪造和全员共享限流桶；同意页禁止 iframe、关闭 query access log、no-referrer/no-store。
6. 服务单 Uvicorn worker 使用内存限流；如扩大到多进程/多实例，必须先安排集中限流，不以本轮单进程限流宣称跨实例防护。

当前 Windows 环境没有 nginx 可执行文件，不能声称已通过 nginx -t；必须在实际目标服务器校验。

## 团队与个人分发

本地直接 HTTP MCP 可在宿主配置 URL，并选择 OAuth 2.1/DCR。新候选包需要显式远程配置，不能把旧本机启动器当成云端连接器。

ChatGPT 团队插件还需管理员在 Workspace 注册真实的资产中心 MCP App，完成本人连接，再取得实际技术标识绑定 `.app.json`。知识库 App ID 不能用于资产中心，也不能凭空生成 plugin_asdk_app 标识。可用 HTTPS MCP、真实 App 注册、插件绑定、成员开放范围和本人业务授权是不同步骤。

千问办公企业后台的连接器与专家套件也分别管理：远程 URL 为部署后的 `/mcp`，认证为 OAuth 2.1 DCR。候选 ZIP 包含配置不代表企业策略已开放；需要管理员实际添加/启用连接器并验证工具发现。不能仅更新两项技能就报告接通。

## 迁移与回退

`f13g20261016` 仅新增 mcp_oauth_clients、mcp_oauth_requests、mcp_oauth_grants 及相关索引；旧设备授权和业务表不改。优先回退应用并关闭 AGENT_MCP_ENABLED，保留增量表及审计，旧 stdio 仍使用原链路。

空的三个新增表可 downgrade 到 f13f；任一表有数据时迁移主动拒绝降级，防止删除已登记客户端或授权状态。不能为通过回退而清空授权表。若确需移除 schema，须另行确认导出、撤销和保留方案。

## 本地验证回执（2026-10-16）

- 101 个 OAuth、远程工具与旧 stdio 回归通过：49 个 OAuth（含真实 PostgreSQL 双连接刷新/撤销竞态）、28 个远程 MCP、24 个旧连接器兼容。证据目录 `.local/subscription-verification/e0768e5332`。这一轮 SDK 夹具 setup error 单独记录，未计为通过；修复后在下一轮实际运行。
- 真实 MCP SDK 1.30.0 的 HTTP 初始化、13 工具发现和 get_capabilities 调用通过；同时完成既有资产可见性与会话安全回归，共 10 项，证据目录 `.local/subscription-verification/eb52edc8d3`。两轮合计 111 个不同目标检查通过。
- 独立新集群迁移 f13f → f13g → f13f → f13g 通过，75 张既有业务表 schema 和种子数据摘要保持。依次加入合成 client、request、grant 后，每次 downgrade 均拒绝，revision、全部授权记录及旧表保持。关闭开关后 GET/POST MCP 为 404。证据 `.local/remote-mcp-rehearsal/81b705162f/REHEARSAL.md`；集群已停止。
- 后端新增模块及相关文件 Ruff F/I、差异检查通过。测试使用本工作区 `uv sync --frozen --extra dev` 创建的独立环境，无新增后端依赖或锁文件修改。
- 两项 Skill 校验、15 项打包回归和候选生成后 --check 通过。0.2.0 候选 ZIP 的 SHA-256 为 5870e236b23c8d84761381696c2065001fa7f5edc5b4ab880c5cc0babd9b3f0a。
- 前端同意页与登录跳转共 17 项执行回归通过，包含 13 个组件用例和 4 个真实 helper 用例；npm run build（含类型检查）通过。登录返回 URL 不带 request_token；页内采用同源 sessionStorage 短时恢复，顶栏等全局入口由统一过滤处理。
- 独立收口已复核 family 锁、本人权限、代理 IP、防 iframe、登录 URL 脱敏和三种候选包来源/字节摘要，先前四项审查问题均关闭。真实千问/团队连接、生产 nginx -t、线上部署及本人业务验收尚未执行。

本地复现（在本工作区根目录执行，PG 路径替换为已安装的本机 PostgreSQL bin；脚本拒绝复用已占用的 55439 端口）：

```powershell
$env:MCP_SDK_PYTHON='<已安装 MCP 1.30.0 的 Python 绝对路径>'
.\backend\.venv\Scripts\python.exe -B scripts/rehearse-subscription-verification.py --pg-bin '<本机 PostgreSQL bin>' --tests tests/test_mcp_oauth.py tests/test_agent_mcp.py tests/test_mcp_sdk_interop.py tests/test_agent_connector.py
.\backend\.venv\Scripts\python.exe -B scripts/rehearse-remote-mcp.py --pg-bin '<本机 PostgreSQL bin>'
```

修改入口：后端 `api/v1/{agent_mcp,mcp_oauth}.py`、`core/mcp_oauth.py` 与独立 models/schemas/migration；前端 `AgentOAuthPage.vue`、路由与登录跳转过滤；代理 `deploy/account-center.https.nginx.conf` 及环境示例；已有 DeviceStart 仅增加 QwenWork/QoderWork 兼容标签。测试、说明和候选打包为配套变更。

## 验证与依据

自动验证、目标环境技术发布和真人业务验收分别记录。运行命令、隔离证据与尚未执行项见同任务交付记录；未部署前不能声称企业插件可用。

- [MCP OAuth 规范](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization)
- [OpenAI 插件认证](https://developers.openai.com/plugins/build/auth)
- [OpenAI 插件结构](https://developers.openai.com/plugins/build/plugins)
- [千问办公企业连接器](https://help.aliyun.com/zh/qwenwork/enterprise-ultimate-ai-assets-connectors)
