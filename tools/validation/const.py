"""Shared paths, vocabularies, patterns, and probe constants."""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

ProbeFn = Callable[[str], str]
RunnerFn = Callable[..., Any]

REPO = Path(__file__).resolve().parent.parent.parent
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
    "kanon-check/1.0"
    " (+https://github.com/politeuma/kanon)"
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

# Process-global validation message sinks (shared with report helpers and
# the legacy ``validate`` shim).
errors: list[str] = []
warnings: list[str] = []
