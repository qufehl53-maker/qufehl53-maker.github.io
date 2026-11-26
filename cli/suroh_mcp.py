#!/usr/bin/env python3
"""
suroh_mcp.py — Zero-dependency stdio MCP (Model Context Protocol) server for Suroh tools.
Exposes local secret scrubbing, token rehydration, context packing, and secret scanning
to Claude Desktop, Claude Code, Cursor, and Windsurf using only Python 3 stdlib.

Homepage: https://qufehl53-maker.github.io
GitHub:   https://github.com/qufehl53-maker/qufehl53-maker.github.io
"""

from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

try:
    from cli.suroh_tools import (
        HIGH_CONF_PREFIXES,
        collect_files,
        estimate_tokens,
        rehydrate_text,
        scrub_text,
    )
except ImportError:
    from suroh_tools import (  # type: ignore
        HIGH_CONF_PREFIXES,
        collect_files,
        estimate_tokens,
        rehydrate_text,
        scrub_text,
    )

SERVER_INFO = {"name": "suroh-mcp", "version": "0.1.3"}
PROTOCOL_VERSION = "2024-11-05"

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "scrub_text",
        "description": (
            "Redact API keys, tokens, PEM private keys, URL credentials, emails, and IPs "
            "into deterministic reversible placeholders ([AI_API_KEY_1], [IPV4_1], etc.)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Raw text, logs, or config to scrub"},
                "keep_localhost": {
                    "type": "boolean",
                    "description": "Preserve 127.0.0.1 and 0.0.0.0 (default: true)",
                    "default": True,
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "rehydrate_text",
        "description": "Restore real secret values back into scrubbed text using a token_map.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text containing [TOKEN_1] placeholders"},
                "token_map": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "Mapping of placeholder token to original value",
                },
            },
            "required": ["text", "token_map"],
        },
    },
    {
        "name": "pack_context",
        "description": "Bundle files or directories into Claude-style XML or Markdown with optional secret scrubbing.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of file or directory paths to pack",
                },
                "format": {"type": "string", "enum": ["xml", "md"], "default": "xml"},
                "scrub": {"type": "boolean", "default": True},
                "line_numbers": {"type": "boolean", "default": False},
            },
            "required": ["paths"],
        },
    },
    {
        "name": "scan_secrets",
        "description": "Scan files or directories for leaked credentials without returning raw secret values.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Files or directories to scan",
                },
                "include_pii": {
                    "type": "boolean",
                    "description": "Also flag emails and IPv4 addresses (default: false)",
                    "default": False,
                },
            },
            "required": ["paths"],
        },
    },
]


def _call_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    if name == "scrub_text":
        text = str(args.get("text", ""))
        keep_localhost = bool(args.get("keep_localhost", True))
        sanitized, mapping = scrub_text(text, keep_localhost=keep_localhost)
        payload = {
            "sanitized_text": sanitized,
            "redacted_count": len(mapping),
            "token_map": mapping,
        }
        return {"content": [{"type": "text", "text": json.dumps(payload, indent=2)}]}

    if name == "rehydrate_text":
        text = str(args.get("text", ""))
        mapping = args.get("token_map") or {}
        if not isinstance(mapping, dict):
            return {"isError": True, "content": [{"type": "text", "text": "token_map must be an object"}]}
        restored = rehydrate_text(text, {str(k): str(v) for k, v in mapping.items()})
        return {"content": [{"type": "text", "text": restored}]}

    if name == "pack_context":
        paths = [str(p) for p in (args.get("paths") or [])]
        if not paths:
            return {"isError": True, "content": [{"type": "text", "text": "paths must be non-empty"}]}
        fmt = args.get("format", "xml")
        do_scrub = bool(args.get("scrub", True))
        line_nums = bool(args.get("line_numbers", False))
        files = collect_files(paths, include_locks=False)
        parts: List[str] = []
        if files:
            tree = "\n".join(f"  {rel}" for rel, _ in files)
            parts.append(
                f"<file_tree>\n{tree}\n</file_tree>" if fmt == "xml" else f"## File Tree\n```text\n{tree}\n```"
            )
        if fmt == "xml":
            docs = []
            for rel, body in files:
                if do_scrub:
                    body, _ = scrub_text(body)
                if line_nums:
                    body = "\n".join(f"{i+1:4d} | {line}" for i, line in enumerate(body.splitlines()))
                esc = rel.replace('"', "&quot;")
                docs.append(f'  <document path="{esc}">\n{body}\n  </document>')
            if docs:
                parts.append("<documents>\n" + "\n".join(docs) + "\n</documents>")
        else:
            for rel, body in files:
                if do_scrub:
                    body, _ = scrub_text(body)
                if line_nums:
                    body = "\n".join(f"{i+1:4d} | {line}" for i, line in enumerate(body.splitlines()))
                ext = Path(rel).suffix.lstrip(".")
                parts.append(f"### `{rel}`\n```{ext}\n{body}\n```")
        bundle = "\n\n".join(parts) + ("\n" if parts else "")
        header = f"# Packed {len(files)} file(s), ~{estimate_tokens(bundle):,} est. tokens\n\n"
        return {"content": [{"type": "text", "text": header + bundle}]}

    if name == "scan_secrets":
        paths = [str(p) for p in (args.get("paths") or [])]
        include_pii = bool(args.get("include_pii", False))
        files = collect_files(paths, include_locks=False)
        report: List[Dict[str, Any]] = []
        total_matches = 0
        for rel, content in files:
            filtered = "\n".join(
                ln for ln in content.splitlines() if "suroh:ignore" not in ln
            )
            _, mapping = scrub_text(filtered, keep_localhost=True)
            matched = []
            for tok in mapping:
                prefix = tok.strip("[]").rsplit("_", 1)[0]
                if include_pii or prefix in HIGH_CONF_PREFIXES:
                    matched.append(prefix)
            if matched:
                total_matches += len(matched)
                report.append({"file": rel, "count": len(matched), "types": sorted(set(matched))})
        summary = {
            "files_scanned": len(files),
            "total_findings": total_matches,
            "clean": total_matches == 0,
            "findings": report,
        }
        return {"content": [{"type": "text", "text": json.dumps(summary, indent=2)}]}

    return {"isError": True, "content": [{"type": "text", "text": f"Unknown tool: {name}"}]}


def handle_request(req: Dict[str, Any]) -> Dict[str, Any] | None:
    req_id = req.get("id")
    method = req.get("method", "")
    params = req.get("params") or {}

    if method == "notifications/initialized" or req_id is None and method.startswith("notifications/"):
        return None
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments") or {}
        try:
            res = _call_tool(name, args)
            return {"jsonrpc": "2.0", "id": req_id, "result": res}
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"isError": True, "content": [{"type": "text", "text": str(exc)}]},
            }

    if req_id is not None:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }
    return None


def main() -> int:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            err = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {exc}"}}
            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()
            continue
        resp = handle_request(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
