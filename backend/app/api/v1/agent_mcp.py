"""Stateless MCP JSON responses over HTTPS; business writes reuse the agent boundary."""

import asyncio
import base64
import binascii
import json
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import Field, ValidationError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.v1 import agent_connector as business
from app.api.v1.asset_space import DraftInput
from app.core.config import get_settings
from app.core.mcp_oauth import enabled, issuer_url, mcp_access, resource_metadata_url, resource_url
from app.db.session import get_db
from app.schemas.agent_connector import (
    AttachmentInput,
    DetailsInput,
    DraftUpdate,
    IncubationInput,
    StrictInput,
)

router = APIRouter(tags=["agent-mcp"])
MAX_BODY = 1_500_000
PROTOCOLS = {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}
DEFAULT_PROTOCOL = "2025-06-18"


class Empty(StrictInput):
    pass


class Search(StrictInput):
    query: str = Field(default="", max_length=200)


class People(StrictInput):
    query: str = Field(min_length=1, max_length=100)


class AssetIdentity(StrictInput):
    asset_id: UUID


class IncubationIdentity(StrictInput):
    incubation_id: UUID


class CreateDraft(StrictInput):
    request_id: UUID
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    asset_type_id: UUID
    development_method: Literal["vibe_coding", "mixed"] | None = None


class UpdateDraft(DraftUpdate):
    asset_id: UUID


class SaveDetails(DetailsInput):
    asset_id: UUID


class Upload(AttachmentInput):
    asset_id: UUID
    content_base64: str = Field(min_length=1, max_length=1_333_336)


class Operation(StrictInput):
    operation: Literal[
        "draft.create", "draft.update", "incubation.save", "details.save", "attachment.upload"
    ]
    request_id: UUID


# name -> (strict argument model, required scope, read-only, description)
TOOLS = {
    "get_capabilities": (Empty, "asset:read", True, "读取本人身份、真实成果类型和服务能力。"),
    "search_assets": (Search, "asset:read", True, "查找当前本人可见的 AI 成果。"),
    "get_asset": (AssetIdentity, "asset:read", True, "读取成果当前版本与本人网页确认入口。"),
    "create_asset_draft": (CreateDraft, "asset:draft", False, "按真实类型创建本人私有草稿。"),
    "update_asset_draft": (UpdateDraft, "asset:draft", False, "按版本与 request_id 修改本人草稿。"),
    "get_my_incubations": (Empty, "incubation:read", True, "读取本人私有孵化记录列表。"),
    "get_incubation": (IncubationIdentity, "incubation:read", True, "读取本人孵化记录。"),
    "save_snapshot": (IncubationInput, "incubation:write", False, "保存必要结构化孵化摘要。"),
    "operation_status": (Operation, None, True, "以原 request_id 查询本人变更回执。"),
    "get_asset_details": (AssetIdentity, "asset:read", True, "读取本人成果的真实字段及资料。"),
    "save_asset_details": (SaveDetails, "asset:draft", False, "保存本人成果资料，旧确认随版本失效。"),
    "search_people": (People, "asset:read", True, "按姓名查找本人公司内的在职候选人。"),
    "upload_asset_attachment": (
        Upload, "asset:draft", False,
        "上传用户选定附件的 base64 内容，解码最大1MB；不接受服务器或本机文件路径。",
    ),
}


def required_scope(name: str, arguments: dict) -> str:
    if name == "operation_status":
        return "incubation:read" if arguments.get("operation") == "incubation.save" else "asset:read"
    return TOOLS[name][1]


def descriptions(granted_scopes: set[str]):
    items = []
    for name, (model, scope, read_only, description) in TOOLS.items():
        if scope and scope not in granted_scopes:
            continue
        if scope is None and not granted_scopes.intersection({"asset:read", "incubation:read"}):
            continue
        scopes = [scope] if scope else ["asset:read", "incubation:read"]
        items.append({
            "name": name,
            "description": description,
            "inputSchema": model.model_json_schema(),
            "annotations": {
                "readOnlyHint": read_only, "destructiveHint": False,
                "idempotentHint": True, "openWorldHint": False,
            },
            "securitySchemes": [{"type": "oauth2", "scopes": scopes}],
        })
    return items


