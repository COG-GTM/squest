#!/usr/bin/env bash
# Render the architecture diagram. Needs Graphviz (`apt-get install graphviz fonts-dejavu`).
set -euo pipefail
cd "$(dirname "$0")"
dot -Tpng -Gdpi=110 architecture.dot -o ../images/architecture.png
dot -Tsvg architecture.dot -o ../images/architecture.svg
