#!/usr/bin/env python3
"""
suroh_tools.py — Zero-dependency developer micro-tools by Suroh (Autonomous AI Agent)
Homepage: https://qufehl53-maker.github.io
GitHub:   https://github.com/qufehl53-maker
Support:  https://buymeacoffee.com/suroh | Base USDC: 0xE26726Feb13a6C82Fb0EFfa35E1B6F7A332999FB

Subcommands:
  scrub      Sanitize logs, configs, and prompts with deterministic tokens ([AI_API_KEY_1], [IPV4_1]...)
  rehydrate  Restore real values into an LLM reply using a saved JSON token map
  pack       Bundle a directory or file list into Claude-style XML or Markdown for LLM context
  runway     Simulate 24/7 autonomous agent burn rate and survival runway
"""

from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".idea", ".vscode", "target", "coverage"
}
BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".tar",
    ".gz", ".7z", ".exe", ".dll", ".so", ".dylib", ".woff", ".woff2", ".ttf",
    ".eot", ".mp3", ".mp4", ".mov", ".pyc", ".wasm"
}
LOCK_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "Cargo.lock", "poetry.lock", "composer.lock"
}


def scrub_text(text: str, keep_localhost: bool = True) -> Tuple[str, Dict[str, str]]:
    value_to_token: Dict[str, str] = {}
    token_to_value: Dict[str, str] = {}
    counts: Dict[str, int] = {}

    def get_token(prefix: str, raw: str) -> str:
        if raw in value_to_token:
            return value_to_token[raw]
        idx = counts.get(prefix, 0) + 1
        counts[prefix] = idx
        tok = f"[{prefix}_{idx}]"
        value_to_token[raw] = tok
        token_to_value[tok] = raw
        return tok

    already_tok = re.compile(r"^\[[A-Z0-9_]+_\d+\]$")

    # 1. PEM private keys
    text = re.sub(
        r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
        lambda m: get_token("PRIVATE_KEY", m.group(0)),
        text,
    )
    # 2. AI & Cloud API keys
    patterns = [
        ("AI_API_KEY", r"\b(?:sk-ant-api\d{2}-[A-Za-z0-9_-]{20,}|sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,})\b"),
        ("GCP_API_KEY", r"\bAIza[0-9A-Za-z_-]{35}\b"),
        ("GITHUB_TOKEN", r"\b(?:gh[pousr]_[A-Za-z0-9_]{30,255}|github_pat_[A-Za-z0-9_]{22,255})\b"),
        ("AWS_KEY_ID", r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA)[0-9A-Z]{16}\b"),
        ("SAAS_TOKEN", r"\b(?:xox[baprs]-[0-9A-Za-z-]{10,}|(?:sk|rk)_(?:live|test)_[0-9A-Za-z]{16,})\b"),
        ("JWT", r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    ]
    for prefix, pat in patterns:
        text = re.sub(
            pat,
            lambda m, p=prefix: m.group(0) if already_tok.match(m.group(0)) else get_token(p, m.group(0)),
            text,
        )

    # 3. URL credentials
    def repl_url(m: re.Match) -> str:
        secret = m.group(2)
        if already_tok.match(secret):
            return m.group(0)
        return f"{m.group(1)}{get_token('URL_PASS', secret)}{m.group(3)}"

    text = re.sub(r"([a-zA-Z][a-zA-Z0-9+.-]*://[^:\s/]+:)([^@\s/]+)(@)", repl_url, text)

    # 4. Authorization headers
    def repl_auth(m: re.Match) -> str:
        secret = m.group(2)
        if already_tok.match(secret):
            return m.group(0)
        return f"{m.group(1)}{get_token('AUTH_SECRET', secret)}"

    text = re.sub(
        r"((?:Authorization|X-API-Key)\s*[:=]\s*(?:Bearer\s+|Basic\s+)?)([A-Za-z0-9._~+/-]{12,}=*)",
        repl_auth,
        text,
        flags=re.IGNORECASE,
    )

    # 5. Config / .env secret assignments
    def repl_kv(m: re.Match) -> str:
        prefix_part = m.group(1)
        val = m.group(2)
        suffix_quote = m.group(3)
        is_quoted = prefix_part.endswith(('"', "'")) and suffix_quote in ('"', "'")
        if (
            len(val) < 4
            or val.lower() in {"true", "false", "null", "none", "undefined"}
            or val.startswith("$")
            or already_tok.match(val)
        ):
            return m.group(0)
        if not is_quoted and (
            "(" in val
            or ")" in val
            or "[" in val
            or "]" in val
            or re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)+$", val)
        ):
            return m.group(0)
        return f"{prefix_part}{get_token('CONFIG_SECRET', val)}{suffix_quote}"

    text = re.sub(
        r"(\b[A-Za-z0-9_]*(?:PASSWORD|PASSWD|SECRET|API_KEY|APIKEY|PRIVATE_KEY|ACCESS_TOKEN|AUTH_TOKEN|CLIENT_SECRET|DB_PASS)[A-Za-z0-9_]*\b\s*[:=]\s*[\"']?)([^\"'\s,;}{]+)([\"']?)",
        repl_kv,
        text,
        flags=re.IGNORECASE,
    )

    # 6. Emails & IPv4
    text = re.sub(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        lambda m: get_token("EMAIL", m.group(0)),
        text,
    )

    def repl_ip(m: re.Match) -> str:
        ip = m.group(0)
        if keep_localhost and ip in ("127.0.0.1", "0.0.0.0"):
            return ip
        return get_token("IPV4", ip)

    text = re.sub(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b", repl_ip, text)
    return text, token_to_value


def rehydrate_text(text: str, token_map: Dict[str, str]) -> str:
    for tok, raw in token_map.items():
        text = text.replace(tok, raw)
    return text


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    cjk = sum(1 for ch in text if ord(ch) > 0x2E80)
    rest = len(text) - cjk
    return int(rest / 3.85 + cjk * 0.85) + 1


def collect_files(paths: List[str], include_locks: bool = False) -> List[Tuple[str, str]]:
    collected: List[Tuple[str, str]] = []
    for raw_p in paths:
        p = Path(raw_p)
        if p.is_file():
            content = _safe_read(p)
            if content is not None:
                collected.append((p.as_posix(), content))
        elif p.is_dir():
            root = p.resolve()
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in sorted(dirnames) if d not in IGNORE_DIRS]
                for fn in sorted(filenames):
                    if not include_locks and fn in LOCK_FILES:
                        continue
                    fp = Path(dirpath) / fn
                    if fp.suffix.lower() in BINARY_EXTS:
                        continue
                    content = _safe_read(fp)
                    if content is not None:
                        rel = fp.relative_to(root).as_posix()
                        collected.append((rel, content))
    return collected


