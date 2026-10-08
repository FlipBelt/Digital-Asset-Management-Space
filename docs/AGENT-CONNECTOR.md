# AI 孵化器与登记器连接器 · 实施与上线清单

## 当前状态

2026-10-08 核实正式站点 https://jtzhzt.flipbeltchina.com：
生产 commit f78407110117610b4d236e6d5cf8229f637ed46b，schema f13c20260928，ready200。
实现基于正式工程 1b11b6a（同一业务代码、追加运维说明），隔离分支 codex/asset-center-agent-connector。
5a6c5f1已推送并创建Draft PR2；测试环境迁移及72张旧表摘要比对通过。生产发布检查发现运行进程连接器路由404，已两次恢复旧应用/静态资源/配置；新增三表为空并保留，schema现为f13d。路由直接挂到应用层的最小兼容修复及真实Uvicorn HTTP检查完成，待按测试、生产顺序复核。真人授权和业务验收尚未执行。

## 一条使用路径

1. 在新 Codex 会话使用登记器或孵化器，明确要求“连接正式资产中心”。
2. start_connection 返回网页与授权码；本人登录资产中心，在 /agent/connect 输入码并批准。
3. complete_connection 将短期令牌写入本机 Windows DPAPI 保管；聊天和配置文件不保存令牌。
4. get_capabilities 返回当前身份、真实类型及能力。查可见成果、保存必要孵化摘要或私有成果草稿。
5. 打开草稿 confirmation_url，在既有成果页预览确切版本、选择共享范围并确认。
6. get_asset 重读 active / pending_review 才报告“已登记，待审核”。它不表示业务批准或已验收。

未请求正式接入时，双 Skill 保持本地模式；旧本地确认不自动转为正式确认。
机器令牌只在 /api/v1/agent 路由生效，不能替代完整网页会话、管理角色或最终确认。

## 实现范围与边界

| 目的 | MCP 工具 | 实际服务 |
| --- | --- | --- |
| 本人授权与撤销 | start_connection / complete_connection / disconnect | 一次性设备码，10 分钟配对，默认24小时授权；网页 /agent/connect 可撤销 |
| 身份与真实字典 | get_capabilities | 服务端实时身份/员工状态/权限检查；无客户端 actor/role 输入 |
| 查重线索与成果续读 | search_assets / get_asset | 当前身份可见的 AI 成果；管理员机器授权也不拥有管理区全量可见性 |
| 草稿创建与更新 | create_asset_draft / update_asset_draft | 统一 Asset，私有默认，复用服务端类型与 AI 开发方式检查 |
| 孵化续接 | get_my_incubations / get_incubation / save_snapshot | 独立本人私有的结构化摘要，不混成 Workflow Asset 或 Audit 内容 |
| 未知结果查询 | operation_status | actor + 操作 + UUID 请求编号、内容摘要；变更携带当前版本 |
| 最终确认 | 本人网页 | 现有 AssetConfirmation 内容摘要与确切版本，不提供机器确认工具 |

当前未开放机器附件和关系写入；capabilities 明确返回 false。
类型来自正式字典，不硬映射不存在的 Prompt、Template、MCP 或 Composite。
列表每次最多50项，定位已有孵化记录时保留 id 并使用 get_incubation；不以空列表证明组织内无重复。
仅存用户授权的必要成果摘要；不上传完整聊天、隐藏推理、整个仓库或秘密。

## 本机接入

已经安装：C:/Users/MSI/.local/bin/flipbelt-agent-connector.exe。
已通过 Codex CLI 添加全局 flipbelt-ai-assets；新会话 /mcp 查看，当前聊天不保证热加载新工具。
服务未上线前不得把本机工具存在说成已连接生产。