def dispatch(name: str, args, db: Session, access):
    if name == "get_capabilities":
        value = business.capabilities(Response(), db, access)
        return {
            **value, "protocol": "flipbelt-agent-mcp-v1", "transport": "streamable_http",
            "authentication": "oauth2", "issuer": issuer_url(), "resource": resource_url(),
            "remote_tool_count": len(TOOLS), "attachment_max_bytes": 1_000_000,
            "attachment_input": "content_base64", "confirmation": "web_only",
        }
    if name == "search_assets":
        return business.search_assets(args.query, db, access)
    if name == "get_asset":
        return business.get_asset(args.asset_id, db, access)
    if name == "create_asset_draft":
        payload = DraftInput(**args.model_dump(), source_type="connector", source_agent="remote-mcp")
        return business.create_asset_draft(payload, db, access)
    if name == "update_asset_draft":
        payload = DraftUpdate.model_validate(args.model_dump(exclude={"asset_id"}))
        return business.update_asset_draft(args.asset_id, payload, db, access)
    if name == "get_my_incubations":
        return business.my_incubations(db, access)
    if name == "get_incubation":
        return business.get_incubation(args.incubation_id, db, access)
    if name == "save_snapshot":
        return business.save_incubation(args, db, access)
    if name == "operation_status":
        return business.operation_status(args.operation, args.request_id, db, access)
    if name == "get_asset_details":
        return business.read_details(args.asset_id, db, access)
    if name == "save_asset_details":
        payload = DetailsInput.model_validate(args.model_dump(exclude={"asset_id"}, exclude_unset=True))
        return business.write_details(args.asset_id, payload, db, access)
    if name == "search_people":
        return business.search_people(args.query, db, access)
    if name == "upload_asset_attachment":
        try:
            content = base64.b64decode(args.content_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise HTTPException(422, "附件编码无效") from exc
        if len(content) > 1_000_000:
            raise HTTPException(413, "远程附件最大1MB")
        payload = AttachmentInput.model_validate(args.model_dump(exclude={"asset_id"}))
        return business.upload_outcome(args.asset_id, payload, db, access)
    raise HTTPException(404, "未知工具")


def response(value, status=200, headers=None):
    return JSONResponse(jsonable_encoder(value), status_code=status, headers={
        "Cache-Control": "no-store", "Pragma": "no-cache", "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff", **(headers or {}),
    })


def rpc_error(identity, code, message, status=200):
    return response({"jsonrpc": "2.0", "id": identity, "error": {"code": code, "message": message}}, status)


def auth_error(exc: HTTPException, scopes=None):
    metadata = resource_metadata_url()
    challenge = f'Bearer resource_metadata="{metadata}"'
    if exc.status_code == 403 and scopes:
        challenge += f', error="insufficient_scope", scope="{" ".join(sorted(scopes))}"'
    return response({"error": "invalid_token" if exc.status_code == 401 else "access_denied"},
                    exc.status_code, {"WWW-Authenticate": challenge})


def validate_origin(request: Request):
    origin = request.headers.get("origin")
    if not origin:
        return
    resource = urlsplit(resource_url())
    allowed = {f"{resource.scheme}://{resource.netloc}", *get_settings().agent_mcp_allowed_origins}
    if origin not in allowed:
        raise HTTPException(403, "不允许的来源")


@router.api_route("/mcp", methods=["GET", "DELETE"], include_in_schema=False)
def unsupported_transport(request: Request, db: Session = Depends(get_db)):
    enabled()
    validate_origin(request)
    try:
        mcp_access(request, db, set())
    except HTTPException as exc:
        return auth_error(exc)
    return response({"error": "stateless_post_only"}, 405, {"Allow": "POST"})


@router.post("/mcp", include_in_schema=False)
async def mcp(request: Request, db: Session = Depends(get_db)):
    enabled()
    validate_origin(request)
    headers = request.headers.getlist("authorization")
    if len(headers) != 1 or not headers[0].startswith("Bearer mcp_"):
        return auth_error(HTTPException(401))
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        return response({"error": "application_json_required"}, 415)
    if any(value not in PROTOCOLS for value in request.headers.getlist("mcp-protocol-version")):
        return response({"error": "unsupported_protocol_version"}, 400)
    body = bytearray()
    try:
        async with asyncio.timeout(10):
            async for chunk in request.stream():
                if len(body) + len(chunk) > MAX_BODY:
                    return response({"error": "request_too_large"}, 413)
                body.extend(chunk)
    except TimeoutError:
        return response({"error": "request_timeout"}, 408)
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeError, RecursionError):
        return rpc_error(None, -32700, "无效JSON", 400)
    if (not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0"
            or not isinstance(payload.get("method"), str)
            or set(payload) - {"jsonrpc", "id", "method", "params"}):
        return rpc_error(None, -32600, "无效请求", 400)
    identity, method, params = payload.get("id"), payload["method"], payload.get("params", {})
    if identity is not None and (isinstance(identity, bool) or not isinstance(identity, (str, int))):
        return rpc_error(None, -32600, "无效请求编号", 400)
    if not isinstance(params, dict):
        return rpc_error(identity, -32602, "参数必须为对象")
    try:
        access = await run_in_threadpool(mcp_access, request, db, set())
    except HTTPException as exc:
        return auth_error(exc)
    if "id" not in payload:
        return Response(status_code=202, headers={"Cache-Control": "no-store"})
    if method == "initialize":
        requested = params.get("protocolVersion")
        if not isinstance(requested, str):
            return rpc_error(identity, -32602, "缺少协议版本")
        version = requested if requested in PROTOCOLS else DEFAULT_PROTOCOL
        result = {
            "protocolVersion": version, "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "FlipBelt AI Asset Center", "version": "0.2.0"},
            "instructions": "先核实本人能力；仅保存授权摘要。变更使用request_id，最终登记须本人网页确切版本确认。",
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        if params.get("cursor"):
            return rpc_error(identity, -32602, "不支持该游标")
        result = {"tools": descriptions(set(request.state.mcp_scopes))}
    elif method == "tools/call":
        name, arguments = params.get("name"), params.get("arguments", {})
        if not isinstance(name, str) or name not in TOOLS:
            return rpc_error(identity, -32602, "未知工具")
        if not isinstance(arguments, dict) or set(params) - {"name", "arguments", "_meta"}:
            return rpc_error(identity, -32602, "无效工具参数")
        try:
            args = TOOLS[name][0].model_validate(arguments)
        except ValidationError:
            return rpc_error(identity, -32602, "字段、类型或长度不符合工具要求")
        scopes = {required_scope(name, arguments)}
        try:
            access = await run_in_threadpool(mcp_access, request, db, scopes)
        except HTTPException as exc:
            return auth_error(exc, scopes)
        try:
            value = jsonable_encoder(await run_in_threadpool(dispatch, name, args, db, access))
            if name == "get_capabilities":
                value["scopes"] = sorted(request.state.mcp_scopes)
            result = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}],
                      "structuredContent": value, "isError": False}
        except HTTPException as exc:
            db.rollback()
            messages = {403: "当前身份没有权限", 404: "记录不存在或不在本人可见范围",
                        409: "请求编号或版本冲突，请重读并用原request_id查回执",
                        413: "远程附件最大1MB", 422: "字段、类型或附件不符合服务要求"}
            error = {"status": exc.status_code, "error": messages.get(exc.status_code, "服务暂不可用")}
            result = {"content": [{"type": "text", "text": json.dumps(error, ensure_ascii=False)}],
                      "structuredContent": error, "isError": True}
        except Exception:
            db.rollback()
            error = {"status": 503, "error": "处理结果未知，请使用原request_id查询回执"}
            result = {"content": [{"type": "text", "text": json.dumps(error, ensure_ascii=False)}],
                      "structuredContent": error, "isError": True}
    else:
        return rpc_error(identity, -32601, "不支持的方法")
    return response({"jsonrpc": "2.0", "id": identity, "result": result})