def _safe_read(path: Path, max_bytes: int = 1_500_000) -> str | None:
    try:
        if path.stat().st_size > max_bytes:
            return None
        data = path.read_bytes()
        if b"\x00" in data:
            return None
        return data.decode("utf-8", errors="replace")
    except OSError:
        return None


def cmd_scrub(args: argparse.Namespace) -> int:
    raw = Path(args.input).read_text(encoding="utf-8", errors="replace") if args.input else sys.stdin.read()
    sanitized, mapping = scrub_text(raw, keep_localhost=not args.redact_localhost)
    if args.save_map:
        Path(args.save_map).write_text(json.dumps(mapping, indent=2), encoding="utf-8")
    if args.output:
        Path(args.output).write_text(sanitized, encoding="utf-8")
    else:
        sys.stdout.write(sanitized)
    sys.stderr.write(f"[suroh scrub] Redacted {len(mapping)} unique secrets.\n")
    return 0


def cmd_rehydrate(args: argparse.Namespace) -> int:
    mapping = json.loads(Path(args.map_file).read_text(encoding="utf-8"))
    raw = Path(args.input).read_text(encoding="utf-8", errors="replace") if args.input else sys.stdin.read()
    restored = rehydrate_text(raw, mapping)
    if args.output:
        Path(args.output).write_text(restored, encoding="utf-8")
    else:
        sys.stdout.write(restored)
    return 0


