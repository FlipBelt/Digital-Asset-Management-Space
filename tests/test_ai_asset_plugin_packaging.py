"""Offline package integrity and non-destructive synchronization checks."""

import json
import os
import subprocess
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from scripts import package_ai_asset_plugin as package


class PackagingTests(unittest.TestCase):
    def build(self, target, remote_mcp_url=None, team_app_id=None):
        with patch.object(package, "git_evidence", return_value=("a" * 40, True)):
            return package.build_package(package.ROOT, target, remote_mcp_url, team_app_id)

    def test_three_targets_preserve_source_and_provenance(self):
        for target in ("team", "personal", "qwenwork"):
            with self.subTest(target=target):
                files = self.build(target)
                provenance = json.loads(files["SOURCE-PROVENANCE.json"])
                for name, sha in provenance["copied_files"].items():
                    source = package.ROOT / ".agents" / name
                    self.assertEqual(source.read_bytes(), files[name])
                    self.assertEqual(package.digest(files[name]), sha)
                expected = {name: package.digest(data) for name, data in files.items() if name != "SOURCE-PROVENANCE.json"}
                self.assertEqual(provenance["distribution_files"], expected)
                self.assertEqual(provenance["distribution_tree_sha256"], package.tree_digest(expected))
                self.assertTrue(provenance["canonical_worktree_dirty"])
                self.assertEqual(len(provenance["copied_files"]), 6)

    def test_zip_is_reproducible_rooted_correctly_and_byte_exact(self):
        files = self.build("qwenwork")
        content = package.zip_bytes(files)
        self.assertEqual(content, package.zip_bytes(files))
        with zipfile.ZipFile(BytesIO(content)) as archive:
            self.assertIsNone(archive.testzip())
            self.assertIn(".qoder-plugin/plugin.json", archive.namelist())
            self.assertNotIn(".qwen-plugin/plugin.json", archive.namelist())
            self.assertTrue(all("\\" not in name for name in archive.namelist()))
            self.assertEqual(len(archive.namelist()), len(set(archive.namelist())))
            self.assertEqual({name: archive.read(name) for name in archive.namelist()}, files)

    def test_filesystem_enumeration_order_cannot_change_package_bytes(self):
        expected = self.build("qwenwork")
        original = package.checked_files

        def reversed_files(*args, **kwargs):
            return dict(reversed(list(original(*args, **kwargs).items())))

        with patch.object(package, "checked_files", side_effect=reversed_files):
            self.assertEqual(package.zip_bytes(expected), package.zip_bytes(self.build("qwenwork")))

    def test_crlf_skill_source_is_rejected_before_git_can_change_hashed_bytes(self):
        original = package.checked_files

        def windows_line_endings(directory, *args, **kwargs):
            files = original(directory, *args, **kwargs)
            if directory.name == package.SKILLS[0]:
                files["SKILL.md"] = files["SKILL.md"].replace(b"\n", b"\r\n")
            return files

        with patch.object(package, "checked_files", side_effect=windows_line_endings):
            with self.assertRaisesRegex(ValueError, "Git byte parity"):
                self.build("team")

    def test_cannot_misrepresent_rest_as_mcp_or_bundle_automatic_connection(self):
        for target in ("team", "personal", "qwenwork"):
            files = self.build(target)
            self.assertNotIn(".mcp.json", files)
            self.assertNotIn(".app.json", files)
            if target != "qwenwork":
                self.assertFalse(any(name.startswith("connector/") for name in files))
            else:
                self.assertIn("connector/uv.lock", files)
                self.assertIn("connector/run.ps1", files)
            for name, data in files.items():
                self.assertNotIn(".venv", Path(name).parts)
                if name.endswith("plugin.json"):
                    manifest = json.loads(data)
                    self.assertFalse({"apps", "mcpServers"} & set(manifest))

    def test_explicit_remote_profile_wires_exact_mcp_without_inventing_app_or_credentials(self):
        endpoint = "https://jtzhzt.flipbeltchina.com/mcp"
        for target in ("team", "personal", "qwenwork"):
            with self.subTest(target=target):
                files = self.build(target, endpoint)
                manifest_name = ".qoder-plugin/plugin.json" if target == "qwenwork" else ".codex-plugin/plugin.json"
                manifest = json.loads(files[manifest_name])
                self.assertEqual(manifest["mcpServers"], "./.mcp.json")
                config = json.loads(files[manifest["mcpServers"].removeprefix("./")])
                self.assertEqual(config, {"mcpServers": {"flipbelt-ai-assets": {"type": "http", "url": endpoint}}})
                self.assertNotIn("apps", manifest)
                self.assertNotIn(".app.json", files)
                self.assertFalse(any(name.startswith("connector/") for name in files))
                provenance = json.loads(files["SOURCE-PROVENANCE.json"])
                self.assertEqual(provenance["connection_profile"], "remote-oauth-candidate")
                self.assertEqual(provenance["remote_mcp_url"], endpoint)
                self.assertFalse(provenance["remote_deployment_verified"])
                self.assertFalse(provenance["host_runtime_verified"])
                self.assertEqual(provenance["distribution_files"][".mcp.json"], package.digest(files[".mcp.json"]))
                for name, sha in provenance["copied_files"].items():
                    self.assertEqual(files[name], (package.ROOT / ".agents" / name).read_bytes())
                    self.assertEqual(sha, package.digest(files[name]))

    def test_remote_url_rejects_non_https_credentials_rest_query_and_path_ambiguity(self):
        for endpoint in (
            "", "http://example.invalid/mcp", "https://user:secret@example.invalid/mcp",
            "https://example.invalid", "https://example.invalid/api/v1/agent",
            "https://example.invalid/mcp/", "https://example.invalid/../mcp",
            "https://example.invalid/%2e%2e/mcp", "https://example.invalid/mcp?",
            "https://example.invalid/mcp?token=private", "https://example.invalid/mcp#",
            "https://example.invalid/mcp#fragment", "https://example.invalid:0/mcp",
            "https://example.invalid:65536/mcp", "https://example.invalid\\mcp",
            "https://example.invalid/mcp\n", "https:///mcp",
        ):
            with self.subTest(endpoint=endpoint):
                with self.assertRaisesRegex(ValueError, "exact HTTPS"):
                    self.build("qwenwork", endpoint)
        self.assertEqual(package.remote_url("https://example.invalid/test-api/mcp"), "https://example.invalid/test-api/mcp")
        self.assertIsNone(package.remote_url(None))

    def test_team_app_id_normalizes_only_the_supported_technical_id_shape(self):
        identity = "asdk_app_" + "a" * 32  # Synthetic format fixture, never an existing App claim.
        self.assertEqual(package.normalize_team_app_id(identity), identity)
        self.assertEqual(package.normalize_team_app_id("plugin_" + identity), identity)
        self.assertIsNone(package.normalize_team_app_id(None))
        for value in ("", "asdk_app_", "plugin_asdk_app_", "asdk_app__invalid",
                      " " + identity, identity + "\n", identity + "/extra", identity + "?query",
                      "plugin_plugin_" + identity, "connector_example", "asdk_app_" + "x" * 200):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "exact asdk_app_"):
                    package.normalize_team_app_id(value)

    def test_team_app_binding_is_exact_and_aliases_have_identical_provenance(self):
        endpoint = "https://example.invalid/mcp"
        identity = "asdk_app_" + "a" * 32
        files = self.build("team", endpoint, identity)
        self.assertEqual(files, self.build("team", endpoint, "plugin_" + identity))
        manifest = json.loads(files[".codex-plugin/plugin.json"])
        self.assertEqual(manifest["apps"], "./.app.json")
        self.assertNotIn("mcpServers", manifest)
        self.assertNotIn(".mcp.json", files)
        self.assertEqual(json.loads(files[".app.json"]), {
            "apps": {"flipbelt-ai-assets": {"id": identity, "required": True}},
        })
        provenance = json.loads(files["SOURCE-PROVENANCE.json"])
        self.assertEqual(provenance["workspace_app_id"], identity)
        self.assertEqual(provenance["remote_mcp_url"], endpoint)
        self.assertEqual(provenance["connection_profile"], "workspace-app-candidate")
        self.assertFalse(provenance["workspace_app_binding_verified"])
        self.assertFalse(provenance["host_runtime_verified"])
        self.assertEqual(provenance["distribution_files"][".app.json"], package.digest(files[".app.json"]))
        self.assertFalse(any(name.startswith("connector/") for name in files))

    def test_app_binding_rejects_other_targets_or_missing_remote_service(self):
        identity = "asdk_app_" + "a" * 32
        for target, endpoint in (("team", None), ("personal", "https://example.invalid/mcp"),
                                 ("qwenwork", "https://example.invalid/mcp")):
            with self.subTest(target=target):
                with self.assertRaisesRegex(ValueError, "team target and an explicit remote"):
                    self.build(target, endpoint, identity)

    def test_remote_team_market_requires_app_before_any_output_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output, market = root / "output", root / "market"
            for identity in (None, "plugin_invalid"):
                argv = ["package", "--output-dir", str(output), "--team-root", str(market),
                        "--remote-mcp-url", "https://example.invalid/mcp"]
                if identity is not None:
                    argv += ["--team-app-id", identity]
                with self.subTest(identity=identity), patch("sys.argv", argv):
                    with self.assertRaises(ValueError):
                        package.main()
                self.assertFalse(output.exists())
                self.assertFalse(market.exists())

    def test_cli_app_binding_affects_only_team_and_check_reuses_exact_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            identity = "asdk_app_" + "a" * 32
            argv = ["package", "--output-dir", str(output), "--remote-mcp-url", "https://example.invalid/mcp",
                    "--team-app-id", "plugin_" + identity]
            with patch("sys.argv", argv), patch.object(package, "git_evidence", return_value=("b" * 40, True)), patch("builtins.print"):
                package.main()
            self.assertTrue((output / "team/.app.json").is_file())
            self.assertFalse((output / "team/.mcp.json").exists())
            for target in ("personal", "qwenwork"):
                self.assertTrue((output / target / ".mcp.json").is_file())
                self.assertFalse((output / target / ".app.json").exists())
                self.assertNotIn(identity, (output / target / "SOURCE-PROVENANCE.json").read_text())
            before = package.checked_files(output)
            with patch("sys.argv", argv + ["--check"]), patch.object(package, "git_evidence", return_value=("b" * 40, True)), patch("builtins.print"):
                package.main()
            self.assertEqual(package.checked_files(output), before)

    def test_invalid_remote_url_stops_before_any_output_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            with patch("sys.argv", ["package", "--output-dir", str(output), "--remote-mcp-url", "https://example.invalid/api/v1/agent"]):
                with self.assertRaisesRegex(ValueError, "exact HTTPS"):
                    package.main()
            self.assertFalse(output.exists())

    def test_remote_zip_profile_is_exact_and_reproducible(self):
        files = self.build("qwenwork", "https://example.invalid/mcp")
        content = package.zip_bytes(files)
        self.assertEqual(content, package.zip_bytes(self.build("qwenwork", "https://example.invalid/mcp")))
        with zipfile.ZipFile(BytesIO(content)) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual({name: archive.read(name) for name in archive.namelist()}, files)
            self.assertEqual(len(archive.namelist()), len(set(archive.namelist())))

    def test_unknown_downstream_file_stops_without_deleting(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "user-note.md").write_text("preserve", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unexpected downstream"):
                package.preflight(directory, {"README.md": b"new"}, False)
            self.assertEqual((directory / "user-note.md").read_text(), "preserve")
            self.assertFalse((directory / "README.md").exists())

    def test_downstream_check_rejects_missing_or_modified_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            files = {"README.md": b"expected"}
            with self.assertRaisesRegex(ValueError, "drift"):
                package.preflight(directory, files, True)
            package.write_tree(directory, files)
            package.preflight(directory, files, True)
            (directory / "README.md").write_bytes(b"modified")
            with self.assertRaisesRegex(ValueError, "drift"):
                package.preflight(directory, files, True)

    def test_all_targets_preflight_before_first_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            out = root / "output"
            market = root / "market"
            (market / ".agents/plugins").mkdir(parents=True)
            (market / ".agents/plugins/marketplace.json").write_text(json.dumps({"name": "flipbelt-team"}))
            plugin = market / "plugins/flipbelt-ai-asset-center"
            plugin.mkdir(parents=True)
            (plugin / "private-note.md").write_text("keep")
            argv = ["package", "--output-dir", str(out), "--team-root", str(market)]
            with patch("sys.argv", argv), patch.object(package, "git_evidence", return_value=("b" * 40, True)):
                with self.assertRaisesRegex(ValueError, "Unexpected downstream"):
                    package.main()
            self.assertFalse(out.exists())
            self.assertEqual((plugin / "private-note.md").read_text(), "keep")

    def test_broken_relative_reference_is_not_silently_distributed(self):
        with self.assertRaisesRegex(ValueError, "Broken reference"):
            package.check_links({"skills/example/SKILL.md": b"[protocol](references/missing.md)"})

    def test_public_files_reject_credentials_and_machine_paths(self):
        for data in (b"C:/Users/synthetic/private", b"agt_" + b"x" * 30,
                     b"mcp_" + b"x" * 64, b"mrf_" + b"x" * 64,
                     b"-----BEGIN PRIVATE KEY-----"):
            with self.subTest(data=data[:20]):
                with self.assertRaises(ValueError):
                    package.public_files({"README.md": data})

    @unittest.skipUnless(os.name == "nt", "Windows junction boundary")
    def test_junction_entry_and_nested_source_are_rejected_before_resolution(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "outside"
            target.mkdir()
            link = root / "link"
            created = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(link), str(target)],
                                     capture_output=True, text=True)
            self.assertEqual(created.returncode, 0, created.stderr)
            with self.assertRaisesRegex(ValueError, "reparse"):
                package.safe_absolute(link / "output")
            with self.assertRaisesRegex(ValueError, "reparse"):
                package.preflight(link / "output", {"README.md": b"new"}, False)
            with self.assertRaisesRegex(ValueError, "reparse"):
                package.checked_files(root)
            self.assertFalse((target / "output").exists())


if __name__ == "__main__":
    unittest.main()
