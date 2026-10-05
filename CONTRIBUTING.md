# Contributing to good-future-codex

This repo owns the *content layer* of the ethics/legal stack: reviewed,
versioned prose sections that consumers vendor into generated projects. The
consumer template (daimonion) does **not** accept section changes — new
sections and corrections to section prose or sources are proposed here.

Issues and PRs in English are welcome. The sections themselves are written
in Japanese prose, as the existing ones are.

## What the corpus enforces

Read these before proposing anything:

- `sections/_template.md.jinja` — the authoring aid: header fields, section
  structure, the fixed 制度変更ウォッチ block and the trailing not-legal-advice
  comment.
- `sections/MANIFEST.yml` — the distribution contract: every section's
  `placement` and abstract `when` condition, from a documented vocabulary.
- `sections/baseline/pki-chain.md.jinja` — a worked example (header, 要約,
  bad/good pairs, review_by dates).
- `tools/validate.py` — what actually gets checked (run it locally; see
  below).

`just check` fails on: a section file missing from MANIFEST or vice versa;
a header whose `id` differs from the MANIFEST id or from the `<tier>-<slug>`
path name; a missing or malformed `version` (`YYYY-MM-DD.rev`), missing
`status`, or non-empty `triggers`; a MANIFEST `when`/`placement` outside the
documented vocabulary; jinja expressions (`{{`/`{%`) anywhere in the body
after the header; a missing or out-of-order required heading; and a missing
`(review_by: YYYY-MM-DD)` date in 制度変更ウォッチ. Expired `review_by` dates
are errors; dates due within 30 days are warnings. There are no other
checks — describe nothing beyond what the validator enforces.

## Proposing a new section

1. Copy `sections/_template.md.jinja` into the matching tier directory —
   `sections/baseline/`, `domain/`, `region/`, `sector/`, or `lang/` — as
   `sections/<tier>/<slug>.md.jinja`.
2. Fill the `{# ethics: ... #}` header: `id=<tier>-<slug>` (must match both
   the MANIFEST id and the path name), `version=YYYY-MM-DD.rev`,
   `status=draft` (new sections start as `draft`; promote to `active` only
   after review), non-empty `triggers=[...]` keywords, and
   `sources=[...]` primary citations.
3. Add a row to `sections/MANIFEST.yml` with `placement` (`agents_md` /
   `charter` / `legal_md` / `standalone`) and `when` from the documented
   vocabulary (`always` / `scraping` / `oj_code` / `mcp` / `data_science` /
   `web_api` / `commercial` / `eu_market` / `jp` / `ai_assisted`).
4. Write the body flag-agnostically: never name a consumer's variable or
   flag; keep code/config snippets free of `{{ }}` / `{% %}`. Cite the
   primary source as a one-line summary plus link — never paste statutes or
   articles verbatim.
5. Keep the required headings in order (## 事実 / ## 禁止パターン /
   ## 推奨設定 / ## 運用チェック / ## 制度変更ウォッチ) and leave at least
   one `(review_by: YYYY-MM-DD)` date under 制度変更ウォッチ, far enough out
   that `just check` does not warn.
6. Leave the trailing not-legal-advice comment in place if the section
   touches 法域・業法 (the template's comment marks this).

## Correcting a source or a fact

Fix the prose and/or `sources=[...]`, then bump the header `version` to
`YYYY-MM-DD.rev` (e.g. `2026-10-06.2`). The version is the record of the
last content change; consumers' sync PRs diff on it. Never edit a
`review_by` date merely to silence the validator — that is the drift-watch's
signal that the section needs a real re-check.

## Running the checks

```bash
just check    # or: uv run --with pyyaml python tools/validate.py
just drift    # or: uv run --with pyyaml python tools/validate.py --drift
```

`just check` exits non-zero on any error. `just drift` reports
due/expired `review_by` dates and probes declared source URLs (curl HEAD);
it always exits 0.

## What happens downstream

Consumers vendor this repo's sections pinned to a SHA (daimonion vendors
into `_shared/ethics/`, pinned by `.ethics-vendored`). Their sync workflow
diffs the pinned SHA against upstream and opens a sync PR for the
maintainer; nothing fetches this repo at render time. So a merged change
here reaches generated projects only after a consumer's sync PR lands.