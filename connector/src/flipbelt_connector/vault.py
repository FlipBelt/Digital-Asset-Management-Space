"""Windows DPAPI storage; secrets never appear in MCP results or config files."""

import ctypes
import hashlib
import json
import os
from ctypes import wintypes
from pathlib import Path
from uuid import uuid4


class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_byte))]


def crypt(data: bytes, entropy: bytes, *, decrypt=False) -> bytes:
    if os.name != "nt":
        raise RuntimeError("本版凭据保管仅支持 Windows DPAPI")
    buffers = []

    def blob(value):
        buf = ctypes.create_string_buffer(value)
        buffers.append(buf)
        return Blob(len(value), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))

    source, extra, target = blob(data), blob(entropy), Blob()
    crypto = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    fn = crypto.CryptUnprotectData if decrypt else crypto.CryptProtectData
    fn.argtypes = [
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(Blob),
    ]
    fn.restype = wintypes.BOOL
    # CRYPTPROTECT_UI_FORBIDDEN, bound to the current Windows user, not LocalMachine.
    if not fn(
        ctypes.byref(source),
        None,
        ctypes.byref(extra),
        None,
        None,
        1,
        ctypes.byref(target),
    ):
        raise RuntimeError("Windows 凭据保管失败")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(target.data)


class Vault:
    def __init__(self, base: str):
        self.entropy = base.encode()
        self.path = (
            Path(os.environ["LOCALAPPDATA"])
            / "FlipBelt"
            / "agent-connector"
            / (hashlib.sha256(self.entropy).hexdigest() + ".bin")
        )

    def load(self):
        if not self.path.exists():
            return None
        return json.loads(crypt(self.path.read_bytes(), self.entropy, decrypt=True))

    def save(self, token: str):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        encrypted = crypt(json.dumps({"token": token}).encode(), self.entropy)
        temporary = self.path.with_suffix("." + uuid4().hex + ".tmp")
        temporary.write_bytes(encrypted)
        temporary.replace(self.path)

    def clear(self):
        self.path.unlink(missing_ok=True)
