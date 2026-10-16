# 登记器、孵化器统一插件分发

## 0.2.0 当前交付（2026-10-16）

登记器、孵化器与资产中心远程连接统一以0.2.0插件分发，Skill版本为0.2.3-pilot。正式远程服务已按测试→正式发布至 `https://jtzhzt.flipbeltchina.com/mcp`，当前应用提交为 `a160657200a93f05050d5c69d31ff7d0f966a448`。用户本人已允许ChatGPT连接，并在ChatGPT Work的FB GPT中完成一次只读 `get_capabilities` 调用；这不替代全部工具与登记闭环验收。部署与验证回执见[远程MCP说明](REMOTE-MCP.md)。

| 目标 | 当前交付与边界 |
| --- | --- |
| 团队市场 flipbelt-team | 插件 `flipbelt-ai-asset-center` 的0.2.0已推送main，提交 [aaa3c4a](https://github.com/J21NIANYI/flipbelt-plugin-marketplace/commit/aaa3c4a27e0388048c927e8f95882d8fc1f61f25)，绑定真实资产App；[CI 38856116286](https://github.com/J21NIANYI/flipbelt-plugin-marketplace/actions/runs/38856116286) success，155个tracked blob路径/模式/Git SHA匹配，15个变更文件远端字节回读一致。FB GPT市场已同步确切revision并重载确认成果助手已导入，真实App为必需依赖。用户反馈App已发布，但独立回读仍为草稿及工作空间权限错误；团队插件在工作空间列表显示禁用/不可用，原因未确定。管理员发布及恢复团队可用性仍待处理。 |
| 个人市场 flipbelt-personal | 插件 `flipbelt-ai-asset-center-personal` 的0.2.0已推送main，提交 [b34d776](https://github.com/J21NIANYI/flipbelt-personal-marketplace/commit/b34d7768ac2d0783d3bf2a5feb0ff864848bc36c)；[CI 38851739980](https://github.com/J21NIANYI/flipbelt-personal-marketplace/actions/runs/38851739980) success，78个远端blob字节回读一致。 |
| 千问办公 | 企业后台已创建并enabled OAuth DCR连接器 `flipbelt-ai-assets`，地址为正式 `/mcp`；已导出下方最终ZIP。用户明确暂不测试千问；本轮不声称ZIP已导入、成员OAuth成功、工具可调用或业务验收通过。 |

真实ChatGPT资产App为 `asdk_app_6ad1a995522c819197dd69e6aca6f71f`，技术插件标识为 `plugin_asdk_app_6ad1a995522c819197dd69e6aca6f71f`。团队包的 `.app.json` 使用前者且 `required: true`；不复用知识库App。App目录版本1.0.0与本项目插件版本0.2.0独立，不能相互替代。本人连接证据来自用户确认与宿主可见调用，不冒充原始服务日志；响应中的 `remote_tool_count=13` 不是13个工具分别执行通过，且响应没有 `role` 或 `connected` 字段。

同步后已进入导入插件详情回读：标题为“飞比特AI成果助手”、目录为FB GPT、版本为0.2.0，两项Skill可见；应用区链接指向上述真实资产App并标记“必需”。证据截图为 `.local/connection-proof/team-plugin-0.2.0-required-app.png`。这确认导入后的插件绑定，不替代App组织发布或其他成员的连接验收。

### 维护源与最终ZIP

正式维护源为 `C:/Users/MSI/Documents/Codex/work/asset-center-remote-mcp`，Git仓库为 [FlipBelt/Digital-Asset-Management-Space](https://github.com/FlipBelt/Digital-Asset-Management-Space)。技能源为本项目 `.agents/skills/` 下的登记器与孵化器，元数据和模板位于 `plugin/`，统一打包入口为 `scripts/package_ai_asset_plugin.py`。D盘旧副本保留原有改动，已不是分发真源；下游市场不直接修改技能。

最终千问ZIP：`C:/Users/MSI/Downloads/flipbelt-ai-asset-center-0.2.0-qwenwork-a160657200a9.zip`，31,213字节。

SHA-256：`441e7dceec26f9e8e25533764bf49eed3c7ddac710f459862b1cca3601cd360a`。

生成目录为 `.local/remote-mcp-final-distribution/a160657200a9/`，来源提交为干净的 `a160657200a93f05050d5c69d31ff7d0f966a448`。ZIP根目录含 `.qoder-plugin/plugin.json` 和 `.mcp.json`，共11文件，未带Windows运行资源、令牌或团队App ID。逐文件回读、CRC与正斜杠条目检查通过；9个技能源/模板文件和6个复制技能文件与已推送个人市场的来源字节一致。个人市场记录的生成提交为 `210b85f`，两次提交之间上述9个源文件内容未变化；不把不同provenance文件或ZIP摘要混称同一产物。

真正的团队App绑定输出位于团队仓库 `.tmp/ai-asset-0.2.0-a160657200a9/team`，已应用到其 `plugins/flipbelt-ai-asset-center`。上述本地最终ZIP生成目录中的 `team` 子目录是无App的直接MCP候选，不能作为团队市场绑定包使用。旧候选和Downloads中的0.1.0历史包保留，验收本轮交付应使用上面的0.2.0文件名及摘要。

早期无App的0.2.0候选ZIP摘要 `5870e236b23c8d84761381696c2065001fa7f5edc5b4ab880c5cc0babd9b3f0a` 仅保留为历史证据，不是本轮最终交付摘要。

### 配置与市场门禁

两个技能共用逐字节一致的 `CONNECTOR.md`。远程MCP提供13种业务工具，由宿主管理OAuth DCR、PKCE S256与本人同意，不暴露本机的 `start_connection`、`complete_connection`、`disconnect`。远程附件只接受内容base64，解码最大1,000,000字节；旧Windows stdio才使用绝对 `file_path`、最大20MB。

- `local-legacy`：保留旧本机兼容方式；不随包自动配置MCP。
- `remote-oauth-candidate`：指定 `--remote-mcp-url` 后，个人和千问包加入 `.mcp.json`，使用 `mcpServers → flipbelt-ai-assets → type=http/url`。该内部profile名称保留，不代表此时服务仍未部署。无App团队直连包只供本地核查，不能写入团队市场。
- `workspace-app-candidate`：同时指定 `--remote-mcp-url` 与真实 `--team-app-id`，团队包仅生成 `.app.json` 和 `manifest.apps`；个人和千问仍为直接远程MCP。指定 `--team-root` 必须有真实App标识。
- `SOURCE-PROVENANCE.json` 保留生成时的connection_profile、提交、dirty状态与逐文件摘要。`workspace_app_binding_verified`、`remote_deployment_verified`、`host_runtime_verified`默认false；独立部署和宿主证据另记，不回写为自动验证成功，也不改写已交付包。

App参数仅接受严格的 `asdk_app_...` 或 `plugin_asdk_app_...`，后者规范化为前者；不接受URL、空白、嵌套前缀或其他ID类别。这是本项目的窄输入边界，打包输入不能代替真实App、服务地址和成员策略回读。脚本不注册App、批准用户授权或推送仓库；下游存在多余文件时停止且不删除，所有目标预检后才写入，并拒绝符号链接及Windows junction/reparse path。

生成到独立目录并回读（在正式工程根目录执行；真实App标识可从上方回执核对）：

```powershell
$env:FLIPBELT_TEAM_APP_ID='asdk_app_6ad1a995522c819197dd69e6aca6f71f'
python -B -X utf8 scripts/package_ai_asset_plugin.py --output-dir work/ai-asset-plugin/0.2.0-app --remote-mcp-url https://jtzhzt.flipbeltchina.com/mcp --team-app-id $env:FLIPBELT_TEAM_APP_ID
python -B -X utf8 scripts/package_ai_asset_plugin.py --output-dir work/ai-asset-plugin/0.2.0-app --remote-mcp-url https://jtzhzt.flipbeltchina.com/mcp --team-app-id $env:FLIPBELT_TEAM_APP_ID --check
```

本轮打包定向回归20/20通过，包括App格式与别名规范化、团队独占App引用、缺URL/错误目标拒绝、无App团队市场零写入，以及CLI三目标生成和逐字节回读；两项Skill quick_validate通过。团队市场22项全仓测试、市场校验、两技能校验与9个源文件/6个技能复制文件核对通过，提交仅含本轮15个路径。个人市场另完成18项分发回归及既有产品专家检查。官方plugin-creator校验器当前不存在，不声称完成官方全Schema验证。

团队市场的local、origin/main、GitHub main与ls-remote均指向上述 `aaa3c4a`，工作区干净。155个tracked blob的Git SHA核验与15个变更文件的完整字节回读分别记录，不将前者描述为全部155文件均已下载比对。

### 后续安装与验收

FB GPT市场同步已完成，重载回读的revision为 `aaa3c4a27e0388048c927e8f95882d8fc1f61f25`，统计为0添加、1更新、4未变、0源删除、0失败，成果助手显示已导入；截图为 `.local/connection-proof/team-market-synced-aaa3c4a.png`。

App Workspace批准与发布尚未获得成功回执：先前Shared弹窗明确要求“此应用必须先获得工作空间管理员的批准，其他用户才能使用”；App设置显示草稿、共享设置加载失败，点击发布后返回“插件不可用，你没有权限访问此工作空间中的插件”。用户随后反馈“App已发布”，但独立刷新及新tab的WORKSPACE范围回读仍为草稿、共享设置失败与插件权限错误，发布尚未在回读中生效；团队插件在工作空间列表还显示禁用/不可用，原因未确定，不归因于代码或用户操作。证据为 `.local/connection-proof/team-app-admin-approval-required.png` 和 `.local/connection-proof/app-workspace-publish-permission.png`。管理员发布及恢复团队可用性仍待处理，不绕过该权限。此前当前账号已完成OAuth和一次只读能力查询的事实保留；其他成员可用性尚未验证。

市场更新、App绑定、组织批准和每位用户的OAuth连接分别记录。其他员工仍需本人登录资产中心并允许确切权限，机器不得代点同意。

千问企业连接器与专家套件分别管理。最终ZIP可供后续导入，后台连接器已enabled；用户已选择暂不测试，因此不继续调整坐席或发起千问运行端测试。后续若恢复测试，应在目标客户端验证工具发现、本人授权及必要业务路径。已有FBC-21/24/25人工UAT保持独立，技术发布、一次能力查询和后台启用均不关闭这些验收项。

官方依据：[OpenAI插件打包](https://developers.openai.com/plugins/build/plugins)、[OpenAI团队插件管理](https://learn.chatgpt.com/docs/enterprise/plugin-management)、[App标识格式](https://developers.openai.com/plugins/deploy/submission-errors)、[千问企业连接器](https://help.aliyun.com/zh/qwenwork/enterprise-ultimate-ai-assets-connectors)、[千问企业专家套件](https://help.aliyun.com/zh/qwenwork/enterprise-ultimate-ai-assets-expert-kits)。2026-10-16已核对的OpenAI团队说明区分App引用与Desktop only的直接MCP配置；千问附件仅用于选择 `.qoder-plugin` 元数据布局，不能替代本插件的目标环境验收。

## 0.1.0 历史分发记录

以下保留2026-10-15的实际发布与安装说明，属于旧本机兼容版的历史证据，不得用于判断0.2.0远程版的当前发布、连接或验收状态；当前状态以上方记录为准。

日期：2026-10-15。跟踪：[FBC-216](https://linear.app/j21nianyi/issue/FBC-216)。插件版本 0.1.0，Skill 版本 0.2.2-pilot。

当时已完成三分发、两个市场 main 推送与远端 CI/文件回读。用户已确认千问目标为允许本机 stdio MCP 的 Windows 桌面端，并明确授权提交推送两个市场仓库。两市场包提供两项 Skill 与独立连接器配置说明；千问 ZIP 另外携带 Windows 本机连接器资源。千问企业后台导入、本人授权和登记业务验收由用户实际操作确认。

### 历史维护与分发

唯一行为源为本项目 `.agents/skills/flipbelt-ai-asset-registrar` 与 `.agents/skills/flipbelt-ai-workflow-incubator`。插件元数据和说明在 `plugin/`，打包入口为 `scripts/package_ai_asset_plugin.py`。下游不直接修改技能。

| 目标 | 插件标识 | 0.1.0当时的内容与证据 |
| --- | --- | --- |
| 团队市场 flipbelt-team | flipbelt-ai-asset-center | 10文件、2技能；已推送市场main，原生Codex解析与远端CI通过 |
| 个人市场 flipbelt-personal | flipbelt-ai-asset-center-personal | 11文件、2技能；已推送市场main，保留最小根manifest，Grok市场仍仅原产品专家；原生解析与远端CI通过 |
| 千问办公 ZIP | flipbelt-ai-asset-center | 19文件、2技能、可选Windows connector资源；.qoder-plugin/plugin.json位于ZIP根，无额外嵌套目录 |

团队下游：`C:/Users/MSI/repos/codex-plugins/distributions/flipbelt-plugin-marketplace`。
个人下游：`C:/Users/MSI/repos/codex-plugins/distributions/flipbelt-personal-marketplace`。
生成目录：`work/ai-asset-plugin/0.1.0/{team,personal,qwenwork}`。
ZIP：`work/ai-asset-plugin/0.1.0/flipbelt-ai-asset-center-0.1.0-qwenwork.zip`。

0.1.0历史ZIP SHA-256：`e182bc765807c3a74f356fa51caa2d846c6e7492ed98ddda9c14dbf70b71e733`，72735字节。逐文件比对、CRC、正斜杠条目和可重复生成通过；下载副本为 `C:/Users/MSI/Downloads/flipbelt-ai-asset-center-0.1.0-qwenwork.zip`。当时将六个技能源文件统一为LF，避免Git规范化换行破坏来源哈希；该摘要仅用于核对0.1.0历史包，当前0.2.0交付见上方记录。

项目源工作区有原有未提交改动，本次未提交源文件。来源清单明确记录 `canonical_worktree_dirty=true`、观察到的Git基线及逐文件/source-tree摘要；Git基线不能单独代表包内内容。三种包的六个技能文件逐字节一致。

### 旧版连接器边界

连接器源码固定来自正式工程 `fa56c38f9f9b37d78ba65971f1f9b810ce8d2ddf`，仅复制四个Python模块、pyproject.toml和uv.lock；原始字节与Git换行规范化摘要均在 `plugin/connector/SOURCE-PROVENANCE.json`。该0.1.0分发当时没有连接生产确认线上版本。

它是 Windows Python 3.11–3.13 stdio MCP → HTTPS REST API，凭据由 Windows DPAPI 加密保存；不是远程 HTTP MCP。默认业务站点不可当作MCP入口。没有真实资产App ID或远程MCP时不编造、不复用Knowledge App，也不添加自动MCP配置。

千问包携带手动安装说明和 `run.ps1`，仅在企业宿主允许Windows本机stdio时可按说明配置。安装依赖是用户主动步骤；启动器不安装、不下载、不改执行策略或全局配置。云端/Linux执行端在该旧版中没有远程MCP；0.2.0实现及发布见上方当前记录。

两Codex包不含连接器源码或 `.mcp.json` / `.app.json`；可以复用已配置的本机连接器，或从同次千问ZIP提取connector目录。套件存在不代表工具已可调用。实际16工具和字段能力须同时由客户端工具目录与get_capabilities确认。

本人授权、私有草稿、request_id幂等和网页确切版本确认保持；缺连接器时保留本地模式。组织保存、待审核与真实业务验收分开报告。

### 历史生成命令（0.1.0）

以下命令仅保留当时0.1.0生成记录，不应用于重新生成当前版本。脚本只生成/同步已知文件，发现下游多余文件时停止且不删除；检查全部目标后才写入，拒绝符号链接和Windows junction/reparse path。

```powershell
python -B -X utf8 scripts/package_ai_asset_plugin.py --output-dir work/ai-asset-plugin/0.1.0 --team-root C:/Users/MSI/repos/codex-plugins/distributions/flipbelt-plugin-marketplace --personal-root C:/Users/MSI/repos/codex-plugins/distributions/flipbelt-personal-marketplace
python -B -X utf8 scripts/package_ai_asset_plugin.py --output-dir work/ai-asset-plugin/0.1.0 --team-root C:/Users/MSI/repos/codex-plugins/distributions/flipbelt-plugin-marketplace --personal-root C:/Users/MSI/repos/codex-plugins/distributions/flipbelt-personal-marketplace --check
python -B -X utf8 -m unittest discover -s tests -p test_ai_asset_plugin_packaging.py -v
```

### 0.1.0 实际验证

- 打包回归11/11：三目标来源、逐文件内容、可重复ZIP、文件枚举顺序变化、CRLF源拒绝、未知下游文件保留、全部目标预检、链接完整性、秘密/本机路径拒绝及真实Windows junction负向回归。独立审查发现的先resolve后检查问题已修复并复核关闭；两仓暂存区原始字节已独立核对来源哈希。
- 连接器包隔离pytest 6/6：上游摘要/锁文件、16工具、真实stdio初始化、无凭据时在HTTP前停止，以及缺uv/环境/依赖的失败路径。使用已有隔离测试解释器，未安装新依赖；测试屏蔽HTTPX和非回环网络，仅允许Windows事件循环内部回环。
- Skill官方quick_validate：两项均通过。
- 团队市场：5插件/20技能；新分发7/7与既有编辑部分发5/5通过。
- 个人市场：2插件/10技能，Grok仍1插件；新分发8/8及既有产品专家grok plugin validate通过。
- 两市场新测试命令已接入既有CI工作流；本轮两个main提交的GitHub CI均已完成且成功，见下表。
- 原生Codex app-server plugin/read：两新插件分别读取两项技能，enabled=true，apps/mcpServers为空。此为只读解析，未安装新插件。
- 官方plugin-creator校验器当前不存在，未声称完整官方插件Schema验证；两市场原有插件约束与Grok清单保持。

### 0.1.0 远端发布回执

| 市场 | main 提交 | CI |
| --- | --- | --- |
| 团队 | [5678d7e](https://github.com/J21NIANYI/flipbelt-plugin-marketplace/commit/5678d7e045b2add218d249a259cb2fb7b1b80961) | [38720009044 success](https://github.com/J21NIANYI/flipbelt-plugin-marketplace/actions/runs/38720009044) |
| 个人 | [6227fda](https://github.com/J21NIANYI/flipbelt-personal-marketplace/commit/6227fda6022e5aea2893392749352fb425cfd620) | [38720016134 success](https://github.com/J21NIANYI/flipbelt-personal-marketplace/actions/runs/38720016134) |

GitHub API独立回读两仓main、完整插件文件集合、全部Git blob字节摘要、市场清单及SOURCE-PROVENANCE；团队10文件与个人11文件均与本地一致。旧插件及个人Grok清单没有变更。提交身份仅通过已验证GitHub身份的命令级参数指定，未更改全局Git配置。

### 0.1.0 历史安装步骤

1. 千问运行端已经用户确认：Windows桌面、本机stdio。用户在企业后台上传ZIP，核对标识/版本/两技能与成员范围。上传套件不会自动授予业务权限。
2. 解压ZIP中的connector目录，按其README主动安装锁定依赖，再将run.ps1配置为本机stdio入口；已有同名连接器时复用。无需改为远程MCP。
3. 用户在实际客户端完成16工具发现、本人授权、私有草稿、网页确切版本确认及重读；既有FBC-21/24/25人工UAT保持，不由本轮技术分发关闭。

官方依据：[千问企业专家套件](https://help.aliyun.com/zh/qwenwork/enterprise-ultimate-ai-assets-expert-kits)、[千问企业连接器](https://help.aliyun.com/zh/qwenwork/enterprise-ultimate-ai-assets-connectors)。用户附件关于v1.2.5的 `.qoder-plugin` 安装证据用于本包格式选择，不能替代本插件目标环境验收。
