"""Secret scan of the working tree and the whole git history (MASTERSPEC §9.4).

A stand-in for gitleaks, which is not installed in this environment. It looks for provider key
shapes and for assignments of secret-ish names to long literals, then reports file:line with the
match masked — the point is to find a leak, not to reprint it.

    python scripts/scan_secrets.py            # working tree (tracked files) + git history
    python scripts/scan_secrets.py --tree     # working tree only (fast; use in a pre-commit)

Exit code 1 if anything is found, so this can gate a release.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Provider key shapes. Kept specific: a scan nobody trusts is a scan nobody runs.
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[0-9A-Za-z-]{10,}\b")),
    ("stripe-key", re.compile(r"\b[sr]k_(?:live|test)_[0-9A-Za-z]{16,}\b")),
    ("openai-key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("huggingface-token", re.compile(r"\bhf_[A-Za-z0-9]{30,}\b")),
    ("elevenlabs-key", re.compile(r"\bsk_[0-9a-f]{40,}\b")),
    ("sentry-dsn-with-secret", re.compile(r"https://[0-9a-f]{16,}:[0-9a-f]{16,}@")),
    ("mongodb-srv-with-password", re.compile(r"mongodb(?:\+srv)?://[^\s:/@]+:[^\s:/@]+@")),
    ("private-key-block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    (
        "assigned-secret",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret|password|passwd|token|access[_-]?key|private[_-]?key)"
            r"\b\s*[:=]\s*[\"']([^\"'\s]{16,})[\"']"
        ),
    ),
)

# Placeholders and obvious non-secrets. These are the values a template is *meant* to contain.
ALLOW = re.compile(
    r"(?i)^(?:x+|\.+|<[^>]*>|\$\{?[a-z_]+\}?|your[_-]?\w*|changeme|placeholder|replace[_-]?me|"
    r"example\w*|dummy\w*|fake\w*|test\w*|none|null|true|false|\d+|sk-\.\.\.|"
    r"\*+|-+|_+)$"
)
# A match that still contains a template placeholder is a template, not a leak:
# "mongodb+srv://<user>:<password>@<cluster>" is exactly what .env.example is supposed to hold.
PLACEHOLDER_INSIDE = re.compile(r"<[^>]*>|\$\{[^}]*\}|%\([^)]*\)s|\{\{[^}]*\}\}")

# Paths whose long literals are lockfile hashes, fixtures or this scanner's own patterns.
SKIP_PATHS = re.compile(
    r"(?:^|/)(?:package-lock\.json|\.venv/|node_modules/|dist/|dist-e2e/|\.git/|"
    r"scripts/scan_secrets\.py|docs/SECURITY\.md)"
)
BINARY_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2", ".ttf", ".otf",
    ".pdf", ".gguf", ".bin", ".safetensors", ".mp3", ".wav", ".zip", ".gz", ".whl",
}


def mask(value: str) -> str:
    """Never print a candidate secret in full, even one that turns out to be a placeholder."""
    if len(value) <= 8:
        return value[0] + "*" * (len(value) - 1)
    return f"{value[:4]}...{value[-2:]} ({len(value)} chars)"


def findings(text: str, where: str) -> list[str]:
    out: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if len(line) > 4000:  # minified bundle or data blob: scan key shapes only
            line = line[:4000]
        for name, pattern in PATTERNS:
            for m in pattern.finditer(line):
                value = m.group(1) if m.groups() else m.group(0)
                if ALLOW.match(value) or PLACEHOLDER_INSIDE.search(m.group(0)):
                    continue
                out.append(f"{where}:{lineno}: {name}: {mask(value)}")
    return out


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, errors="replace", check=False
    ).stdout


def scan_tree() -> list[str]:
    hits: list[str] = []
    for rel in git("ls-files").splitlines():
        if not rel or SKIP_PATHS.search(rel) or Path(rel).suffix.lower() in BINARY_EXT:
            continue
        path = ROOT / rel
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hits += findings(text, rel)
    return hits


def scan_history() -> list[str]:
    """Every blob ever committed: a key removed in a later commit is still in the history."""
    hits: list[str] = []
    revs = git("rev-list", "--all").splitlines()
    for rev in revs:
        patch = git("show", "--format=%H", "--unified=0", "--no-color", rev)
        for line in patch.splitlines():
            if not line.startswith("+") or line.startswith("+++"):
                continue
            hits += [f"{rev[:10]}:{h.split(':', 2)[2]}" for h in findings(line[1:], "commit")]
    return sorted(set(hits))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tree", action="store_true", help="working tree only, skip git history")
    args = ap.parse_args()

    tree = scan_tree()
    print(f"working tree: {len(tree)} finding(s)")
    for hit in tree:
        print(f"  {hit}")

    history: list[str] = []
    if not args.tree:
        history = scan_history()
        print(f"git history: {len(history)} finding(s)")
        for hit in history:
            print(f"  {hit}")

    total = len(tree) + len(history)
    print("CLEAN" if total == 0 else f"FOUND {total} candidate secret(s) - review each")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
