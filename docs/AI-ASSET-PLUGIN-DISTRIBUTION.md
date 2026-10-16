# 登记器、孵化器统一插件分发

## 0.2.0 远程与团队 App 引用候选（2026-10-16）

本轮准备独立候选包，解决“套件仅有 Skill、远程工具未随包声明”的配置缺口。插件版本为0.2.0，Skill为0.2.3-pilot；远程代码和配置存在不等于线上已部署。候选入口 `https://jtzhzt.flipbeltchina.com/mcp` 的公开部署、本人授权与宿主调用以独立回执为准，打包器不会自动设置验证通过。

正式维护源已迁入 `C:/Users/MSI/Documents/Codex/work/asset-center-remote-mcp`，后续从正式工程中已审阅的源码与提交生成；D盘旧副本不再作为分发真源。来源清单仍分别记录提交、dirty状态及逐文件摘要，不能以旧Git基线替代未提交文件内容。

唯一技能源仍是本项目 `.agents/skills/` 下的登记器与孵化器。两个技能共用逐字节一致的 CONNECTOR.md，区分远程13种业务工具与 Windows 旧版16个工具；前者由宿主处理 OAuth DCR、PKCE S256 和本人同意，没有 start_connection / complete_connection / disconnect。远程附件输入为内容 base64，解码最大1,000,000字节；本机旧版才使用绝对 file_path、最大20MB，远程不接受服务器路径。

### 打包配置与市场门禁

- 默认 local-legacy：保留无自动 MCP 的兼容方式；千问包携带可选 Windows 连接器，Codex 包保留连接说明。
- 显式 remote-oauth-candidate：指定 --remote-mcp-url 后，个人和千问包加入 `.mcp.json`，对应宿主 manifest 引用该文件。无App的团队直连包只供本地候选核查，指定 --team-root 时必须另有 --team-app-id。兼容条目为 mcpServers → flipbelt-ai-assets → type=http/url；远程包不混入旧 Windows 运行资源。
- 显式 workspace-app-candidate：同时指定 --remote-mcp-url 与 --team-app-id，团队包仅生成 `.app.json` 和 manifest.apps；个人和千问仍为直接远程MCP，不会带团队App ID。App引用为required: true。
- 所有包的 SOURCE-PROVENANCE.json 记录 connection_profile、入口、源/分发文件摘要及未验证标记。包内没有用户令牌、客户端秘密、共享 Cookie 或虚构 App 标识。

App参数只接受严格 `asdk_app_...` 或 `plugin_asdk_app_...`，后者规范化为前者；不接受URL、空白、嵌套plugin_前缀或其他ID类别。这是本项目的窄输入边界，不是声称OpenAI只支持这一类App。真实App须由有权限的人创建，并独立核对服务地址及成员策略；打包输入不替代该回读。provenance记录规范化workspace_app_id，workspace_app_binding_verified、remote_deployment_verified与host_runtime_verified均默认false。千问企业后台仍需连接器OAuth DCR和开放策略；套件上架不会授予业务权限。

无App候选生成路径为 `work/ai-asset-plugin/0.2.0-remote-candidate/{team,personal,qwenwork}`，ZIP同目录下名为 `flipbelt-ai-asset-center-0.2.0-qwenwork.zip`；绑定App时使用下方新目录。脚本不推送或注册服务，市场同步只在显式指定目标并通过门禁后发生。来源清单记录生成时的实际dirty状态和逐文件摘要，Git基线不能单独代表未提交包内容。保留旧候选和Downloads中的0.1.0历史包，最终交付另记摘要。

```powershell
python -B -X utf8 scripts/package_ai_asset_plugin.py --output-dir work/ai-asset-plugin/0.2.0-remote-candidate --remote-mcp-url https://jtzhzt.flipbeltchina.com/mcp
python -B -X utf8 scripts/package_ai_asset_plugin.py --output-dir work/ai-asset-plugin/0.2.0-remote-candidate --remote-mcp-url https://jtzhzt.flipbeltchina.com/mcp --check
python -B -X utf8 -m unittest discover -s tests -p test_ai_asset_plugin_packaging.py -v
```

取得并回读真实团队App ID后，以新目录准备绑定包。`FLIPBELT_TEAM_APP_ID`仅填该回执中的标识；此命令不会注册App、批准用户授权或推送仓库：

```powershell
python -B -X utf8 scripts/package_ai_asset_plugin.py --output-dir work/ai-asset-plugin/0.2.0-app-candidate --remote-mcp-url https://jtzhzt.flipbeltchina.com/mcp --team-app-id $env:FLIPBELT_TEAM_APP_ID
python -B -X utf8 scripts/package_ai_asset_plugin.py --output-dir work/ai-asset-plugin/0.2.0-app-candidate --remote-mcp-url https://jtzhzt.flipbeltchina.com/mcp --team-app-id $env:FLIPBELT_TEAM_APP_ID --check
```

本轮打包定向回归20/20通过，增加App格式/别名规范化、团队独占引用、错误目标与无URL拒绝、缺App团队市场零写入，以及CLI三目标生成和--check逐字节回读。保留原有legacy、HTTPS、秘密/路径、ZIP与Windows junction门禁。测试内App标识为显式合成夹具，不作为真实App回执。

