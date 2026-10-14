# kanon

The canonical legal & ethical sections of the **Good-future charter** —
reviewed, versioned prose that consuming templates vendor into generated
`AGENTS.md` files. *kanon*: κανών, the measuring rod — the origin of
*canon*. This repo owns *content only*: no template flags, no
gating logic, no enforcement. Consumers decide which sections apply.

## Layout

```
sections/<tier>/<slug>.md   one file per section: YAML front matter + Markdown body
sections/VOCABULARY.yml     the when / placement / status vocabulary (hand-maintained)
sections/MANIFEST.yml       GENERATED index of every section (tools/manifest.py)
sections/_template.md       authoring aid; copy it to start a section
sections/lang/*.yml         structured data a section relies on
```

Sections are plain Markdown. Nothing in them is templated; wrapping a
section in Jinja (or anything else) is the consumer's job.

### Front matter

Every section's metadata lives in its YAML front matter — nowhere else:

```yaml
---
id: domain-scraping-law            # stable id: <tier>-<slug>; consumers key on it
version: "2026-09-24.1"            # YYYY-MM-DD.rev of the last content change
status: active                     # draft | active
placement: agents_md               # where it wants to land
when: scraping                     # abstract condition, or a list ("any of these")
obligations:                       # law-map obligation ids the section serves
  - obligation.copyright.ai-training-data-use
triggers:
  keywords: ["sitemap", "robots.txt"]       # presence-scan keywords
  pattern: '(?i)\b(sitemap|robotparser)\b'  # code / diff trigger regex
  config: '(?i)\b(allowed_domains)\b'       # optional config-file trigger regex
sources:                           # primary citations the section rests on
  - https://www.rfc-editor.org/rfc/rfc9309.html
license: CC-BY-4.0
en:                                # concise English rendering
  title: "Scraping legality — ..."
  summary: ["...", "..."]          # the 要約 rules
  prohibited: ["...", "..."]       # the 禁止パターン lines
---
# スクレイピングの適法性 — ...
```

The Japanese body is canonical for now; `en:` carries the summary and the
prohibited patterns in English so an English-language consumer can render
those without the Japanese prose.

`sections/MANIFEST.yml` is a build artifact: `just manifest` derives it from
the front matter and `VOCABULARY.yml`, and `just check` (and CI) fail when the
committed copy is stale. Never edit it by hand.

### Freshness

