# good-future-codex

The canonical legal & ethical sections of the **Good-future charter** —
reviewed, versioned prose that consuming templates vendor into generated
`AGENTS.md` files. This repo owns *content only*: no template flags, no
gating logic, no enforcement. Consumers decide which sections apply.

## Layout

```
sections/<class>/<id>.md.jinja   one file per section; frontmatter + prose body
```

Frontmatter (per section):

```yaml
---
id: domain-scraping-law        # stable identifier consumers key on
audience: scraping             # who the section is for (free-form)
review_by: 2026-12-18          # next scheduled review
sources:                       # the citations the section rests on
  - https://...
---
```

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
