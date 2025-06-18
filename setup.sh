#!/bin/bash
# setup.sh
set -e

echo "▶️  Install Python dependencies with poetry..."
poetry install

echo "▶️  Run virtual environment..."
source ./.venv/bin/activate

echo "▶️  run post-install-skript aus..."
# Rufe hier dein Bash-Skript auf
./cfg/patch-doorstop

echo "✅  Setup completed!"