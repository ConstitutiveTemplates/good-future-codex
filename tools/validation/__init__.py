"""Section-corpus validation, split by responsibility.

- :mod:`validation.const` — paths, vocabularies, patterns, probe constants
- :mod:`validation.report` — shared error/warning sinks
- :mod:`validation.corpus` — MANIFEST / header / body / review_by checks
- :mod:`validation.sources` — declared-URL collection (offline)
- :mod:`validation.probe` — curl HEAD/GET probing (network)
- :mod:`validation.upstream` — law-map / open-law grounding lookup
- :mod:`validation.liveness` — probe orchestration, flagging, drift output
- :mod:`validation.cli` — argparse entry point
"""
