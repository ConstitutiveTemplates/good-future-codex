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