先前无App候选曾生成并以--check回读：团队11文件、个人12文件、千问11文件，ZIP SHA-256为 `5870e236b23c8d84761381696c2065001fa7f5edc5b4ab880c5cc0babd9b3f0a`。该摘要只指旧候选，说明与打包器更新后必须重新生成最终包并记录新摘要；不把它作为本轮绑定包交付。两Skill此前quick_validate均通过。部署/客户端发现/授权/登记四类证据分别核验。

官方依据：[OpenAI 插件打包](https://developers.openai.com/plugins/build/plugins)、[OpenAI 团队插件管理](https://learn.chatgpt.com/docs/enterprise/plugin-management)、[App标识格式](https://developers.openai.com/plugins/deploy/submission-errors)、[千问企业连接器](https://help.aliyun.com/zh/qwenwork/enterprise-ultimate-ai-assets-connectors)、[千问企业专家套件](https://help.aliyun.com/zh/qwenwork/enterprise-ultimate-ai-assets-expert-kits)。2026-10-16读取：OpenAI团队说明明确plugin_asdk_app标识应去掉plugin_前缀，直接MCP配置即使HTTPS仍为Desktop only。本轮维持既有兼容布局，并为团队增加必需App引用。千问MCP配置引用仍需目标客户端验证；原案例只证明.qoder-plugin元数据目录曾被接受。

## 0.1.0 历史分发记录

以下保留2026-10-15的实际发布与安装说明，属于旧本机兼容版的历史证据，不代表0.2.0候选已经发布或远程可用。

日期：2026-10-15。跟踪：[FBC-216](https://linear.app/j21nianyi/issue/FBC-216)。插件版本 0.1.0，Skill 版本 0.2.2-pilot。

当前已完成三分发、两个市场 main 推送与远端 CI/文件回读。用户已确认千问目标为允许本机 stdio MCP 的 Windows 桌面端，并明确授权提交推送两个市场仓库。两市场包提供两项 Skill 与独立连接器配置说明；千问 ZIP 另外携带 Windows 本机连接器资源。千问企业后台导入、本人授权和登记业务验收由用户实际操作确认。

## 维护与分发

唯一行为源为本项目 `.agents/skills/flipbelt-ai-asset-registrar` 与 `.agents/skills/flipbelt-ai-workflow-incubator`。插件元数据和说明在 `plugin/`，打包入口为 `scripts/package_ai_asset_plugin.py`。下游不直接修改技能。

| 目标 | 插件标识 | 内容与当前证据 |
| --- | --- | --- |
| 团队市场 flipbelt-team | flipbelt-ai-asset-center | 10文件、2技能；已推送市场main，原生Codex解析与远端CI通过 |
| 个人市场 flipbelt-personal | flipbelt-ai-asset-center-personal | 11文件、2技能；已推送市场main，保留最小根manifest，Grok市场仍仅原产品专家；原生解析与远端CI通过 |
| 千问办公 ZIP | flipbelt-ai-asset-center | 19文件、2技能、可选Windows connector资源；.qoder-plugin/plugin.json位于ZIP根，无额外嵌套目录 |

团队下游：`C:/Users/MSI/repos/codex-plugins/distributions/flipbelt-plugin-marketplace`。
个人下游：`C:/Users/MSI/repos/codex-plugins/distributions/flipbelt-personal-marketplace`。
生成目录：`work/ai-asset-plugin/0.1.0/{team,personal,qwenwork}`。
ZIP：`work/ai-asset-plugin/0.1.0/flipbelt-ai-asset-center-0.1.0-qwenwork.zip`。

当前ZIP SHA-256：`e182bc765807c3a74f356fa51caa2d846c6e7492ed98ddda9c14dbf70b71e733`，72735字节。逐文件比对、CRC、正斜杠条目和可重复生成通过；下载副本为 `C:/Users/MSI/Downloads/flipbelt-ai-asset-center-0.1.0-qwenwork.zip`。本轮将六个技能源文件统一为LF，避免Git规范化换行破坏来源哈希；前轮下载副本已更新，请使用此最终摘要核对。

项目源工作区有原有未提交改动，本次未提交源文件。来源清单明确记录 `canonical_worktree_dirty=true`、观察到的Git基线及逐文件/source-tree摘要；Git基线不能单独代表包内内容。三种包的六个技能文件逐字节一致。

## 连接器边界

连接器源码固定来自正式工程 `fa56c38f9f9b37d78ba65971f1f9b810ce8d2ddf`，仅复制四个Python模块、pyproject.toml和uv.lock；原始字节与Git换行规范化摘要均在 `plugin/connector/SOURCE-PROVENANCE.json`。本轮没有连接生产确认线上版本。

它是 Windows Python 3.11–3.13 stdio MCP → HTTPS REST API，凭据由 Windows DPAPI 加密保存；不是远程 HTTP MCP。默认业务站点不可当作MCP入口。没有真实资产App ID或远程MCP时不编造、不复用Knowledge App，也不添加自动MCP配置。

千问包携带手动安装说明和 `run.ps1`，仅在企业宿主允许Windows本机stdio时可按说明配置。安装依赖是用户主动步骤；启动器不安装、不下载、不改执行策略或全局配置。云端/Linux执行端仍需另行实现远程MCP/逐人授权适配。

两Codex包不含连接器源码或 `.mcp.json` / `.app.json`；可以复用已配置的本机连接器，或从同次千问ZIP提取connector目录。套件存在不代表工具已可调用。实际16工具和字段能力须同时由客户端工具目录与get_capabilities确认。

本人授权、私有草稿、request_id幂等和网页确切版本确认保持；缺连接器时保留本地模式。组织保存、待审核与真实业务验收分开报告。

## 更新命令

在项目根执行以下命令。脚本只生成/同步已知文件，发现下游多余文件时停止且不删除；检查全部目标后才写入，拒绝符号链接和Windows junction/reparse path。

```powershell
python -B -X utf8 scripts/package_ai_asset_plugin.py --output-dir work/ai-asset-plugin/0.1.0 --team-root C:/Users/MSI/repos/codex-plugins/distributions/flipbelt-plugin-marketplace --personal-root C:/Users/MSI/repos/codex-plugins/distributions/flipbelt-personal-marketplace
python -B -X utf8 scripts/package_ai_asset_plugin.py --output-dir work/ai-asset-plugin/0.1.0 --team-root C:/Users/MSI/repos/codex-plugins/distributions/flipbelt-plugin-marketplace --personal-root C:/Users/MSI/repos/codex-plugins/distributions/flipbelt-personal-marketplace --check
python -B -X utf8 -m unittest discover -s tests -p test_ai_asset_plugin_packaging.py -v
```

## 实际验证

- 打包回归11/11：三目标来源、逐文件内容、可重复ZIP、文件枚举顺序变化、CRLF源拒绝、未知下游文件保留、全部目标预检、链接完整性、秘密/本机路径拒绝及真实Windows junction负向回归。独立审查发现的先resolve后检查问题已修复并复核关闭；两仓暂存区原始字节已独立核对来源哈希。
- 连接器包隔离pytest 6/6：上游摘要/锁文件、16工具、真实stdio初始化、无凭据时在HTTP前停止，以及缺uv/环境/依赖的失败路径。使用已有隔离测试解释器，未安装新依赖；测试屏蔽HTTPX和非回环网络，仅允许Windows事件循环内部回环。
- Skill官方quick_validate：两项均通过。
- 团队市场：5插件/20技能；新分发7/7与既有编辑部分发5/5通过。
- 个人市场：2插件/10技能，Grok仍1插件；新分发8/8及既有产品专家grok plugin validate通过。
- 两市场新测试命令已接入既有CI工作流；本轮两个main提交的GitHub CI均已完成且成功，见下表。
- 原生Codex app-server plugin/read：两新插件分别读取两项技能，enabled=true，apps/mcpServers为空。此为只读解析，未安装新插件。
- 官方plugin-creator校验器当前不存在，未声称完整官方插件Schema验证；两市场原有插件约束与Grok清单保持。

## 远端发布回执

| 市场 | main 提交 | CI |
| --- | --- | --- |
| 团队 | [5678d7e](https://github.com/J21NIANYI/flipbelt-plugin-marketplace/commit/5678d7e045b2add218d249a259cb2fb7b1b80961) | [38720009044 success](https://github.com/J21NIANYI/flipbelt-plugin-marketplace/actions/runs/38720009044) |
| 个人 | [6227fda](https://github.com/J21NIANYI/flipbelt-personal-marketplace/commit/6227fda6022e5aea2893392749352fb425cfd620) | [38720016134 success](https://github.com/J21NIANYI/flipbelt-personal-marketplace/actions/runs/38720016134) |

GitHub API独立回读两仓main、完整插件文件集合、全部Git blob字节摘要、市场清单及SOURCE-PROVENANCE；团队10文件与个人11文件均与本地一致。旧插件及个人Grok清单没有变更。提交身份仅通过已验证GitHub身份的命令级参数指定，未更改全局Git配置。

## 用户安装与业务验收

1. 千问运行端已经用户确认：Windows桌面、本机stdio。用户在企业后台上传ZIP，核对标识/版本/两技能与成员范围。上传套件不会自动授予业务权限。
2. 解压ZIP中的connector目录，按其README主动安装锁定依赖，再将run.ps1配置为本机stdio入口；已有同名连接器时复用。无需改为远程MCP。
3. 用户在实际客户端完成16工具发现、本人授权、私有草稿、网页确切版本确认及重读；既有FBC-21/24/25人工UAT保持，不由本轮技术分发关闭。

官方依据：[千问企业专家套件](https://help.aliyun.com/zh/qwenwork/enterprise-ultimate-ai-assets-expert-kits)、[千问企业连接器](https://help.aliyun.com/zh/qwenwork/enterprise-ultimate-ai-assets-connectors)。用户附件关于v1.2.5的 `.qoder-plugin` 安装证据用于本包格式选择，不能替代本插件目标环境验收。
