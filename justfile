# good-future-codex development tasks

check:
    uv run --with pyyaml python tools/validate.py

drift:
    uv run --with pyyaml python tools/validate.py --drift
