# 资产中心连接器配置

版本：0.2.0。使用资产中心受限连接器；插件中的声明不会创建服务、完成本人授权或替代业务确认。先查看 SOURCE-PROVENANCE.json：workspace-app-candidate 是团队 App 引用候选，remote-oauth-candidate 是显式远程候选，local-legacy 是本机兼容模式。

## 远程 OAuth 候选

候选入口为 `https://jtzhzt.flipbeltchina.com/mcp`。**包内配置不提供部署或宿主验收结论。** 正式工程中的代码、隔离测试和包内配置分别是各自范围的证据；公开入口、宿主工具发现、逐人授权和真实登记需要独立验证回执。

个人与千问远程包包含根目录 `.mcp.json`，通过宿主 manifest 的 mcpServers 引用；服务条目采用兼容格式 type: http 与 url，不带令牌、共享 Cookie 或客户端秘密。未绑定 App 的团队本地候选也可采用此格式，但不得同步团队市场。它是 MCP 配置，`https://jtzhzt.flipbeltchina.com` 网页及 `/api/v1/agent` REST API 均不能替代 MCP 入口。远程配置由打包参数显式加入。

远程授权由宿主完成 OAuth 发现与动态客户端注册（DCR）、PKCE S256 和本人网页同意。远程业务工具不包含 start_connection、complete_connection 或 disconnect；不要把本机设备码流程套用到远程。撤销通过宿主连接设置或本人资产中心“AI 助手连接授权”页面完成，工具目录以实际获授权结果为准。

远程实现有13种业务工具：get_capabilities、search_assets、get_asset、create_asset_draft、update_asset_draft、get_my_incubations、get_incubation、save_snapshot、operation_status、get_asset_details、save_asset_details、search_people、upload_asset_attachment。工具按授权 scope 过滤；目录和能力回读均支持时才调用。远程附件输入为 file_name、content_base64，连同 asset_id、version 和 request_id；解码内容最大1,000,000字节。不能传 file_path、服务器路径或让服务端读取任意文件。没有授权文件读取/编码能力时保留附件入口，不伪造上传。

千问管理员在“AI 管理 → AI 资产管理 → 连接器”选择 MCP OAuth 2.1（DCR），待入口已部署并验证后填写完整 MCP URL，测试连接、保存并设置成员及目标端开放策略。专家套件和连接器分别核对；若该客户端未加载套件中的 MCP 声明，可在企业连接器入口配置同一服务。管理员可见或自动安装不等于成员拥有业务访问权限。

团队市场的远程包必须通过打包参数 `--team-app-id` 提供真实资产 App 标识，并同时指定 `--remote-mcp-url` 记录服务来源。参数严格接受 `asdk_app_...` 或 `plugin_asdk_app_...`；后者仅移除一次 `plugin_` 前缀，`.app.json` 最终保存 App ID 与 required: true，manifest 的 apps 指向该文件，团队包不含 `.mcp.json`。格式校验不证明 App 真实存在、对应此服务或已向组织开放；实际 ID、服务地址、成员策略和授权必须另行回读。不借用只读 Knowledge App。个人与千问包不带该 App ID。

根据 [OpenAI 团队插件管理说明](https://learn.chatgpt.com/docs/enterprise/plugin-management)，直接声明 MCP 的插件即使使用 HTTPS 也属于桌面端分发；已注册 App 应通过 `.app.json` 引用。团队 App 引用、管理员开放和成员本人授权是三个独立步骤。

## Windows 本机兼容模式

旧适配器为 Windows Python stdio MCP，使用设备码本人授权和 DPAPI 本机凭据保管，共16个工具：上述13种业务工具加 start_connection、complete_connection、disconnect。只能在实际目录存在这些工具时采用该流程；云端/Linux执行端不能直接运行此 Windows 适配器。

本机兼容模式的千问 ZIP 另带 connector/ 源码、锁文件、来源清单和 run.ps1；两 Codex 包需复用已配置的本机连接器，或从同次本机兼容千问 ZIP 获取该目录。需要 Windows、Python 3.11–3.13 和 uv；由本人在选定目录主动安装依赖：

```powershell
uv sync --frozen --no-dev --project '<连接器目录>'
```

宿主需支持本机 stdio。命令为 powershell.exe，参数依次为 -NoProfile、-File、run.ps1 的绝对路径；千问可设 FLIPBELT_CLIENT_NAME=QwenWork。启动器不下载、不自动安装、不修改执行策略或全局配置。已有同名连接器时复用。

先 get_capabilities；未连接且实际提供设备工具时调用 start_connection，向本人展示 verification_uri 和授权码，由本人登录网页批准。至少五秒后调用 complete_connection，pending 仍是待授权。凭据不得写入聊天、安装包或跨员工复制。本机 upload_asset_attachment 使用用户明确选定的绝对 file_path，最大20MB；仅限连接器实际运行端可读文件，不代表远程服务器路径已授权。

## 保存与登记

仅保存用户授权的必要结构化摘要；身份、类型和权限以服务端回读为准。每次变更保留 UUID request_id，结果未知先用原编号查询 operation_status。草稿私有；正式登记须本人打开回执 confirmation_url 核对确切版本并选择共享范围，Agent 不代点。重读状态后区分草稿、已登记待审核和真实业务验收。连接器缺失、授权失败或远程入口未验证时继续本地模式。

官方依据：[OpenAI 插件打包](https://developers.openai.com/plugins/build/plugins)、[千问企业连接器](https://help.aliyun.com/zh/qwenwork/enterprise-ultimate-ai-assets-connectors)、[千问企业专家套件](https://help.aliyun.com/zh/qwenwork/enterprise-ultimate-ai-assets-expert-kits)。OpenAI 当前推荐 portable plugin.json / mcp.json，同时保留 Codex 兼容布局；本包继续采用现有 .codex-plugin / .mcp.json 布局。千问 .qoder-plugin/plugin.json 选择来自用户提供的 v1.2.5 兼容案例；本轮加入的 MCP 引用仍需目标客户端验证，不能把格式案例当作本插件运行验收。
