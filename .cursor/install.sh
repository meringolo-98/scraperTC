#!/usr/bin/env bash
set -euo pipefail

python3 -m pip install --user -e ".[dev]"

mkdir -p "$HOME/.local/bin"
for cmd in scrapertc cardhunt pytest ruff; do
  sudo ln -sfn "$HOME/.local/bin/$cmd" "/usr/local/bin/$cmd"
done
