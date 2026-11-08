#!/bin/sh
# Build a source archive of DevSentry. The archive is not a git clone and does
# not include virtual environments, caches, or the Hermes checkout.
set -eu
cd "$(dirname "$0")/.."
rm -rf devsentry/__pycache__ tests/__pycache__ fixtures/sample-project/__pycache__ .pytest_cache
mkdir -p artifacts
archive="artifacts/devsentry-0.1.0-source.tar.gz"
tar \
  --exclude-vcs \
  --exclude "./artifacts" \
  --exclude "./.venv" \
  --exclude "./dist" \
  --exclude "./.pytest_cache" \
  --exclude "./.mypy_cache" \
  --exclude "devsentry/__pycache__" \
  --exclude "tests/__pycache__" \
  --exclude "fixtures/sample-project/__pycache__" \
  --exclude "*.pyc" \
  --exclude "*.pyo" \
  --exclude "./.hermes" \
  --exclude "./agent-tools" \
  --exclude "./uploads" \
  -czf "$archive" \
  LICENSE \
  README.md \
  pyproject.toml \
  devsentry \
  docs \
  fixtures \
  samples \
  scripts \
  tests
echo "wrote $archive"
