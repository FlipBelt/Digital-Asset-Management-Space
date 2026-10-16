"""Independent public byte, discovery and anonymous-auth checks; no OAuth consent."""
import argparse
import base64
import concurrent.futures
import gzip
import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

HOST = "https://jtzhzt.flipbeltchina.com"


def frozen_manifest(package):
    manifest = json.loads((package / "PACKAGE.json").read_bytes())
    raw = (package / "release.json.gz").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    assert digest == manifest["sha256"]
    spec = json.loads(gzip.decompress(raw))
    assert spec["kind"] == "digital-center-remote-mcp"
    assert set(spec["static"]) == {"test", "production"} and spec["backend"]

    def hashes(entries):
        assert entries
        result = {}
        for name, entry in entries.items():
            assert not Path(name).is_absolute() and ".." not in Path(name).parts
            data = base64.b64decode(entry["data"], validate=True)
            result[name] = hashlib.sha256(data).hexdigest()
            assert result[name] == entry["sha256"]
        return result

    static = {label: hashes(entries) for label, entries in spec["static"].items()}
    backend = hashes(spec["backend"])
    for label in ("test", "production"):
        metadata = json.loads(base64.b64decode(
            spec["static"][label]["release-meta.json"]["data"], validate=True
        ))
        assert metadata["commit"] == metadata["backend_commit"] == spec["commit"]
        assert metadata["release_kind"] == spec["kind"] and metadata["environment"] == label
        assert metadata["schema"] == "f13g20261016"
    derived = {"commit": spec["commit"], "kind": spec["kind"], "schema": "f13g20261016",
               "operator_sha256": spec["operator_sha256"], "static": static, "backend": backend}
    assert all(manifest[key] == value for key, value in derived.items())
    assert all(manifest[key] == spec[key] for key in ("source_base", "live_base"))
    assert hashlib.sha256((package / "remote-mcp-release.py").read_bytes()).hexdigest() == (
        spec["operator_sha256"]
    )
    return {**derived, "sha256": digest}


def request(path, method="GET"):
    req = urllib.request.Request(HOST + path, method=method, headers={"Cache-Control": "no-cache"})
    for attempt in range(3):
        try:
            try:
                with urllib.request.urlopen(req, timeout=20) as response:
                    return response.status, response.read(), {
                        key.lower(): value for key, value in response.headers.items()
                    }
            except urllib.error.HTTPError as error:
                return error.code, error.read(), {
                    key.lower(): value for key, value in error.headers.items()
                }
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == 2:
                raise RuntimeError("Public check failed: " + method + " " + path) from None
            time.sleep(attempt + 1)
    raise AssertionError("Unreachable retry state")


def verify(package, manifest, label):
    prefix, mount = ("/test-api", "/test/") if label == "test" else ("", "/")
    commit = manifest["commit"]

    def check_file(item):
        name, expected = item
        assert not Path(name).is_absolute() and ".." not in Path(name).parts
        status, data, _ = request(mount + name)
        assert status == 200 and hashlib.sha256(data).hexdigest() == expected, "Static mismatch: " + name

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(check_file, manifest["static"][label].items()))
    status, raw, _ = request(mount + "release-meta.json")
    metadata = json.loads(raw)
    assert status == 200 and metadata["commit"] == metadata["backend_commit"] == commit
    assert metadata["schema"] == "f13g20261016" and metadata["environment"] == label
    assert metadata["release_kind"] == "digital-center-remote-mcp"
    status, raw, _ = request(prefix + "/api/v1/health/ready")
    assert status == 200 and json.loads(raw)["database"] == "ok"
    resource = HOST + prefix + "/mcp"
    issuer = HOST + prefix + "/mcp-oauth"
    protected_path = "/.well-known/oauth-protected-resource" + prefix + "/mcp"
    status, raw, _ = request(protected_path)
    protected = json.loads(raw)
    assert status == 200 and protected["resource"] == resource
    assert protected["authorization_servers"] == [issuer]
    status, raw, _ = request("/.well-known/oauth-authorization-server" + prefix + "/mcp-oauth")
    authorization = json.loads(raw)
    assert status == 200 and authorization["issuer"] == issuer
    for key, suffix in (("authorization_endpoint", "/authorize"), ("token_endpoint", "/token"),
                        ("registration_endpoint", "/register"), ("revocation_endpoint", "/revoke")):
        assert authorization[key] == issuer + suffix
    assert authorization["code_challenge_methods_supported"] == ["S256"]
    for method in ("GET", "POST", "DELETE"):
        status, _, headers = request(prefix + "/mcp", method)
        assert status == 401
        assert 'resource_metadata="' + HOST + protected_path + '"' in headers["www-authenticate"]
    assert request(prefix + "/api/v1/agent/capabilities")[0] == 401
    status, page, headers = request(mount + "agent/oauth")
    assert status == 200 and b'id="app"' in page
    assert headers["referrer-policy"] == "no-referrer"
    assert "no-store" in headers["cache-control"] and headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in headers["content-security-policy"]
    receipt = {"status": "PASS", "environment": label, "commit": commit,
               "package_sha256": manifest["sha256"], "kind": "digital-center-remote-mcp",
               "operator_sha256": manifest["operator_sha256"],
               "schema": "f13g20261016", "static_files_verified": len(manifest["static"][label]),
               "resource": resource, "issuer": issuer, "public_checks": [
                   "frozen_static_bytes", "ready", "resource_and_issuer", "oauth_metadata",
                   "anonymous_mcp_challenge", "consent_page_headers",
               ], "business_writes_performed": False,
               "human_oauth_or_business_uat_performed": False,
               "completed_at": datetime.now(UTC).isoformat()}
    (package / (label + "-public-PASS.json")).write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--environment", choices=["test", "production", "final"], required=True)
    args = parser.parse_args()
    package = args.package.resolve()
    manifest = frozen_manifest(package)
    labels = ("test", "production") if args.environment == "final" else (args.environment,)
    print(json.dumps([verify(package, manifest, label) for label in labels]), flush=True)


if __name__ == "__main__":
    main()
