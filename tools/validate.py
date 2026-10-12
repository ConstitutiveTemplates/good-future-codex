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
      uv run --with pyyaml python tools/validate.py --sources
      (--drift prints due/expired review_by + probes declared source URLs
      with curl HEAD (GET fallback) and never exits non-zero; --sources
      probes only the declared source URLs and exits 1 when any is flagged)
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

ProbeFn = Callable[[str], str]
RunnerFn = Callable[..., Any]

REPO = Path(__file__).resolve().parent.parent
SECTIONS = REPO / "sections"
MANIFEST = SECTIONS / "MANIFEST.yml"

# --- Manifest vocabularies --------------------------------------------------
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

# --- Section header/body patterns -------------------------------------------
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

# --- Declared-source liveness probing ---------------------------------------
SOURCE_TIMEOUT = 10.0
SOURCE_RETRIES = 2
SOURCE_USER_AGENT = (
    "good-future-codex-check/1.0"
    " (+https://github.com/ConstitutiveTemplates/good-future-codex)"
)
CURL_STATUS_RE = re.compile(r"^http/\S+\s+(\d{3})\b", re.IGNORECASE)

# HTTP status classes treated as dead/flagged probe results.
FLAGGED_STATUS_PREFIXES = ("40", "50")
# Markers of non-HTTP probe results (curl missing, no response received).
NO_HTTP_STATUS_MARKER = "no HTTP status"
UNAVAILABLE_MARKER = "unavailable"
# HEAD responses retried as GET (server refuses HEAD but may serve GET).
HEAD_FALLBACK_CODES = frozenset({"405", "501"})
# Redirect responses carry a target location worth reporting.
REDIRECT_STATUS_PREFIX = "30"
# Upstream grounding lookup locations.
OBLIGATIONS_SUBDIR = "obligations"
OPEN_LAW_SOURCES_SUBDIR = Path("src") / "open_law" / "sources"

# Probe-result triple: (origin relpath, url, status string).
SourceFlag = tuple[str, str, str]

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


def _report_review_date(path: Path, due: dt.date, today: dt.date, *, drift_mode: bool) -> None:
    if due < today:
        msg = f"{path}: review_by {due} expired (today {today})"
        if drift_mode:
            print(f"[drift] EXPIRED {msg}")
        else:
            error(msg)
    elif due <= today + REVIEW_HORIZON:
        msg = f"{path}: review_by {due} due within 30 days (today {today})"
        if drift_mode:
            print(f"[drift] due {msg}")
        else:
            warn(msg)


def check_review_by(path: Path, body: str, drift_mode: bool = False) -> list[tuple[str, dt.date]]:
    found = [(m.group(1), dt.date.fromisoformat(m.group(1))) for m in REVIEW_BY_RE.finditer(body)]
    if not found:
        if not drift_mode:
            error(f"{path}: no (review_by: YYYY-MM-DD) date in 制度変更ウォッチ")
        return found
    today = dt.datetime.now(dt.UTC).date()
    for _, due in found:
        _report_review_date(path, due, today, drift_mode=drift_mode)
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


def strip_url_punct(url: str) -> str:
    """Drop trailing prose punctuation the URL regex may have swallowed."""
    return url.rstrip(".,;:!?")


def _split_header_body(text: str) -> tuple[str, str]:
    """Split section text into (header sources blob, body after the header)."""
    header_m = ETHICS_HEADER_RE.search(text)
    if header_m is None:
        return "", text
    sources_m = HEADER_SOURCES_RE.search(header_m.group(1))
    head = sources_m.group(1) if sources_m else ""
    return head, text[header_m.end():]


def extract_section_urls(text: str) -> list[str]:
    """URLs declared by one .md.jinja section: header sources + body links."""
    head, body = _split_header_body(text)
    return [strip_url_punct(u) for u in URL_RE.findall(head) + URL_RE.findall(body)]


