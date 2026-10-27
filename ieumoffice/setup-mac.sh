#!/usr/bin/env bash
# Builds IeumOffice with the worship caption band on this Mac.
#
#   bash setup-mac.sh            # first time: clone, patch, install, build, run
#   bash setup-mac.sh --run      # later: just run the patched app
#
# Needs: Node 22.12+ (https://nodejs.org), git, and Rust (https://rustup.rs) for the
# spreadsheet engine that IeumOffice builds. The patched copy lives in ~/ieumoffice-worship.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DIR="$HOME/ieumoffice-worship"
COMMIT="$(cat "$HERE/UPSTREAM_COMMIT")"

if [[ "${1:-}" == "--run" ]]; then
  cd "$DIR" && exec npx electron apps/shell
fi

command -v node >/dev/null || { echo "Node.js가 없습니다: https://nodejs.org 에서 22 버전 이상을 설치하세요."; exit 1; }
command -v cargo >/dev/null || { echo "Rust가 없습니다: https://rustup.rs 의 한 줄 설치 명령을 먼저 실행하세요."; exit 1; }

if [[ ! -d "$DIR/.git" ]]; then
  git clone https://github.com/pblsketch/openoffice.git "$DIR"
fi
cd "$DIR"
git fetch origin
git checkout -f "$COMMIT"
git clean -fd apps/slides/src/renderer/components
git apply "$HERE/worship-captions.patch"
echo "자막 패치 적용 완료 (원본 커밋 ${COMMIT:0:7})"

npm install
npm run build:all
echo "빌드 완료. 앱을 실행합니다."
exec npx electron apps/shell