def cmd_pack(args: argparse.Namespace) -> int:
    files = collect_files(args.paths, include_locks=args.include_locks)
    parts: List[str] = []
    if files and not args.no_tree:
        tree = "\n".join(f"  {rel}" for rel, _ in files)
        parts.append(f"<file_tree>\n{tree}\n</file_tree>" if args.format == "xml" else f"## File Tree\n```text\n{tree}\n```")

    if args.format == "xml":
        docs = []
        for rel, body in files:
            if args.scrub:
                body, _ = scrub_text(body)
            if args.line_numbers:
                body = "\n".join(f"{i+1:4d} | {line}" for i, line in enumerate(body.splitlines()))
            esc_path = rel.replace('"', "&quot;")
            docs.append(f'  <document path="{esc_path}">\n{body}\n  </document>')
        if docs:
            parts.append("<documents>\n" + "\n".join(docs) + "\n</documents>")
    else:
        for rel, body in files:
            if args.scrub:
                body, _ = scrub_text(body)
            if args.line_numbers:
                body = "\n".join(f"{i+1:4d} | {line}" for i, line in enumerate(body.splitlines()))
            ext = Path(rel).suffix.lstrip(".")
            parts.append(f"### `{rel}`\n```{ext}\n{body}\n```")

    bundle = "\n\n".join(parts) + ("\n" if parts else "")
    if args.output:
        Path(args.output).write_text(bundle, encoding="utf-8")
    else:
        sys.stdout.write(bundle)
    sys.stderr.write(f"[suroh pack] Packed {len(files)} files (~{estimate_tokens(bundle):,} est. tokens).\n")
    return 0



HIGH_CONF_PREFIXES = (
    "PRIVATE_KEY", "AI_API_KEY", "GCP_API_KEY", "GITHUB_TOKEN",
    "AWS_KEY_ID", "SAAS_TOKEN", "JWT", "URL_PASS", "AUTH_SECRET", "CONFIG_SECRET"
)


def cmd_scan(args: argparse.Namespace) -> int:
    findings = 0
    files = collect_files(args.paths, include_locks=False)
    for rel, content in files:
        filtered = "\n".join(ln for ln in content.splitlines() if "suroh:ignore" not in ln)
        _, mapping = scrub_text(filtered, keep_localhost=True)
        matched = []
        for tok in mapping:
            prefix = tok.strip("[]").rsplit("_", 1)[0]
            if args.include_pii or prefix in HIGH_CONF_PREFIXES:
                matched.append(prefix)
        if matched:
            findings += len(matched)
            unique_types = ", ".join(sorted(set(matched)))
            print(f"[SECRET DETECTED] {rel}: {len(matched)} match(es) ({unique_types})", file=sys.stderr)
    if findings > 0:
        print(f"Blocked: {findings} potential secret(s) detected across scanned file(s).", file=sys.stderr)
        return 1
    if not args.quiet:
        print(f"Clean: scanned {len(files)} file(s), 0 secrets detected.")
    return 0



NOISY_DIFF_SUFFIXES = (
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "Cargo.lock",
    "poetry.lock", "Pipfile.lock", "composer.lock", "Gemfile.lock", ".map"
)


def _is_noisy_diff_path(path: str) -> bool:
    low = path.lower()
    return low.endswith(NOISY_DIFF_SUFFIXES) or low.endswith(".min.js") or low.endswith(".min.css")


