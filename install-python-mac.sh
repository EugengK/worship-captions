#!/usr/bin/env bash
# Installs Python 3.12 for this user only, on a Mac whose own python3 is too old (e.g. Big Sur).
#
#   bash install-python-mac.sh
#
# Uses uv (https://docs.astral.sh/uv/), which puts Python inside the home folder: no administrator
# password is needed, and nothing outside ~/.local changes.
set -euo pipefail

UV="$HOME/.local/bin/uv"
if [ ! -x "$UV" ]; then
  echo "uv(파이썬 설치 도구)를 내 사용자 폴더에 설치합니다…"
  curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh
fi
[ -x "$UV" ] || { echo "uv 설치에 실패했습니다. 터미널 화면을 Claude에게 보내 주세요."; exit 1; }

echo "Python 3.12를 내 사용자 폴더에 설치합니다 (관리자 암호 필요 없음)…"
"$UV" python install 3.12
echo "설치 완료: $("$UV" python find 3.12)"
echo "이제 다시 실행하세요:  bash start-mac.sh player-demo"
