#!/bin/bash
cd "$(dirname "$0")"

if [ ! -x ./venv/bin/python ]; then
    echo "error: venv not found (./venv/bin/python missing)." >&2
    echo "Set it up first:" >&2
    echo "  python3 -m venv venv" >&2
    echo "  ./venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi

if ! ./venv/bin/python -c "import textual" 2>/dev/null; then
    echo "error: dependencies not installed in ./venv." >&2
    echo "Run:" >&2
    echo "  ./venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi

exec ./venv/bin/python app.py "$@"
