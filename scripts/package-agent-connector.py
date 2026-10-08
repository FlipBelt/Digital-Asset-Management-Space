"""Build a secret-free release from tracked files and the verified static build."""

import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "1b11b6aef4594cafe86aa2100c226837a010d6ec"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main():
    if git("status", "--porcelain"):
        raise RuntimeError("Commit the reviewed implementation before packaging")
    commit = git("rev-parse", "HEAD")
    assert git("merge-base", commit, BASE) == BASE
    tracked = git("ls-files").splitlines()
    exact = {
        "backend/pyproject.toml",
        "backend/uv.lock",
        "backend/alembic.ini",
        "docs/AGENT-CONNECTOR.md",
    }
    entries = []
    for name in tracked:
        if name in exact or name.startswith(("backend/app/", "backend/alembic/")):
            assert ".env" not in name and "__pycache__" not in name
            entries.append((name, ROOT / name))
        elif name.startswith("connector/") and not name.startswith("connector/tests/"):
            entries.append((name, ROOT / name))
    static = ROOT / "frontend/dist"
    assert (static / "index.html").is_file(), "Production static build required"
    for path in sorted(static.rglob("*")):
        if path.is_file() and path.name != "release-meta.json":
            assert (
                path.resolve().is_relative_to(static.resolve())
                and not path.is_symlink()
            )
            entries.append(("frontend/" + path.relative_to(static).as_posix(), path))
    for name, path in entries:
        assert path.is_file() and not path.is_symlink(), name
    out = ROOT / ".deploy-artifacts" / "agent-connector" / commit[:12]
    out.mkdir(parents=True, exist_ok=False)
    archive = out / ("release-" + commit[:12] + ".tar.gz")
    records = [
        f"| {name} | {path.stat().st_size} | {hashlib.sha256(path.read_bytes()).hexdigest()} |"
        for name, path in entries
    ]
    manifest = (
        "# Agent connector candidate release\n\n"
        f"- Commit: {commit}\n- Parent production lineage: {BASE}\n"
        "- Required production schema: f13c20260928 -> f13d20261008\n"
        "- Status: candidate; not pushed or deployed\n"
        "- No .env, credentials, DB dumps, test data or virtual environments included\n"
        "- See docs/AGENT-CONNECTOR.md for activation and rollback boundaries\n\n"
        "| Path | Bytes | SHA-256 |\n| --- | --- | --- |\n" + "\n".join(records) + "\n"
    ).encode()
    metadata = json.dumps(
        {
            "commit": commit,
            "environment": "candidate",
            "release": commit[:12] + "-agent-connector",
            "schema": "f13d20261008",
        },
        separators=(",", ":"),
    ).encode()
    with tarfile.open(archive, "w:gz") as package:
        for name, path in entries:
            package.add(path, arcname=name, recursive=False)
        for name, body in (
            ("MANIFEST.md", manifest),
            ("frontend/release-meta.json", metadata),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(body)
            package.addfile(info, io.BytesIO(body))
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    # Verify contents rather than trusting the file list or archive call alone.
    with tarfile.open(archive) as package:
        names = package.getnames()
        assert len(names) == len(entries) + 2
        assert not any(
            ".." in n.split("/") or n.startswith("/") or ".env" in n for n in names
        )
        for name, path in entries:
            extracted = package.extractfile(name).read()
            assert (
                hashlib.sha256(extracted).digest()
                == hashlib.sha256(path.read_bytes()).digest()
            )
    (out / "MANIFEST.md").write_bytes(
        manifest
        + (
            f"\nArchive SHA-256: {checksum}\nArchive bytes: {archive.stat().st_size}\n"
        ).encode()
    )
    print(f"Candidate: {archive}\nSHA-256: {checksum}\nFiles: {len(names)}")


if __name__ == "__main__":
    main()