Each section names the law-map obligations it serves in `obligations:`;
[law-map](https://github.com/politeuma/law-map) owns the freshness of those
obligations' groundings (review dates, source liveness). `(review_by:
YYYY-MM-DD)` dates in a section's 制度変更ウォッチ are still checked when
present — an expired one is an error — and are required only for a section
with no obligations.

## Contract

- **Consumer-agnostic.** Section bodies never reference a consumer's
  files, flags or variable names (`scraping_effective`, `REGISTRY.yml`,
  ...); the validator rejects them. Gating lives in the consumer.
- **Reviewed, not live.** Consumers vendor a pinned SHA; a sync workflow
  diffs upstream and opens a PR. Nothing fetches this repo at render time.
- **Sources are load-bearing.** Every section's `sources:` name the real
  authority (statute, opinion, standard) it descends from.

Consumers:
- [architekton-py](https://github.com/politeuma/architekton-py) — the
  consumer template; vendors this repo's sections
  into `_shared/ethics/` pinned by `.ethics-vendored`, and opens a sync PR
  when drift is detected (see its `docs/explanations/ethics-external.md`).
- [law-map](https://github.com/politeuma/law-map) — the
  obligation graph; its obligations link sections here via
  `related_sections` ids (`<tier>-<slug>`), and each section names the
  same obligations back in `obligations:` (`just check` warns on a
  mismatch when a law-map checkout sits next to this repo).
- [daimonion](https://github.com/politeuma/daimonion) — the
  ethics linter; bundles this repo's snapshot inside
  its wheel and renders the matching sections into any project's
  `AGENTS.md`, whatever template it came from.

## Placement & conditions

Every section declares **where** it wants to land (`placement`) and
**under what abstract condition** (`when`, a condition or a list meaning
"any of these"). The vocabulary is deliberately abstract — kanon never
names a consumer's flag. A consumer maps each condition to its own gating:
kanon owns the *intent*; the consumer owns the *wiring*.

Core conditions sit on three axes — distribution form, data handled, and
market. Niche conditions live in **extension packs**; a consumer that does
not opt into a pack can ignore its conditions, and MANIFEST marks each
section with the `pack` it belongs to (`core` unless it is gated only on
one pack's conditions). The table below is generated from MANIFEST:

<!-- BEGIN GENERATED: when-vocabulary (tools/manifest.py from sections/MANIFEST.yml) -->
| Group | Condition | Meaning | Sections |
| --- | --- | --- | --- |
| Unconditional | `always` | every project that renders the sections | 3 |
| Unconditional | `ai_assisted` | AI coding agents work in the repository | 0 |
| axis: Distribution form | `library` | a library / API package | 1 |
| axis: Distribution form | `cli` | a command-line / terminal tool | 3 |
| axis: Distribution form | `web_api` | an HTTP API or web service | 2 |
| axis: Distribution form | `mcp` | an MCP server or tool-calling agent code | 2 |
| axis: Data handled | `personal_data` | processes personal data | 1 |
| axis: Data handled | `face_recognition` | performs biometric identification or verification | 2 |
| axis: Data handled | `medtech` | medical / SaMD software (clinical decisions or patient data) | 2 |
| axis: Data handled | `scraping` | fetches third-party web content | 1 |
| axis: Data handled | `data_science` | trains or evaluates models on datasets | 2 |
| axis: Market | `commercial` | distributed commercially | 1 |
| axis: Market | `eu_market` | offered on the EU market | 1 |
| axis: Market | `jp` | offered in Japan / operates under Japanese law | 2 |
| extension pack `competitive-programming` | `oj_code` | code submitted to an online judge | 1 |
| extension pack `competitive-programming` | `kaggle` | a data-competition (Kaggle-style) workspace | 1 |
| extension pack `embedded` | `embedded` | embedded / microcontroller firmware | 1 |

`placement`: `agents_md` (the AGENTS.md ethics appendix) / `charter` (a CHARTER.md, for scraping projects) / `legal_md` (a LEGAL.md checklist) / `standalone` (its own file).

`status`: `draft` (written but not yet reviewed; consumers should not render it) / `active` (reviewed; consumers render it when `when` matches).
<!-- END GENERATED: when-vocabulary -->

## Validation

`tools/validate.py` (stdlib + PyYAML, run via `uv run --with pyyaml`)
enforces the corpus contract on every commit:

```bash
just check     # validate + tests
just manifest  # regenerate sections/MANIFEST.yml and the vocabulary tables
just drift     # report due/expired review_by + probe source URLs (exit 0)
just sources   # probe only declared sources URLs (exit 1 when any is flagged)
```

Checks: every `sections/<tier>/<slug>.md` opens with front matter carrying
exactly the keys above; `id` equals the `<tier>-<slug>` path name;
`version` is `YYYY-MM-DD.rev`; `status`, `placement` and `when` stay within
`VOCABULARY.yml`; trigger regexes compile; `license` is `CC-BY-4.0`; `en`
has a title and non-empty `summary` / `prohibited` lists. Bodies stay
consumer-agnostic — no `{{`/`{%`, and no banned phrases (consumer file and
flag names, `配布:` / `Triggers:` lines that belong in front matter,
retired project names). Every section keeps the required headings;
present `review_by` dates must not be expired (due within 30 days warns).
MANIFEST and the generated vocabulary tables must match `tools/manifest.py`.

## Contributing

New sections and corrections to section prose or sources belong here, in
kanon — not in the consumer template. See
[CONTRIBUTING.md](CONTRIBUTING.md) for how to propose a section or fix a
source. Obligation-level changes (which laws ground which behaviors) go
through
[law-map's Legal RFC issue template](https://github.com/politeuma/law-map/issues/new?template=legal_rfc.yml);
template/rendering problems go to
[architekton-py](https://github.com/politeuma/architekton-py).

**Not legal advice.** Sections record what statutes, opinions, and standards
say, with one-line summaries and links to the primary source; they do not
interpret the law for a specific project or situation. For an actual
compliance determination, consult a qualified practitioner.
