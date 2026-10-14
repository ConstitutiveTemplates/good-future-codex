"""Declared-source URL collection: MANIFEST rows, section files, YAML data files."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlparse

import yaml

from .const import (
    ETHICS_HEADER_RE,
    HEADER_SOURCES_RE,
    SECTIONS,
    SECTION_GLOB,
    URL_RE,
)


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
    """URLs declared by one .md section: header sources + body links."""
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
    ``sections/*/*.md`` (header ``sources=[...]`` + body links),
    and sibling YAML data files (any ``sources:`` list, e.g.
    ``lang/copyright-terms.yml``). Reads files only; never touches
    the network.
    """
    collected: dict[str, set[str]] = {}
    _manifest_source_urls(sections_dir, collected)
    _section_file_source_urls(sections_dir, collected)
    _yaml_data_source_urls(sections_dir, collected)
    return {origin: sorted(urls) for origin, urls in sorted(collected.items())}
