#!/usr/bin/env python3
"""Validate the kanon sections corpus.

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

Implementation lives in :mod:`validation` (split by responsibility);
this module keeps the historical ``python tools/validate.py`` entry point
and the ``import validate`` attribute surface working.
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

from validation.cli import main, print_validation_report
from validation.const import (
    CURL_STATUS_RE,
    ETHICS_HEADER_RE,
    FLAGGED_STATUS_PREFIXES,
    HEADER_ID_RE,
    HEADER_SOURCES_RE,
    HEADER_STATUS_RE,
    HEADER_TRIGGERS_RE,
    HEADER_VERSION_RE,
    HEAD_FALLBACK_CODES,
    JINJA_RE,
    MANIFEST,
    NO_HTTP_STATUS_MARKER,
    OBLIGATIONS_SUBDIR,
    OPEN_LAW_SOURCES_SUBDIR,
    PLACEMENT_VOCAB,
    REDIRECT_STATUS_PREFIX,
    REPO,
    REQUIRED_HEADINGS,
    REVIEW_BY_RE,
    REVIEW_HORIZON,
    SECTIONS,
    SECTION_GLOB,
    SOURCE_RETRIES,
    SOURCE_TIMEOUT,
    SOURCE_USER_AGENT,
    STATUS_VOCAB,
    UNAVAILABLE_MARKER,
    URL_RE,
    WHEN_VOCAB,
    ProbeFn,
    RunnerFn,
    SourceFlag,
    errors,
    warnings,
)
from validation.corpus import (
    check_flag_agnostic,
    check_headings,
    check_review_by,
    expected_id,
    load_manifest,
    parse_header,
    section_files,
    validate_corpus,
    validate_section_files,
)
from validation.liveness import (
    check_sources,
    drift_report,
    flagged_unique_count,
    format_source_summary,
    is_flagged_status,
    print_source_summary,
    run_sources_check,
)
from validation.probe import curl_args, parse_curl_status, probe_source
from validation.report import error, reset, warn
from validation.sources import (
    collect_source_urls,
    extract_section_urls,
    extract_yaml_sources,
    strip_url_punct,
)
from validation.upstream import check_upstream_project_status

__all__ = [
    "CURL_STATUS_RE",
    "ETHICS_HEADER_RE",
    "FLAGGED_STATUS_PREFIXES",
    "HEADER_ID_RE",
    "HEADER_SOURCES_RE",
    "HEADER_STATUS_RE",
    "HEADER_TRIGGERS_RE",
    "HEADER_VERSION_RE",
    "HEAD_FALLBACK_CODES",
    "JINJA_RE",
    "MANIFEST",
    "NO_HTTP_STATUS_MARKER",
    "OBLIGATIONS_SUBDIR",
    "OPEN_LAW_SOURCES_SUBDIR",
    "PLACEMENT_VOCAB",
    "REDIRECT_STATUS_PREFIX",
    "REPO",
    "REQUIRED_HEADINGS",
    "REVIEW_BY_RE",
    "REVIEW_HORIZON",
    "SECTIONS",
    "SECTION_GLOB",
    "SOURCE_RETRIES",
    "SOURCE_TIMEOUT",
    "SOURCE_USER_AGENT",
    "STATUS_VOCAB",
    "UNAVAILABLE_MARKER",
    "URL_RE",
    "WHEN_VOCAB",
    "ProbeFn",
    "RunnerFn",
    "SourceFlag",
    "errors",
    "warnings",
    "check_flag_agnostic",
    "check_headings",
    "check_review_by",
    "check_sources",
    "check_upstream_project_status",
    "collect_source_urls",
    "curl_args",
    "drift_report",
    "error",
    "expected_id",
    "extract_section_urls",
    "extract_yaml_sources",
    "flagged_unique_count",
    "format_source_summary",
    "is_flagged_status",
    "load_manifest",
    "main",
    "parse_curl_status",
    "parse_header",
    "print_source_summary",
    "print_validation_report",
    "probe_source",
    "reset",
    "run_sources_check",
    "section_files",
    "strip_url_punct",
    "validate_corpus",
    "validate_section_files",
    "warn",
]

# Back-compat: the pre-split module exposed these private helpers, so keep
# them importable (without advertising them in __all__).
from validation.corpus import (  # noqa: E402
    _validate_manifest_rows,
    _validate_section_file,
    _validate_section_files,
)
from validation.liveness import (  # noqa: E402
    _format_source_line,
    _is_flagged_with_grounding,
    _print_upstream_notes,
    _probe_unique_urls,
    _report_review_dates_drift,
    _report_source_liveness,
)
from validation.probe import _run_curl  # noqa: E402
from validation.sources import (  # noqa: E402
    _add_source_urls,
    _collect_yaml_source_urls,
    _manifest_source_urls,
    _section_file_source_urls,
    _split_header_body,
    _yaml_data_source_urls,
)
from validation.upstream import (  # noqa: E402
    _load_obligation_doc,
    _obligation_notes,
    _open_law_note,
)

# Back-compat: the old module printed via a private `_print_validation_report`.
_print_validation_report = print_validation_report


if __name__ == "__main__":
    sys.exit(main())
