#!/usr/bin/env bash
# Installs Python 3.13 from python.org on a Mac whose own python3 is too old (e.g. Big Sur).
#
#   bash install-python-mac.sh
#
# Finds the newest 3.13.x macOS installer on python.org, downloads it, installs it (asks for the
# Mac's login password once), then installs the security certificates Python needs for HTTPS.
set -euo pipefail

SERIES="3.13"
BASE="https://www.python.org/ftp/python"

echo "python.org에서 Python ${SERIES} 최신 설치 파일을 찾는 중…"
VERSIONS="$(curl -fsSL "$BASE/" | grep -oE "href=\"${SERIES//./\\.}\.[0-9]+/\"" | grep -oE "${SERIES//./\\.}\.[0-9]+" | sort -t. -k3 -n -r | uniq)"
PKG_URL=""
for v in $VERSIONS; do
  url="$BASE/$v/python-$v-macos11.pkg"
  if curl -fsIL -o /dev/null "$url"; then
    PKG_URL="$url"
    VERSION="$v"
    break
  fi
done
if [ -z "$PKG_URL" ]; then
  echo "설치 파일을 찾지 못했습니다. https://www.python.org/downloads/macos/ 에서 직접 받아 설치해 주세요."
  exit 1
fi

PKG="$(mktemp -d)/python-$VERSION.pkg"
echo "Python $VERSION 내려받는 중… ($PKG_URL)"
curl -fL --progress-bar -o "$PKG" "$PKG_URL"

echo "설치합니다. 맥 로그인 암호를 물으면 입력하세요 (입력해도 화면에 보이지 않습니다)."
sudo installer -pkg "$PKG" -target /
rm -f "$PKG"

# python.org's Python brings its own OpenSSL and needs this step for HTTPS (Google) to work
CERTS="/Applications/Python $SERIES/Install Certificates.command"
if [ -f "$CERTS" ]; then
  echo "인터넷 보안 인증서를 설치합니다…"
  bash "$CERTS" >/dev/null
fi

PY="/Library/Frameworks/Python.framework/Versions/$SERIES/bin/python3"
echo "설치 완료: $("$PY" --version)"
echo "이제 다시 실행하세요:  bash start-mac.sh player-demo"
