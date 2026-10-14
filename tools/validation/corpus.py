"""Corpus validators: MANIFEST rows, section headers, bodies, review dates."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import yaml

from .const import (
    ETHICS_HEADER_RE,
    HEADER_ID_RE,
    HEADER_SOURCES_RE,
    HEADER_STATUS_RE,
    HEADER_TRIGGERS_RE,
    HEADER_VERSION_RE,
    JINJA_RE,
    MANIFEST,
    PLACEMENT_VOCAB,
    REQUIRED_HEADINGS,
    REVIEW_BY_RE,
    REVIEW_HORIZON,
    SECTION_GLOB,
    SECTIONS,
    STATUS_VOCAB,
    WHEN_VOCAB,
)
from .report import error, warn


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
    """region/eu-cra.md -> region-eu-cra (tier-slug naming rule)."""
    return f"{path.parent.name}-{path.name.removesuffix('.md')}"


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


def _validate_manifest_rows(manifest_rows: list) -> dict[str, dict]:
    manifest_by_file: dict[str, dict] = {}
    seen_ids: set[str] = set()
    for row in manifest_rows:
        if not isinstance(row, dict):
            error(f"MANIFEST.yml: section row {row!r} is not a mapping")
            continue
        sid = row.get("id")
        if not isinstance(sid, str) or not sid:
            error(f"MANIFEST.yml: section row {row!r} has no string id")
            continue
        if sid in seen_ids:
            error(f"MANIFEST.yml: duplicate section id {sid!r}")
        seen_ids.add(sid)
        when = row.get("when")
        when_items = when if isinstance(when, list) else [when]
        bad = [w for w in when_items if w not in WHEN_VOCAB]
        if bad:
            error(f"MANIFEST.yml: section {sid!r}: when {bad!r} not in {sorted(WHEN_VOCAB)}")
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


def validate_section_files(
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


def validate_corpus(*, drift_mode: bool = False) -> tuple[dict[str, dict], list[Path]]:
    """Run MANIFEST + section-file validation; return lookup data for callers."""
    manifest = load_manifest()
    manifest_rows = manifest.get("sections", []) if manifest else []
    manifest_by_file = _validate_manifest_rows(manifest_rows)
    files = section_files()
    validate_section_files(files, manifest_by_file, drift_mode=drift_mode)
    return manifest_by_file, files


# Back-compat alias for the pre-split private name.
_validate_section_files = validate_section_files
