"""Bounded HTTPS client. Transport errors never trigger a second write."""

from urllib.parse import urlsplit

import httpx


class ConnectorError(Exception):
    pass


class Connector:
    def __init__(self, base, vault, transport=None):
        parsed = urlsplit(base)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or "%" in parsed.path
            or ".." in parsed.path
            or "\\" in base
            or any(ord(c) < 33 for c in base)
        ):
            raise ValueError("连接器地址必须是可信 HTTPS 地址")
        self.base, self.vault, self.pending = base.rstrip("/"), vault, None
        self.http = httpx.Client(
            timeout=15, follow_redirects=False, trust_env=False, transport=transport
        )

    def call(self, method, path, payload=None, *, public=False):
        headers = {}
        if not public:
            saved = self.vault.load()
            if not saved:
                raise ConnectorError(
                    "尚未连接，请先 start_connection，再由本人在网页授权"
                )
            headers["Authorization"] = "Bearer " + saved["token"]
        try:
            response = self.http.request(
                method,
                self.base + "/api/v1/agent" + path,
                json=payload,
                headers=headers,
            )
        except httpx.HTTPError:
            raise ConnectorError(
                "网络结果未知；写入请用原 request_id 查询 operation_status，勿换编号重试"
            ) from None
        if response.status_code == 401:
            self.vault.clear()
        if not response.is_success:
            # Never echo arbitrary upstream messages, HTML, credentials or request bodies.
            messages = {
                400: "授权失效或已领取，请重新连接",
                401: "授权失效，请重新连接",
                403: "当前身份没有权限",
                404: "记录不存在或连接器尚未启用",
                409: "请求编号或版本冲突，请先读取当前记录并用原编号查结果",
                422: "输入不符合服务端要求，请检查字段、类型和开发方式",
                429: "请求过快，请稍后重试",
            }
            raise ConnectorError(
                messages.get(response.status_code, "服务暂不可用，请保留原请求编号")
            ) from None
        return response.json()

    def start(self, client_name):
        if self.pending:
            raise ConnectorError("已有待授权请求，请完成或重启连接器后重试")
        value = self.call(
            "POST", "/device/start", {"client_name": client_name}, public=True
        )
        self.pending = value["device_code"]
        return {
            k: value[k]
            for k in ("user_code", "verification_uri", "expires_in", "interval")
        }

    def finish(self):
        if not self.pending:
            raise ConnectorError("没有待授权请求，请先 start_connection")
        result = self.call(
            "POST", "/device/poll", {"device_code": self.pending}, public=True
        )
        if result.get("status") == "authorized":
            self.vault.save(result["access_token"])
            self.pending = None
            return {
                "status": "connected",
                "expires_at": result["expires_at"],
                "scopes": result["scopes"],
            }
        return {"status": "pending", "next": "请由本人完成网页授权，至少五秒后重试"}