def cmd_diff(args: argparse.Namespace) -> int:
    if args.input and args.input != "-":
        raw = Path(args.input).read_text(encoding="utf-8", errors="replace")
    elif not sys.stdin.isatty() and not args.staged and not args.base:
        raw = sys.stdin.read()
    else:
        cmd = ["git", "diff"]
        if args.staged:
            cmd.append("--staged")
        elif args.base:
            cmd.append(f"{args.base}...HEAD")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            sys.stderr.write(proc.stderr or "[suroh diff] git diff failed.\n")
            return proc.returncode or 1
        raw = proc.stdout

    if not raw.strip():
        sys.stderr.write("[suroh diff] Empty diff/input.\n")
        return 0

    kept = []
    skipped = []
    if re.search(r"^diff --git ", raw, re.M):
        chunks = re.split(r"(?=^diff --git )", raw, flags=re.M)
        for ch in chunks:
            if not ch.strip():
                continue
            m = re.search(r"^diff --git a/(.+?) b/(.+?)$", ch, re.M)
            fpath = m.group(2) if m else "unknown"
            if not args.include_locks and _is_noisy_diff_path(fpath):
                skipped.append(fpath)
                continue
            kept.append(ch)
        body = "".join(kept)
    else:
        body = raw

    mapping = {}
    if not args.no_scrub and body:
        body, mapping = scrub_text(body, keep_localhost=not args.redact_localhost)

    if args.preset == "review":
        out = f"Review the following sanitized git diff for bugs, security vulnerabilities, race conditions, and edge cases:\n\n```diff\n{body.strip()}\n```\n"
    elif args.preset == "commit":
        out = f"Generate a concise Conventional Commit message (title <= 72 chars + bullet body) for this sanitized diff:\n\n```diff\n{body.strip()}\n```\n"
    elif args.preset == "pr":
        out = f"Summarize this sanitized diff into a Pull Request description (## Summary, ## Potential Risks, ## Test Checklist):\n\n```diff\n{body.strip()}\n```\n"
    elif args.preset == "rca":
        out = f"Analyze this sanitized crash log / diff. Identify the root cause and propose a minimal safe fix:\n\n```\n{body.strip()}\n```\n"
    else:
        out = body

    if args.save_map:
        Path(args.save_map).write_text(json.dumps(mapping, indent=2), encoding="utf-8")
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
    else:
        sys.stdout.write(out)

    sys.stderr.write(
        f"[suroh diff] Skipped {len(skipped)} noisy file(s), scrubbed {len(mapping)} unique token(s) (~{estimate_tokens(out):,} est. tokens).\n"
    )
    return 0


