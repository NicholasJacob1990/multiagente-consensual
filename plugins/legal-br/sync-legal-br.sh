#!/usr/bin/env bash
# Registra este checkout pelo instalador nativo do Claude; não copia sessões.
set -euo pipefail
PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
claude plugin marketplace add "$PLUGIN_DIR"
claude plugin install legal-br@legal-br-plugins
