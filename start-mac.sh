#!/usr/bin/env bash
# 맥에서 실시간 번역 자막을 시험하는 시작 스크립트.
#
#   bash start-mac.sh demo              # 1단계: 데모 자막만 (인터넷·API 비용 없음)
#   bash start-mac.sh file 녹음.wav     # 2단계: 녹음 파일로 실제 번역 시험
#   bash start-mac.sh                   # 3단계: 마이크로 실시간 번역 (영어+태국어)
#   LANGS=en,th,zh bash start-mac.sh    # 자막 언어 바꾸기
#   NOTES="창세기 12:1-9. 이 본문에서는 아브람(Abram)" bash start-mac.sh   # 오늘 본문 메모
#
# 처음 실행할 때 필요한 프로그램을 설치하고 Gemini API 키를 한 번 묻습니다.
# 키는 이 폴더의 .env 파일에만 저장되며 GitHub에는 올라가지 않습니다(.gitignore).
# 끝낼 때는 이 터미널 창에서 Control + C.
set -euo pipefail
cd "$(dirname "$0")"

MODE="${1:-live}"
LANGS="${LANGS:-en,th}"
NOTES="${NOTES:-}"

if ! command -v python3 >/dev/null; then
  echo "python3가 없습니다. 터미널에서 'xcode-select --install'을 실행해 설치한 뒤 다시 실행하세요."
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "처음 실행: 필요한 프로그램을 설치합니다 (1~3분)…"
  python3 -m venv .venv
  .venv/bin/python -m pip install -q --upgrade pip
  .venv/bin/python -m pip install -q -r hub/requirements.txt
fi

if [ "$MODE" != "demo" ]; then
  if [ ! -f .env ]; then
    read -rsp "Gemini API 키를 붙여넣고 Enter를 누르세요 (화면에 보이지 않습니다): " KEY; echo
    printf 'GEMINI_API_KEY=%s\n' "$KEY" > .env
    chmod 600 .env
  fi
  set -a; . ./.env; set +a
fi

HUB_ARGS=()
[ "$MODE" = "demo" ] && HUB_ARGS+=(--demo)
.venv/bin/python hub/caption_hub.py "${HUB_ARGS[@]+"${HUB_ARGS[@]}"}" &
HUB_PID=$!
trap 'kill $HUB_PID 2>/dev/null' EXIT
sleep 1

# 자막 화면을 기본 브라우저로 엽니다. 프로젝터 쪽으로 옮긴 뒤 Control+Command+F로 전체 화면.
command -v open >/dev/null && open web/captions.html

case "$MODE" in
  demo)
    echo "데모 자막이 브라우저 아래쪽에 4초마다 나옵니다. 끝내려면 Control + C."
    wait "$HUB_PID"
    ;;
  file)
    [ -n "${2:-}" ] || { echo "사용법: bash start-mac.sh file 녹음파일.wav"; exit 1; }
    .venv/bin/python hub/live_engine.py --file "$2" --langs "$LANGS" --notes "$NOTES"
    echo "녹음 파일 번역이 끝났습니다. 기록: hub/logs/"
    ;;
  live)
    echo "마이크로 듣는 중입니다. 맥의 '시스템 설정 > 사운드 > 입력'에서 핀마이크 수신기를 고르세요."
    echo "처음에는 터미널의 마이크 사용 허용 창이 뜰 수 있습니다 → 허용."
    .venv/bin/python hub/live_engine.py --langs "$LANGS" --notes "$NOTES"
    ;;
  *)
    echo "알 수 없는 모드: $MODE (demo | file | live)"; exit 1
    ;;
esac
