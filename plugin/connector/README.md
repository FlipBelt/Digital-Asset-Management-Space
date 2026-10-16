# 可选 Windows 本机连接器

本目录是插件随附的 Windows stdio MCP 运行资源，保留正式工程的 16 个工具。它通过受限 HTTPS API 连接资产中心，不能作为远程 HTTP MCP 服务使用，也没有证明千问办公企业云端能执行此程序。千问宿主是否允许本机 stdio、能否访问所选附件，须由实际客户端单独核验。

## 主动安装

需要 Windows、已安装的 Python 3.11–3.13 和 `uv`。安装插件或启动 `run.ps1` 不会替你安装这些前置软件、下载依赖或修改全局 MCP 配置。

在解压后的本目录打开 PowerShell，由本人明确执行一次依赖安装。该命令会从锁定的软件源安装本目录 `.venv`；不要把安装后的 `.venv`、缓存或个人凭据重新打包分发。

```powershell
$env:UV_PYTHON_DOWNLOADS = 'never'
uv sync --frozen --no-dev --project .
```

如果系统策略禁止脚本执行，请按企业已批准的方式运行脚本；本包不修改执行策略。

## 启动

仅在宿主明确支持 **Windows 本机 stdio** 时，将本目录 `run.ps1` 配为本机进程入口；具体配置由宿主说明决定。下列命令也可在本目录手动启动，程序将等待 MCP stdio 输入。

```powershell
$env:FLIPBELT_CLIENT_NAME = 'QwenWork'
powershell.exe -NoLogo -NoProfile -NonInteractive -File .\run.ps1
```

启动器先检查 `uv`、本目录 Python 环境、依赖和连接器入口，再执行：

```powershell
uv run --frozen --no-sync --project . flipbelt-agent-connector
```

实际脚本以自身目录的绝对路径指定 `--project`，不依赖宿主当前目录，并禁用 uv 联网与 Python 下载。缺少依赖时明确报错退出，需本人返回安装步骤处理。它不会自动安装、写全局配置或复制凭据。`FLIPBELT_CLIENT_NAME` 未设置时默认为 `QwenWork`，已有值会保留。

## 授权与能力

默认 API 地址仍为正式工程原值 `https://jtzhzt.flipbeltchina.com`。本目录的安装与启动不等于已经联网授权；只有用户明确要求连接正式中心后，才能调用工具发起授权。先调用 `get_capabilities`；未连接时使用 `start_connection`，由本人打开返回的 `verification_uri` 输入授权码并批准，至少五秒后再调用 `complete_connection`。

令牌由原连接器按当前 Windows 用户通过 DPAPI 加密保存，不写入插件、聊天或 MCP 配置。不得复制任何人的凭据文件给其他员工或服务器。组织登记须由本人打开 `confirmation_url` 核对确切版本并确认；Agent 没有替人确认或审核的工具。

工具包括连接/撤销、可见成果检索、私有草稿、私有孵化摘要、写入回执查询，以及补充资料、人员候选检索和授权附件上传。实际服务能力须以 `get_capabilities` 回读为准；附件上传只能读取此 MCP 运行端可访问且用户明确选定的文件。

## 来源与验证边界

`SOURCE-PROVENANCE.json` 记录正式工程仓库、固定提交、原文件路径及逐文件 SHA-256；六个上游源文件按原字节复制。`run.ps1`、本说明和来源清单是分发适配资源。没有包含测试虚拟环境、账号、令牌、数据库或服务器配置。

离线工具发现检查证明包内代码能完成 stdio 初始化并列出 16 个工具，且无凭据时在发 HTTP 前停止。它不等于千问实际发现、本人授权、业务登记、企业云端执行或人工验收已通过。
