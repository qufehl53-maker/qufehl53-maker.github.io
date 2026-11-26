import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli.suroh_tools import scrub_text, rehydrate_text
from cli.suroh_mcp import handle_request


class TestSurohTools(unittest.TestCase):
    def test_scrub_and_rehydrate_roundtrip(self):
        raw = (
            "OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz123456\n"
            "postgres://admin:S3cretPass!@10.20.30.40:5432/prod\n"
            "Contact: alice@example.com from 127.0.0.1\n"
        )
        scrubbed, mapping = scrub_text(raw, keep_localhost=True)
        self.assertIn("[AI_API_KEY_1]", scrubbed)
        self.assertIn("[URL_PASS_1]", scrubbed)
        self.assertIn("[IPV4_1]", scrubbed)
        self.assertIn("[EMAIL_1]", scrubbed)
        self.assertIn("127.0.0.1", scrubbed)
        self.assertNotIn("S3cretPass!", scrubbed)
        restored = rehydrate_text(scrubbed, mapping)
        self.assertEqual(restored, raw)

    def test_repl_kv_avoids_code_false_positives(self):
        code = (
            "secret = m.group(2)\n"
            "secretInput = document.getElementById('box')\n"
            "api_key = config.api_key\n"
        )
        scrubbed, mapping = scrub_text(code)
        self.assertEqual(mapping, {})
        self.assertEqual(scrubbed, code)

    def test_repl_kv_catches_real_unquoted_and_quoted_secrets(self):
        env = 'DB_PASS=myS3cret99\nCLIENT_SECRET="prod_secret_xyz"\n'
        scrubbed, mapping = scrub_text(env)
        self.assertEqual(len(mapping), 2)
        self.assertNotIn("myS3cret99", scrubbed)
        self.assertNotIn("prod_secret_xyz", scrubbed)

    def test_cli_scan_clean_on_cli_dir(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "cli" / "suroh_tools.py"), "scan", str(ROOT / "cli")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr + proc.stdout)

    def test_cli_scan_respects_suroh_ignore(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "demo.py"
            f.write_text('TOKEN = "ghp_1234567890abcdefABCDEF1234567890abcd" # suroh:ignore\n', encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(ROOT / "cli" / "suroh_tools.py"), "scan", str(td)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)

    def test_mcp_protocol_flow(self):
        init = handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(init["result"]["serverInfo"]["name"], "suroh-mcp")

        lst = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tool_names = [t["name"] for t in lst["result"]["tools"]]
        self.assertEqual(tool_names, ["scrub_text", "rehydrate_text", "pack_context", "scan_secrets"])

        call_scrub = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "scrub_text", "arguments": {"text": "key=ghp_1234567890abcdefABCDEF1234567890abcd"}},
            }
        )
        data = json.loads(call_scrub["result"]["content"][0]["text"])
        self.assertEqual(data["redacted_count"], 1)
        self.assertIn("[GITHUB_TOKEN_1]", data["sanitized_text"])

        call_reh = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "rehydrate_text",
                    "arguments": {"text": data["sanitized_text"], "token_map": data["token_map"]},
                },
            }
        )
        self.assertEqual(call_reh["result"]["content"][0]["text"], "key=ghp_1234567890abcdefABCDEF1234567890abcd")


if __name__ == "__main__":
    unittest.main()