Codex 配置依据：[官方 MCP 文档](https://developers.openai.com/codex/mcp)。
复现安装与配置（仓库根目录）：

```powershell
uv tool install ./connector
codex mcp add flipbelt-ai-assets --env FLIPBELT_API_BASE=https://jtzhzt.flipbeltchina.com --env FLIPBELT_CLIENT_NAME=Codex -- "$env:USERPROFILE/.local/bin/flipbelt-agent-connector.exe"
```

Qoder-CN 使用相同程序。在 IDE 的 MCP 配置中新增以下单项并合并保留已有服务器，不覆盖整个配置：

```json
{
  "mcpServers": {
    "flipbelt-ai-assets": {
      "command": "C:/Users/MSI/.local/bin/flipbelt-agent-connector.exe",
      "args": [],
      "env": {
        "FLIPBELT_API_BASE": "https://jtzhzt.flipbeltchina.com",
        "FLIPBELT_CLIENT_NAME": "Qoder-CN"
      }
    }
  }
}
```

[Qoder-CN MCP 说明](https://docs.qoder.cn/user-guide/guide-for-using-mcp)与
[CLI MCP 参考](https://docs.qoder.cn/cli/mcp-reference)说明 stdio 接入方式。
本机仅有 IDE/调度入口，CLI 未安装；没有擅自安装 CLI，也未声称 IDE 已发现新工具。
双 Skill 全局共享目录仍为 C:/Users/MSI/.agents/skills；0.2.0 已同步，0.1.7 本地基线保留。

## 数据与权限变更

增量 schema：f13c20260928 → f13d20261008，仅增加 agent_grants、agent_operations、agent_incubations。
不新增组织身份资源，不批量重分类旧资产，不修改知识平台。
令牌/设备码/用户授权码仅存摘要；孵化表只保留结构化摘要，审计只记录操作者和业务动作。
连接器由 AGENT_CONNECTOR_ENABLED 控制，默认 false；启用须设置可信 AGENT_FRONTEND_URL。
HTTPS、合法员工状态、当前权限、Cookie CSRF、对象可见性与版本都由服务端检查。
进程内限流适合当前少数人员单进程试用；扩大到多 worker/多实例前必须增加统一网关限流。
授权信息有期限，操作回执与孵化摘要保留以支持续接；未实现自动删除业务记录。

## 验证与复现

- PostgreSQL 127.0.0.1:55433 全新独立库，68项目标检查通过，包括既有确认与会话回归。
- 官方 MCP SDK 1.30.0，11项检查通过：stdio 初始化与12工具发现、无凭据断路、未知写入不重试、DPAPI与源绑定。
- 前端 vue-tsc / Vite 生产构建通过；未执行真实用户或真实设备的界面验收。
- 空库升级、当前生产 schema 升级/回滚/再升级通过；所有旧业务表内容摘要保持一致。
- 已含连接器数据的 schema 降级被主动拒绝，避免丢弃孵化记录。
- Starlette 既有 TestClient/httpx 弃用提示不影响通过结果；没有为此改依赖。

隔离验证命令（需已启动既有专用回环测试 PostgreSQL，preflight 仅本地测试用户）：

```powershell
backend/.venv/Scripts/python.exe scripts/rehearse-agent-connector.py
cd connector
uv sync --locked --group dev
uv run pytest -q
```

本轮实际复用了原工程 backend/.venv 解释器；报告位于 .local/agent-connector/REHEARSAL.md。
真实扫码、两客户端发现、人员权限与业务验收均单列，未标记通过。

## 待批准的生产步骤

1. 发布前重新读取 release-meta、服务 WorkingDirectory/端口、当前 alembic revision、系统服务账户与静态目录；若与上述基线不一致，先检查差异，不直接覆盖。
2. 用既有生产备份流程保存数据库、后端与静态文件、当前配置；不导出或回传凭据。先在隔离 /test/ 演练同包与迁移，保留测试/生产身份与数据库边界。
3. 发布包只含必要 backend/app、alembic 与锁文件、构建静态资源和说明；不含 .env、凭据、测试数据库或虚拟环境。后端依赖未新增 MCP SDK，SDK 只在本机适配器。
4. 维护窗口停止生产 API 写入，使用服务器本机既有环境执行 alembic upgrade f13d20261008，再发布匹配后端与静态资源。保持启用开关 false 完成健康与匿名边界复核。
5. 通过既有服务配置方式追加非秘密项 AGENT_CONNECTOR_ENABLED=true、AGENT_FRONTEND_URL=https://jtzhzt.flipbeltchina.com、AGENT_TOKEN_TTL_HOURS=24；不猜配置覆盖顺序，不覆盖已有认证字段。重启后验证 ready、匿名工具401、浏览器会话无法充当机器令牌、机器令牌不能确认。
6. 由本人完成首次配对与一条真实孵化/草稿/网页确认链路。操作前保留 request_id、id、version，发现异常立即撤销连接。

生产确认范围：三个新表、授权页、受限 API、静态资源替换和开启连接器；不授予额外管理角色，不代替用户确认任何资产。

回退：先关闭开关并撤销连接，回退后端与静态文件，保留三个增量表和业务记录。
不直接降级或整库恢复以覆盖用户新记录。确需 schema 降级时先导出并审核新增数据；迁移会拒绝删除有数据的表。
生产部署需要用户明确授权，当前仅完成代码、隔离验证与本机配置。
