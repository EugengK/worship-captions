#!/usr/bin/env bash
# 맥에서 실시간 번역 자막을 시험하는 시작 스크립트.
#
#   bash start-mac.sh worship           # ★ 예배: 예배 발표기 + 마이크 실시간 번역
#   bash start-mac.sh player-demo       # 예배 발표기 + 데모 자막 (인터넷·API 비용 없음)
#   bash start-mac.sh demo              # 1단계: 데모 자막만 (인터넷·API 비용 없음)
#   bash start-mac.sh file 녹음.wav     # 2단계: 녹음 파일로 실제 번역 시험
#   bash start-mac.sh                   # 3단계: 마이크로 실시간 번역 (영어+태국어)
#   LANGS=en,th,zh bash start-mac.sh    # 자막 언어 바꾸기
#   NOTES="창세기 12:1-9. 이 본문에서는 아브람(Abram)" bash start-mac.sh   # 오늘 본문 메모
#   bash start-mac.sh reset-key         # 저장된 API 키를 지우고 다시 입력
#
# 처음 실행할 때 필요한 프로그램을 설치하고 Gemini API 키를 한 번 묻습니다.
# 키는 이 폴더의 .env 파일에만 저장되며 GitHub에는 올라가지 않습니다(.gitignore).
# 끝낼 때는 이 터미널 창에서 Control + C.
set -euo pipefail
cd "$(dirname "$0")"

MODE="${1:-live}"

if [ "$MODE" = "reset-key" ]; then
  rm -f .env
  echo "저장된 키를 지웠습니다. 다음 실행 때 키를 다시 묻습니다."
  exit 0
fi

# Asks Google whether a key works (prints only the HTTP status, never the key).
key_ok() {
  [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 \
        -H "x-goog-api-key: $1" 'https://generativelanguage.googleapis.com/v1beta/models?pageSize=1')" = "200" ]
}
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

if [ "$MODE" != "demo" ] && [ "$MODE" != "player-demo" ]; then
  if [ -f .env ]; then
    set -a; . ./.env; set +a
    if ! key_ok "${GEMINI_API_KEY:-}"; then
      echo "저장된 Gemini 키가 거절되었습니다. 키를 다시 입력해 주세요."
      rm -f .env
    fi
  fi
  tries=0
  while [ ! -f .env ]; do
    tries=$((tries + 1))
    [ "$tries" -gt 3 ] && { echo "키 확인에 3번 실패했습니다. AI Studio에서 키를 새로 복사해 다시 실행하세요."; exit 1; }
    read -rsp "Gemini API 키를 붙여넣고 Enter를 누르세요 (화면에 보이지 않습니다): " KEY; echo
    # 붙여넣을 때 딸려 온 공백·줄바꿈·따옴표, "GEMINI_API_KEY=" 앞부분을 지웁니다.
    KEY="$(printf '%s' "$KEY" | tr -d '[:space:]"'"'"'' | sed 's/^GEMINI_API_KEY=//')"
    if key_ok "$KEY"; then
      printf 'GEMINI_API_KEY=%s\n' "$KEY" > .env
      chmod 600 .env
      echo "키 확인 완료. 저장했습니다."
    else
      echo "Google이 이 키를 거절했습니다. AI Studio(https://aistudio.google.com/apikey)에서 키 전체를 다시 복사해 붙여넣으세요."
    fi
  done
  set -a; . ./.env; set +a
fi

HUB_ARGS=()
case "$MODE" in demo|player-demo) HUB_ARGS+=(--demo) ;; esac
.venv/bin/python hub/caption_hub.py "${HUB_ARGS[@]+"${HUB_ARGS[@]}"}" &
HUB_PID=$!
trap 'kill $HUB_PID 2>/dev/null' EXIT
sleep 1

case "$MODE" in
  worship|player-demo)
    # 예배 발표기: player 폴더만 이 맥 안에서(127.0.0.1) 보여 줍니다. .env 등 다른 파일은 열리지 않습니다.
    .venv/bin/python -m http.server 8080 --bind 127.0.0.1 --directory player >/dev/null 2>&1 &
    WEB_PID=$!
    trap 'kill $HUB_PID $WEB_PID 2>/dev/null' EXIT
    sleep 1
    URL="http://127.0.0.1:8080/index.html"
    if command -v open >/dev/null; then
      open -a "Google Chrome" "$URL" 2>/dev/null || open "$URL"
    fi
    echo "예배 발표기: $URL"
    echo "  1) '예배 PPT 열기'로 pptx를 고릅니다."
    echo "  2) '청중 화면 열기' → 새 창을 프로젝터 화면으로 끌어다 놓고 F 키 (전체 화면)."
    echo "  3) 노트북 창에서 → / ← 또는 클리커로 넘깁니다. T = 번역 켜기/끄기, B = 화면 가림."
    ;;
  *)
    # 자막 화면을 기본 브라우저로 엽니다. 프로젝터 쪽으로 옮긴 뒤 Control+Command+F로 전체 화면.
    command -v open >/dev/null && open web/captions.html
    ;;
esac

case "$MODE" in
  demo|player-demo)
    echo "데모 자막이 4초마다 나옵니다. 끝내려면 Control + C."
    wait "$HUB_PID"
    ;;
  file)
    [ -n "${2:-}" ] || { echo "사용법: bash start-mac.sh file 녹음파일.wav"; exit 1; }
    [ -f "$2" ] || { echo "파일을 찾을 수 없습니다: $2"; exit 1; }
    .venv/bin/python hub/live_engine.py --file "$2" --langs "$LANGS" --notes "$NOTES"
    echo "녹음 파일 번역이 끝났습니다. 기록: hub/logs/"
    ;;
  live|worship)
    echo "마이크로 듣는 중입니다. 맥의 '시스템 설정 > 사운드 > 입력'에서 핀마이크 수신기를 고르세요."
    echo "처음에는 터미널의 마이크 사용 허용 창이 뜰 수 있습니다 → 허용."
    .venv/bin/python hub/live_engine.py --langs "$LANGS" --notes "$NOTES"
    ;;
  *)
    echo "알 수 없는 모드: $MODE (worship | player-demo | demo | file | live)"; exit 1
    ;;
esac
