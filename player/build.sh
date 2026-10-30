#!/usr/bin/env bash
# Rebuilds player/dist from source (developers only; the Mac just uses the committed dist/).
# Fetches IeumOffice at the pinned commit into player/.ieum, installs its packages, bundles.
set -euo pipefail
cd "$(dirname "$0")"
COMMIT="$(cat ../ieumoffice/UPSTREAM_COMMIT)"
if [ ! -d .ieum/.git ]; then
  git clone https://github.com/pblsketch/openoffice.git .ieum
fi
git -C .ieum fetch -q origin
git -C .ieum checkout -q -f "$COMMIT"
# Native/Electron downloads are not needed for the browser bundle
(cd .ieum && ELECTRON_SKIP_BINARY_DOWNLOAD=1 npm ci --ignore-scripts)
npm install --no-audit --no-fund
node build.mjs
