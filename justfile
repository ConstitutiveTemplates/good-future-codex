# good-future-codex development tasks

check:
    uv run --with pyyaml python tools/validate.py
    uv run --with pytest --with pyyaml python -m pytest -q

test:
    uv run --with pytest --with pyyaml python -m pytest -q

drift:
    uv run --with pyyaml python tools/validate.py --drift

sources:
    uv run --with pyyaml python tools/validate.py --sources