def _collect_yaml_source_urls(node: object, found: list[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "sources" and isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        url = strip_url_punct(item.strip())
                        if url.startswith(("http://", "https://")):
                            found.append(url)
            else:
                _collect_yaml_source_urls(value, found)
    elif isinstance(node, list):
        for item in node:
            _collect_yaml_source_urls(item, found)


def extract_yaml_sources(doc: object) -> list[str]:
    """URL strings under any `sources:` list in a YAML doc (e.g. lang/*.yml)."""
    found: list[str] = []
    _collect_yaml_source_urls(doc, found)
    return found


def _add_source_urls(collected: dict[str, set[str]], origin: str, urls: Iterable[str]) -> None:
    for url in urls:
        parsed = urlparse(url)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            collected.setdefault(origin, set()).add(url)


def _manifest_source_urls(sections_dir: Path, collected: dict[str, set[str]]) -> None:
    manifest_path = sections_dir / "MANIFEST.yml"
    if not manifest_path.is_file():
        return
    with manifest_path.open(encoding="utf-8") as fh:
        manifest = yaml.safe_load(fh) or {}
    rows = manifest.get("sections", []) if isinstance(manifest, dict) else []
    for row in rows or []:
        if isinstance(row, dict) and isinstance(row.get("sources"), list):
            _add_source_urls(collected, "MANIFEST.yml", [u for u in row["sources"] if isinstance(u, str)])


def _section_file_source_urls(sections_dir: Path, collected: dict[str, set[str]]) -> None:
    for path in sorted(sections_dir.glob(SECTION_GLOB)):
        _add_source_urls(collected,
                         path.relative_to(sections_dir).as_posix(),
                         extract_section_urls(path.read_text(encoding="utf-8")))


def _yaml_data_source_urls(sections_dir: Path, collected: dict[str, set[str]]) -> None:
    for pattern in ("*.yml", "*.yaml"):
        for path in sorted(sections_dir.rglob(pattern)):
            if path.name == "MANIFEST.yml":
                continue
            with path.open(encoding="utf-8") as fh:
                doc = yaml.safe_load(fh)
            _add_source_urls(collected,
                             path.relative_to(sections_dir).as_posix(),
                             extract_yaml_sources(doc))


def collect_source_urls(sections_dir: Path = SECTIONS) -> dict[str, list[str]]:
    """Map relative file path -> sorted unique declared source URLs.

    Covers MANIFEST.yml rows (optional ``sources:``), every
    ``sections/*/*.md.jinja`` (header ``sources=[...]`` + body links),
    and sibling YAML data files (any ``sources:`` list, e.g.
    ``lang/copyright-terms.yml``). Reads files only; never touches
    the network.
    """
    collected: dict[str, set[str]] = {}
    _manifest_source_urls(sections_dir, collected)
    _section_file_source_urls(sections_dir, collected)
    _yaml_data_source_urls(sections_dir, collected)
    return {origin: sorted(urls) for origin, urls in sorted(collected.items())}


def is_flagged_status(status: str, *, has_upstream_grounding: bool = False) -> bool:
    """Whether a probe result counts as a dead/flagged source."""
    if status == "403" and has_upstream_grounding:
        return False
    return (
        status.startswith(FLAGGED_STATUS_PREFIXES)
        or NO_HTTP_STATUS_MARKER in status
        or UNAVAILABLE_MARKER in status
    )


def parse_curl_status(output: str) -> tuple[str | None, set[str]]:
    """Final ``(status code, redirect locations)`` from curl -i output."""
    code: str | None = None
    locations: set[str] = set()
    for line in output.splitlines():
        line = line.strip()
        match = CURL_STATUS_RE.match(line)
        if match:
            code = match.group(1)
        elif line.lower().startswith("location:"):
            locations.add(line.split(":", 1)[1].strip())
    return code, locations


def curl_args(url: str, head: bool, timeout: float, retries: int) -> list[str]:
    """Polite curl invocation: bounded time, a few retries, named UA."""
    args = [
        "curl", "-sSL",
        "--max-time", str(int(timeout)),
        "--connect-timeout", str(int(timeout)),
        "--retry", str(max(0, int(retries))), "--retry-all-errors",
        "-A", SOURCE_USER_AGENT,
    ]
    if head:
        args.append("-I")
    else:
        args += ["-o", "/dev/null"]
    args.append(url)
    return args


def _run_curl(url: str, head: bool, timeout: float, retries: int, runner: RunnerFn) -> Any | None:
    """Run one curl probe; None when curl itself is missing."""
    try:
        return runner(curl_args(url, head, timeout, retries),
                      capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return None


def probe_source(
    url: str,
    timeout: float = SOURCE_TIMEOUT,
    retries: int = SOURCE_RETRIES,
    runner: RunnerFn = subprocess.run,
) -> str:
    """HEAD url (GET fallback on 405/501); return a short status string."""
    proc = _run_curl(url, True, timeout, retries, runner)
    if proc is None:
        return "curl unavailable"
    code, locations = parse_curl_status(proc.stdout)
    if code in HEAD_FALLBACK_CODES:
        proc = _run_curl(url, False, timeout, retries, runner)
        if proc is None:
            return "curl unavailable"
        code, locations = parse_curl_status(proc.stdout)
    if code is None:
        return f"no HTTP status (exit {proc.returncode})"
    if code.startswith(REDIRECT_STATUS_PREFIX) and locations:
        return f"{code} -> {min(locations)}"
    return code


def format_source_summary(probed: int, flagged: int) -> str:
    return f"[drift] source probes: {probed} total, {flagged} flagged"


def print_source_summary(probed: int, flagged: int) -> None:
    if not probed:
        print("[drift] no source URLs declared (add sources=[...] to ethics headers)")
    else:
        print(format_source_summary(probed, flagged))
        if not flagged:
            print("[drift] all sources live")


def _probe_unique_urls(
    collected: dict[str, list[str]],
    probe: ProbeFn,
) -> tuple[dict[str, str], int]:
    """Probe each unique URL once in origin order; return (status by url, probed count)."""
    statuses: dict[str, str] = {}
    probed = 0
    for _origin, urls in collected.items():
        for url in urls:
            if url not in statuses:
                statuses[url] = probe(url)
                probed += 1
    return statuses, probed


def _is_flagged_with_grounding(origin: str, url: str, status: str) -> bool:
    """Flag classification that excuses 403s covered by an upstream grounding."""
    upstream = check_upstream_project_status(origin, url) if status == "403" else []
    return is_flagged_status(status, has_upstream_grounding=bool(upstream))


def check_sources(
    sections_dir: Path = SECTIONS,
    probe: ProbeFn = probe_source,
) -> tuple[int, list[SourceFlag]]:
    """Probe each unique declared URL once; return (probed, flagged origins)."""
    collected = collect_source_urls(sections_dir)
    statuses, probed = _probe_unique_urls(collected, probe)
    flagged: list[SourceFlag] = []
    for origin, urls in collected.items():
        for url in urls:
            status = statuses[url]
            if _is_flagged_with_grounding(origin, url, status):
                flagged.append((origin, url, status))
    return probed, flagged


def flagged_unique_count(flagged: list[SourceFlag]) -> int:
    return len({url for _, url, _ in flagged})


def _load_obligation_doc(path: Path) -> dict | None:
    try:
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _open_law_note(grounding: dict, open_law_dir: Path) -> str | None:
    ref = grounding.get("open_law")
    if not isinstance(ref, dict) or not open_law_dir.is_dir():
        return None
    src_id = ref.get("source")
    law_id = ref.get("id")
    adapter = open_law_dir / OPEN_LAW_SOURCES_SUBDIR / f"{src_id}.py"
    available = "adapter installed" if adapter.is_file() else "no local adapter"
    return f"       -> [open-law] source={src_id} law_id={law_id} ({available})"


def _obligation_notes(
    data: dict,
    *,
    ob_id: str,
    sec_id: str,
    url: str,
    open_law_dir: Path,
) -> list[str]:
    notes: list[str] = []
    related = data.get("related_sections", [])
    groundings = data.get("groundings", [])
    matched = False
    for grounding in groundings:
        if isinstance(grounding, dict) and url in grounding.get("sources", []):
            matched = True
            authority = str(grounding.get("authority", "unnamed authority")).strip()
            notes.append(
                f"    -> [law-map] {ob_id}: {authority} "
                f"(status: {grounding.get('status')}, review_by: {grounding.get('review_by')})"
            )
            open_law_note = _open_law_note(grounding, open_law_dir)
            if open_law_note is not None:
                notes.append(open_law_note)
    if not matched and sec_id in related:
        notes.append(
            f"    -> [law-map] governing obligation: {ob_id} ({data.get('title', '').strip()})"
        )
    return notes


def check_upstream_project_status(
    origin: str,
    url: str,
    law_map_dir: Path = REPO.parent / "law-map",
    open_law_dir: Path = REPO.parent / "open-law",
) -> list[str]:
    """Inspect upstream law-map and open-law for groundings covering a failed URL."""
    notes: list[str] = []
    if not law_map_dir.is_dir():
        return notes
    sec_id = origin.replace(".md.jinja", "").replace("/", "-")
    for path in sorted((law_map_dir / OBLIGATIONS_SUBDIR).rglob("*.yml")):
        if path.name.startswith("_"):
            continue
        data = _load_obligation_doc(path)
        if data is None:
            continue
        ob_id = data.get("id") or path.stem
        notes.extend(_obligation_notes(data, ob_id=ob_id, sec_id=sec_id,
                                       url=url, open_law_dir=open_law_dir))
    return notes


def _format_source_line(origin: str, url: str, status: str, *, flagged: bool) -> str:
    line = f"{origin}: {url} -> {status}"
    return f"{line}  <-- FLAGGED" if flagged else line


def _print_upstream_notes(origin: str, url: str) -> None:
    for note in check_upstream_project_status(origin, url):
        print(note)


def run_sources_check(
    sections_dir: Path = SECTIONS,
    probe: ProbeFn = probe_source,
) -> int:
    probed, flagged = check_sources(sections_dir, probe)
    for origin, url, status in flagged:
        print(_format_source_line(origin, url, status, flagged=True))
        _print_upstream_notes(origin, url)
    print_source_summary(probed, flagged_unique_count(flagged))
    return 1 if flagged else 0


def _report_review_dates_drift() -> None:
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


def _report_source_liveness() -> tuple[int, int]:
    print("\n[drift] source liveness (curl HEAD, GET fallback):")
    collected = collect_source_urls()
    statuses, probed = _probe_unique_urls(collected, probe_source)
    flagged_urls: set[str] = set()
    for origin, urls in collected.items():
        for url in urls:
            status = statuses[url]
            bad = is_flagged_status(status)
            if bad:
                flagged_urls.add(url)
            print(_format_source_line(origin, url, status, flagged=bad))
            if bad:
                _print_upstream_notes(origin, url)
    return probed, len(flagged_urls)


def drift_report() -> tuple[int, int]:
    _report_review_dates_drift()
    return _report_source_liveness()


def _validate_manifest_rows(manifest_rows: list) -> dict[str, dict]:
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
    return manifest_by_file


def _validate_section_file(
    path: Path,
    row: dict | None,
    seen_ids: set[str],
    *,
    drift_mode: bool,
) -> None:
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
    check_review_by(path, text, drift_mode=drift_mode)


def _validate_section_files(
    files: list[Path],
    manifest_by_file: dict[str, dict],
    *,
    drift_mode: bool,
) -> None:
    seen_ids: set[str] = set()
    for path in files:
        rel = path.relative_to(SECTIONS).as_posix()
        row = manifest_by_file.get(rel)
        if row is None:
            error(f"{path}: section file not listed in MANIFEST.yml")
        _validate_section_file(path, row, seen_ids, drift_mode=drift_mode)


def _print_validation_report(file_count: int) -> int:
    for msg in errors:
        print(f"error: {msg}", file=sys.stderr)
    for msg in warnings:
        print(f"warning: {msg}")
    if errors:
        print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    print(f"ok: {file_count} sections validate ({len(warnings)} warning(s))")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drift", action="store_true",
                        help="print due/expired review_by + probe declared source URLs; exit 0 always")
    parser.add_argument("--sources", action="store_true",
                        help="HEAD/GET-check declared sources: URLs (network access); "
                        "exit 1 when any URL is flagged (with --drift: single probe run, exit reflects sources)")
    args = parser.parse_args()

    manifest = load_manifest()
    manifest_rows = manifest.get("sections", []) if manifest else []
    manifest_by_file = _validate_manifest_rows(manifest_rows)

    files = section_files()
    _validate_section_files(files, manifest_by_file, drift_mode=args.drift)

    if args.drift:
        _, flagged = drift_report()
        if args.sources:
            return 1 if flagged else 0
        return 0
    if args.sources:
        return run_sources_check()
    return _print_validation_report(len(files))


if __name__ == "__main__":
    sys.exit(main())
