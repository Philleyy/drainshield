#!/bin/sh
# Builds the React site into server/static. Uses npm if it's installed; otherwise downloads Node.js
# as a Python package (the hosting server has Python but no Node). Run from the web/ folder.
set -e
if command -v npm >/dev/null 2>&1; then
  NPM="npm"
else
  python3 -m pip install --quiet --target /tmp/nodewheel "nodejs-wheel-binaries==22.20.0"
  export PATH="/tmp/nodewheel/nodejs_wheel/bin:$PATH"
  NPM="node /tmp/nodewheel/nodejs_wheel/lib/node_modules/npm/bin/npm-cli.js"
fi
cd frontend
$NPM install --no-audit --no-fund
$NPM run build
