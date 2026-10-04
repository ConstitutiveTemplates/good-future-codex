#!/usr/bin/env python3
"""Validate the good-future-codex sections corpus.

Real section shape (sections/<tier>/<slug>.md.jinja):

    {# ethics: id=<tier>-<slug> version=<YYYY-MM-DD.rev> status=<draft|active|kind>
       triggers=["kw", ...] #}
    # <title>
    > **適用条件**: ...
    ## 事実 ... ## 禁止パターン ... ## 推奨設定 ... ## 運用チェック ...
    ## 制度変更ウォッチ  (contains (review_by: YYYY-MM-DD) dates)

Checks (all errors are collected; exit 1 if any, else 0):

  * every ``sections/<tier>/<slug>.md.jinja`` appears in MANIFEST
    ``sections[].file`` and vice versa
  * every file opens with an ``{# ethics: ... #}`` header carrying
      - id        equals the MANIFEST id AND ``<tier>-<slug>`` derived from
                  the file path (``region/eu-cra.md.jinja`` -> ``region-eu-cra``)
      - version   ``YYYY-MM-DD.rev``
      - status    draft | active | kind
      - triggers  a non-empty string list
  * MANIFEST ``when`` / ``placement`` values stay in the documented vocabulary
  * section bodies are flag-agnostic: no ``{{`` / ``{%`` jinja expressions
    after the ethics header
  * every section keeps the required headings in order
    (## 事実 / ## 禁止パターン / ## 推奨設定 / ## 運用チェック / ## 制度変更ウォッチ)
  * every section carries at least one ``(review_by: YYYY-MM-DD)`` date in the
    制度変更ウォッチ block; expired dates are errors, due < 30d are warnings
  * section ids are unique (MANIFEST and files)

Run:  uv run --with pyyaml python tools/validate.py
      uv run --with pyyaml python tools/validate.py --drift
      (--drift prints due/expired review_by + probes in-body source URLs
      with curl HEAD and never exits non-zero)
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import yaml

REPO = Path(__file__).resolve().parent.parent
SECTIONS = REPO / "sections"
MANIFEST = SECTIONS / "MANIFEST.yml"

WHEN_VOCAB = {
    "always",
    "scraping",
    "oj_code",
    "mcp",
    "data_science",
    "web_api",
    "commercial",
    "eu_market",
    "jp",
    "ai_assisted",
}
PLACEMENT_VOCAB = {"agents_md", "charter", "legal_md", "standalone"}
STATUS_VOCAB = {"draft", "active", "kind"}
REQUIRED_HEADINGS = ("## 事実", "## 禁止パターン", "## 推奨設定", "## 運用チェック", "## 制度変更ウォッチ")

# sections/<tier>/<slug>.md.jinja -- _template.md.jinja at the top level
# is an authoring aid, not a section, and is deliberately not matched.
SECTION_GLOB = "*/*.md.jinja"

ETHICS_HEADER_RE = re.compile(r"\{#\s*ethics:\s*(.*?)#\}", re.DOTALL)
HEADER_ID_RE = re.compile(r"\bid=(\S+)")
HEADER_VERSION_RE = re.compile(r"\bversion=(\d{4}-\d{2}-\d{2}\.\d+)")
HEADER_STATUS_RE = re.compile(r"\bstatus=(\w+)")
HEADER_TRIGGERS_RE = re.compile(r"triggers=\[(.*?)\]", re.DOTALL)
REVIEW_BY_RE = re.compile(r"review_by:\s*(\d{4}-\d{2}-\d{2})")
HEADER_SOURCES_RE = re.compile(r"sources=\[(.*?)\]", re.DOTALL)
URL_RE = re.compile(r"https?://[^\s)<>\]\"']+")
JINJA_RE = re.compile(r"\{\{|\{%")
REVIEW_HORIZON = dt.timedelta(days=30)

errors: list[str] = []
warnings: list[str] = []


def error(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def load_manifest() -> dict:
    if not MANIFEST.is_file():
        error(f"{MANIFEST}: missing")
        return {}
    with MANIFEST.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict) or not isinstance(data.get("sections"), list):
        error("MANIFEST.yml: top-level 'sections' list missing")
        return {}
    return data


def section_files() -> list[Path]:
    return sorted(SECTIONS.glob(SECTION_GLOB))


def expected_id(path: Path) -> str:
    """region/eu-cra.md.jinja -> region-eu-cra (tier-slug naming rule)."""
    return f"{path.parent.name}-{path.name.removesuffix('.md.jinja')}"


def parse_header(path: Path) -> dict[str, str] | None:
    text = path.read_text(encoding="utf-8")
    match = ETHICS_HEADER_RE.search(text)
    if match is None:
        error(f"{path}: missing '{{# ethics: ... #}}' header comment")
        return None
    blob = match.group(1)
    id_m = HEADER_ID_RE.search(blob)
    version_m = HEADER_VERSION_RE.search(blob)
    status_m = HEADER_STATUS_RE.search(blob)
    triggers_m = HEADER_TRIGGERS_RE.search(blob)
    sources_m = HEADER_SOURCES_RE.search(blob)
    header: dict[str, str] = {}
    if not id_m:
        error(f"{path}: ethics header missing id=")
    else:
        header["id"] = id_m.group(1)
    if not version_m:
        error(f"{path}: ethics header missing version=<YYYY-MM-DD.rev> (got {id_m and blob[:60]!r})")
    else:
        header["version"] = version_m.group(1)
    if not status_m:
        error(f"{path}: ethics header missing status=")
    else:
        header["status"] = status_m.group(1)
    if not triggers_m or not triggers_m.group(1).strip():
        error(f"{path}: ethics header missing non-empty triggers=[...]")
    if sources_m:
        header["sources"] = sources_m.group(1)
    return header


def check_headings(path: Path, body: str) -> None:
    positions: dict[str, int] = {}
    for heading in REQUIRED_HEADINGS:
        idx = body.find(heading)
        if idx < 0:
            error(f"{path}: missing required heading {heading!r}")
        else:
            positions[heading] = idx
    if len(positions) == len(REQUIRED_HEADINGS):
        order = [positions[h] for h in REQUIRED_HEADINGS]
        if order != sorted(order):
            error(f"{path}: required headings out of order {REQUIRED_HEADINGS}")


def check_review_by(path: Path, body: str, drift_mode: bool = False) -> list[tuple[str, dt.date]]:
    found = [(m.group(1), dt.date.fromisoformat(m.group(1))) for m in REVIEW_BY_RE.finditer(body)]
    if not found:
        if not drift_mode:
            error(f"{path}: no (review_by: YYYY-MM-DD) date in 制度変更ウォッチ")
        return found
    today = dt.datetime.now(dt.UTC).date()
    for _, due in found:
        if due < today:
            msg = f"{path}: review_by {due} expired (today {today})"
            error(msg) if not drift_mode else print(f"[drift] EXPIRED {msg}")
        elif due <= today + REVIEW_HORIZON:
            msg = f"{path}: review_by {due} due within 30 days (today {today})"
            warn(msg) if not drift_mode else print(f"[drift] due {msg}")
    return found


def check_flag_agnostic(path: Path, text: str) -> None:
    header = ETHICS_HEADER_RE.search(text)
    if header is None:
        return  # parse_header already errored
    body = text[header.end():]
    for match in JINJA_RE.finditer(body):
        snippet = body[max(0, match.start() - 25): match.start() + 10].replace("\n", " ")
        error(f"{path}: jinja expression {match.group(0)!r} in body after ethics "
              f"header (near {snippet!r})")


def probe_source(url: str, timeout: float = 25.0) -> str:
    try:
        proc = subprocess.run(
            ["curl", "-sIL", "--max-time", str(int(timeout)), url],
            capture_output=True, text=True, check=False,
        )
    except FileNotFoundError:
        return "curl unavailable"
    status = None
    seen: set[str] = set()
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.lower().startswith("http/"):
            status = line.split(None, 1)[0]
        if line.lower().startswith("location:"):
            seen.add(line.split(":", 1)[1].strip())
    if status is None:
        return f"no HTTP status (exit {proc.returncode})"
    if status.startswith("30") and seen:
        return f"{status} -> {min(seen)}"
    return status


def drift_report() -> None:
    print("[drift] due/expired review_by:")
    today = dt.datetime.now(dt.UTC).date()
    any_due = False
    for path in section_files():
        body = path.read_text(encoding="utf-8")
        dates = check_review_by(path, body, drift_mode=True)
        if any(d < today or d <= today + REVIEW_HORIZON for _, d in dates):
            any_due = True
    if not any_due:
        print("[drift] no review_by due or expired")


    print("\n[drift] source liveness (curl HEAD):")
    flagged = 0
    probed = 0
    for path in section_files():
        text = path.read_text(encoding="utf-8")
        urls: set[str] = set()
        header_m = ETHICS_HEADER_RE.search(text)
        if header_m:
            sources_m = HEADER_SOURCES_RE.search(header_m.group(1))
            if sources_m:
                urls.update(URL_RE.findall(sources_m.group(1)))
        urls.update(URL_RE.findall(text[header_m.end():] if header_m else text))
        for url in sorted(urls):
            parsed = urlparse(url)
            if not parsed.netloc:
                continue
            probed += 1
            status = probe_source(url)
            bad = status.startswith(("40", "50")) or "no HTTP status" in status or "unavailable" in status
            flag = "  <-- FLAGGED" if bad else ""
            if bad:
                flagged += 1
            print(f"{path}: {url} -> {status}{flag}")
    if not probed:
        print("[drift] no source URLs declared (add sources=[...] to ethics headers)")
    elif not flagged:
        print("[drift] all sources live")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drift", action="store_true",
                        help="print due/expired review_by + probe in-body source URLs; exit 0 always")
    args = parser.parse_args()

    manifest = load_manifest()
    manifest_rows = manifest.get("sections", []) if manifest else []
    manifest_by_file: dict[str, dict] = {}
    for row in manifest_rows:
        if not isinstance(row, dict):
            error(f"MANIFEST.yml: section row {row!r} is not a mapping")
            continue
        sid = row.get("id")
        if not isinstance(sid, str) or not sid:
            error(f"MANIFEST.yml: section row {row!r} has no string id")
            continue
        if sid in manifest_by_file.values():
            error(f"MANIFEST.yml: duplicate section id {sid!r}")
        when = row.get("when")
        if when not in WHEN_VOCAB:
            error(f"MANIFEST.yml: section {sid!r}: when {when!r} not in {sorted(WHEN_VOCAB)}")
        placement = row.get("placement")
        if placement not in PLACEMENT_VOCAB:
            error(f"MANIFEST.yml: section {sid!r}: placement {placement!r} not in {sorted(PLACEMENT_VOCAB)}")
        file = row.get("file")
        if not isinstance(file, str):
            error(f"MANIFEST.yml: section {sid!r}: file must be a string")
        elif not (SECTIONS / file).is_file():
            error(f"MANIFEST.yml: section {sid!r}: file {file!r} does not exist")
        else:
            manifest_by_file[file] = row

    files = section_files()
    seen_ids: set[str] = set()
    for path in files:
        rel = path.relative_to(SECTIONS).as_posix()
        row = manifest_by_file.get(rel)
        if row is None:
            error(f"{path}: section file not listed in MANIFEST.yml")
        header = parse_header(path)
        if header is not None:
            sid = header.get("id")
            exp = expected_id(path)
            if sid and row is not None and sid != row.get("id"):
                error(f"{path}: header id {sid!r} != MANIFEST id {row.get('id')!r}")
            if sid and sid != exp:
                error(f"{path}: header id {sid!r} != path-derived id {exp!r}")
            if header.get("status") and header["status"] not in STATUS_VOCAB:
                error(f"{path}: status {header['status']!r} not in {sorted(STATUS_VOCAB)}")
            if sid:
                if sid in seen_ids:
                    error(f"{path}: duplicate section id {sid!r}")
                seen_ids.add(sid)
        text = path.read_text(encoding="utf-8")
        check_flag_agnostic(path, text)
        check_headings(path, text)
        check_review_by(path, text, drift_mode=args.drift)

    if args.drift:
        drift_report()
        return 0

    for msg in errors:
        print(f"error: {msg}", file=sys.stderr)
    for msg in warnings:
        print(f"warning: {msg}")
    if errors:
        print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    print(f"ok: {len(files)} sections validate ({len(warnings)} warning(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
