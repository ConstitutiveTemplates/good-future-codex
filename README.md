# good-future-codex

The canonical legal & ethical sections of the **Good-future charter** —
reviewed, versioned prose that consuming templates vendor into generated
`AGENTS.md` files. This repo owns *content only*: no template flags, no
gating logic, no enforcement. Consumers decide which sections apply.

## Layout

```
sections/<tier>/<slug>.md.jinja   one file per section; header comment + prose body
```

Header (per section, a jinja comment — the file is itself a jinja template):

```jinja
{# ethics: id=domain-scraping-law     # stable id: <tier>-<slug>, consumers key on it
   version=2026-09-24.1                # YYYY-MM-DD.rev of last content change
   status=active                       # draft | active | kind
   triggers=["sitemap", "robots.txt"]  # presence-scan keywords
   sources=["https://..."]             # primary citations the section rests on
#}
```

Freshness lives in the section body: the 制度変更ウォッチ heading carries
one or more `(review_by: YYYY-MM-DD)` dates the validator checks.

## Contract

- **Flag-agnostic.** Section bodies never reference a consumer's variable
  names (`scraping_effective`, `oj_code`, ...). Gating lives in the
  consumer's registry.
- **Reviewed, not live.** Consumers vendor a pinned SHA; a sync workflow
  diffs upstream and opens a PR. Nothing fetches this repo at render time.
- **Sources are load-bearing.** Every section's `why` names the real
  authority (statute, opinion, standard) it descends from.

Consumer: [python-copier-template](https://github.com/ConstitutiveTemplates/python-copier-template)
(vendors into `_shared/ethics/`; see its `docs/explanations/ethics-external.md`).

## Placement & conditions (MANIFEST.yml)

`sections/MANIFEST.yml` is the distribution contract: every section declares
**where** it wants to land (`placement`: `agents_md` / `charter` /
`legal_md` / `standalone`) and **under what abstract condition** (`when`:
`always` / `scraping` / `oj_code` / `mcp` / `data_science` / `web_api` /
`commercial` / `eu_market` / `jp` / `ai_assisted`).

The `when` vocabulary is deliberately abstract — the codex never names a
consumer's flag. A consumer maps each abstract condition to its own gating
(this template's `REGISTRY.yml` maps `scraping` → `scraping_effective`,
`oj_code` → `oj_code`, ...). The codex owns the *intent*; the consumer owns
the *wiring*.

## Validation

`tools/validate.py` (stdlib + PyYAML, run via `uv run --with pyyaml`)
enforces the corpus contract on every commit:

```bash
just check    # or: uv run --with pyyaml python tools/validate.py
just drift    # report due/expired review_by + probe source URLs (exit 0)
```

Checks: every `sections/<tier>/<slug>.md.jinja` appears in MANIFEST and
vice versa; the `{# ethics: ... #}` header carries `id` (must equal both the
MANIFEST id and the `<tier>-<slug>` path name), `version`, `status`
(`draft|active|kind`), non-empty `triggers`, and may carry `sources=[...]`;
MANIFEST `when`/`placement` stay within the documented vocabulary; bodies
stay flag-agnostic (no `{{`/`{%` after the header); every section keeps the
required headings and at least one `(review_by: YYYY-MM-DD)` date in
制度変更ウォッチ — expired dates are errors, due-within-30-days warnings.

A weekly `drift-watch` workflow opens/updates a `codex-drift` issue when a
review_by comes due or a declared source URL stops answering, and closes it
when the report is clean.
