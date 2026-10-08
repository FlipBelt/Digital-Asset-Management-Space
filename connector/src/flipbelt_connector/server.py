"""Shared Codex/Qoder-CN stdio MCP entry point."""

import os
from uuid import UUID

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from flipbelt_connector.client import Connector, ConnectorError
from flipbelt_connector.vault import Vault

BASE = os.environ.get("FLIPBELT_API_BASE", "https://jtzhzt.flipbeltchina.com").rstrip(
    "/"
)
CLIENT_NAME = os.environ.get("FLIPBELT_CLIENT_NAME", "Codex")
connector = Connector(BASE, Vault(BASE))
server = FastMCP(
    "FlipBelt AI Asset Center",
    instructions=(
        "先 get_capabilities 核实身份与真实类型。未连接时 start_connection，用户本人在 verification_uri "
        "输入授权码；不得代替用户批准。至少五秒后 complete_connection。只保存用户授权的必要结构化摘要，"
        "不上传完整聊天、隐藏推理、秘密或整个仓库。写入前保留 request_id；网络结果未知时用原编号查 "
        "operation_status。草稿始终私有，最终登记由本人打开 confirmation_url 在网页预览确认；"
        "active/pending_review 不表示业务批准。不得读取或输出本地凭据。"
    ),
)
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
WRITE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
)


def safe(method, path, payload=None):
    try:
        return connector.call(method, path, payload)
    except ConnectorError as exc:
        raise ValueError(str(exc)) from None


@server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False))
def start_connection() -> dict:
    """发起本人授权，返回网址和用户授权码。不得替用户操作授权页面。"""
    return connector.start(CLIENT_NAME)


@server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False))
def complete_connection() -> dict:
    """本人网页授权后查询连接结果；两次查询至少间隔五秒，不返回令牌。"""
    return connector.finish()


@server.tool(annotations=READ)
def get_capabilities() -> dict:
    """返回服务端验证的当前身份、真实类型字典与支持边界。"""
    return safe("GET", "/capabilities")


@server.tool(annotations=READ)
def search_assets(query: str = "") -> dict:
    """在当前身份可见的 AI 成果内查找；无结果不表示组织内绝无重复。"""
    from urllib.parse import urlencode

    return safe("GET", "/assets?" + urlencode({"q": query}))


@server.tool(annotations=READ)
def get_asset(asset_id: UUID) -> dict:
    """读取可见成果的当前版本、状态与本人网页确认链接。"""
    return safe("GET", f"/assets/{asset_id}")


@server.tool(annotations=WRITE)
def create_asset_draft(
    request_id: UUID,
    name: str,
    description: str,
    asset_type_id: UUID,
    development_method: str | None = None,
) -> dict:
    """用真实类型创建私有成果草稿。request_id 由调用方保存，同一内容重试使用原编号。"""
    return safe(
        "POST",
        "/drafts",
        {
            "request_id": str(request_id),
            "name": name,
            "description": description,
            "asset_type_id": str(asset_type_id),
            "development_method": development_method,
            "source_type": "connector",
            "source_system": "flipbelt-agent-connector",
            "source_agent": CLIENT_NAME,
        },
    )


@server.tool(annotations=WRITE)
def update_asset_draft(
    asset_id: UUID, request_id: UUID, version: int, name: str, description: str
) -> dict:
    """只改本人草稿名称与简介；提交读取到的当前版本，改动后需重新网页预览确认。"""
    return safe(
        "PATCH",
        f"/drafts/{asset_id}",
        {
            "request_id": str(request_id),
            "version": version,
            "name": name,
            "description": description,
        },
    )


@server.tool(annotations=READ)
def get_my_incubations() -> dict:
    """读取本人最近的私有孵化摘要，以便跨会话续接。"""
    return safe("GET", "/incubations")


@server.tool(annotations=READ)
def get_incubation(incubation_id: UUID) -> dict:
    """读取本人指定孵化记录的当前版本。"""
    return safe("GET", f"/incubations/{incubation_id}")


@server.tool(annotations=WRITE)
def save_snapshot(
    request_id: UUID,
    title: str,
    stage: str,
    workflow_summary: str = "",
    opportunity_summary: str = "",
    blueprint_summary: str = "",
    next_step: str = "",
    incubation_id: UUID | None = None,
    version: int = 0,
    asset_id: UUID | None = None,
) -> dict:
    """保存经用户授权的必要结构化孵化摘要；新记录 version=0，续存须带 id 与当前版本。
    stage: discovering/opportunity/blueprint/testing/paused/ready。不上传聊天全文或隐藏推理。
    """
    return safe(
        "POST",
        "/incubations",
        {
            "request_id": str(request_id),
            "id": str(incubation_id) if incubation_id else None,
            "version": version,
            "title": title,
            "stage": stage,
            "workflow_summary": workflow_summary,
            "opportunity_summary": opportunity_summary,
            "blueprint_summary": blueprint_summary,
            "next_step": next_step,
            "asset_id": str(asset_id) if asset_id else None,
        },
    )


@server.tool(annotations=READ)
def operation_status(operation: str, request_id: UUID) -> dict:
    """查询原编号写入结果。operation: draft.create / draft.update / incubation.save。"""
    if operation not in {"draft.create", "draft.update", "incubation.save"}:
        raise ValueError("不支持的操作")
    return safe("GET", f"/operations/{operation}/{request_id}")


@server.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=True
    )
)
def disconnect() -> dict:
    """撤销当前机器授权并清除本机加密凭据；也可在网页撤销。"""
    result = safe("POST", "/disconnect")
    connector.vault.clear()
    return result


def main():
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