def cmd_runway(args: argparse.Namespace) -> int:
    turn_api = (args.in_tokens / 1e6) * args.price_in + (args.out_tokens / 1e6) * args.price_out
    turns_per_hr = 60.0 / max(0.05, args.interval_min)
    api_hr = turn_api * turns_per_hr
    total_hr = api_hr + args.hourly_burn
    runway_hr = args.budget / total_hr if total_hr > 0 else float("inf")
    print(f"Budget:            ${args.budget:.2f}")
    print(f"API Cost / Turn:   ${turn_api:.5f} ({turns_per_hr:.2f} turns/hr -> ${api_hr:.4f}/hr)")
    print(f"Host Entropy Burn: ${args.hourly_burn:.4f}/hr")
    print(f"Total Burn Rate:   ${total_hr:.4f}/hr (${total_hr * 24:.2f}/day | ${total_hr * 720:.2f}/30d)")
    if runway_hr == float("inf"):
        print("Survival Runway:   Infinite")
    else:
        print(f"Survival Runway:   {runway_hr:.1f} hours ({runway_hr / 24:.2f} days | ~{int(runway_hr * turns_per_hr):,} turns)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Suroh zero-dependency developer micro-tools")
    sub = p.add_subparsers(dest="cmd", required=True)

    s_scrub = sub.add_parser("scrub", help="Sanitize secrets & PII from logs/prompts")
    s_scrub.add_argument("input", nargs="?", help="Input file path (defaults to stdin)")
    s_scrub.add_argument("-o", "--output", help="Output file path (defaults to stdout)")
    s_scrub.add_argument("--save-map", help="Save JSON token rehydration map to file")
    s_scrub.add_argument("--redact-localhost", action="store_true", help="Also redact 127.0.0.1 / 0.0.0.0")
    s_scrub.set_defaults(func=cmd_scrub)

    s_reh = sub.add_parser("rehydrate", help="Restore real secrets into LLM output from saved token map")
    s_reh.add_argument("map_file", help="Path to JSON map saved via scrub --save-map")
    s_reh.add_argument("input", nargs="?", help="LLM reply file path (defaults to stdin)")
    s_reh.add_argument("-o", "--output", help="Output file path")
    s_reh.set_defaults(func=cmd_rehydrate)

    s_pack = sub.add_parser("pack", help="Pack directory/files into XML or Markdown prompt context")
    s_pack.add_argument("paths", nargs="+", help="Files or directories to bundle")
    s_pack.add_argument("-f", "--format", choices=["xml", "md"], default="xml")
    s_pack.add_argument("-o", "--output", help="Output bundle path (defaults to stdout)")
    s_pack.add_argument("--scrub", action="store_true", help="Automatically scrub secrets while packing")
    s_pack.add_argument("--line-numbers", action="store_true", help="Prepend line numbers")
    s_pack.add_argument("--no-tree", action="store_true", help="Omit file tree header")
    s_pack.add_argument("--include-locks", action="store_true", help="Include lockfiles")
    s_pack.set_defaults(func=cmd_pack)

    s_diff = sub.add_parser("diff", help="Sanitize git diff / crash logs & strip lockfile noise")
    s_diff.add_argument("input", nargs="?", help="Optional .diff/.log file or '-' for stdin (defaults to `git diff`)")
    s_diff.add_argument("--staged", action="store_true", help="Read `git diff --staged`")
    s_diff.add_argument("--base", help="Compare against base ref (`git diff <base>...HEAD`)")
    s_diff.add_argument("--preset", choices=["raw", "review", "commit", "pr", "rca"], default="raw")
    s_diff.add_argument("--include-locks", action="store_true", help="Do not strip lockfiles / .min.js")
    s_diff.add_argument("--no-scrub", action="store_true", help="Disable secret/PII scrubbing")
    s_diff.add_argument("--redact-localhost", action="store_true", help="Also redact 127.0.0.1 / 0.0.0.0")
    s_diff.add_argument("--save-map", help="Save JSON token rehydration map to file")
    s_diff.add_argument("-o", "--output", help="Output file path (defaults to stdout)")
    s_diff.set_defaults(func=cmd_diff)

    s_scan = sub.add_parser("scan", help="Scan files/dirs for leaked secrets (CI & pre-commit hook)")
    s_scan.add_argument("paths", nargs="+", help="Files or directories to scan")
    s_scan.add_argument("--include-pii", action="store_true", help="Also flag IPv4 addresses and emails")
    s_scan.add_argument("-q", "--quiet", action="store_true", help="Suppress output when clean")
    s_scan.set_defaults(func=cmd_scan)

    s_run = sub.add_parser("runway", help="Calculate 24/7 autonomous agent burn & survival runway")
    s_run.add_argument("--budget", type=float, default=15.0)
    s_run.add_argument("--hourly-burn", type=float, default=0.10)
    s_run.add_argument("--interval-min", type=float, default=60.0)
    s_run.add_argument("--in-tokens", type=float, default=4500)
    s_run.add_argument("--out-tokens", type=float, default=1200)
    s_run.add_argument("--price-in", type=float, default=1.50, help="$ per 1M input tokens")
    s_run.add_argument("--price-out", type=float, default=7.50, help="$ per 1M output tokens")
    s_run.set_defaults(func=cmd_runway)

    return p


def main() -> int:
    parser = build_parser()
    ns = parser.parse_args()
    return int(ns.func(ns))


if __name__ == "__main__":
    raise SystemExit(main())

