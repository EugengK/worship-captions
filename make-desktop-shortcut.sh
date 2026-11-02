#!/usr/bin/env bash
# 바탕화면에 "예배 시작" 실행 아이콘을 만듭니다 (맥마다 한 번만).
#
#   bash ~/worship-captions/make-desktop-shortcut.sh                # 휴대폰 마이크 (교회 MacBook Air)
#   bash ~/worship-captions/make-desktop-shortcut.sh worship        # 맥에 꽂은 마이크(핀마이크 수신기)
#
# 만들어지는 것 (바탕화면):
#   - "예배 시작.command"  : 더블클릭하면 터미널이 열리고 예배 발표기 + 실시간 번역이 켜짐
#   - "이번주 예배" 폴더    : 이번 주 pptx, 자막 파일, 설교 원고(…script.json)를 넣어 두는 곳
set -euo pipefail
cd "$(dirname "$0")"
APP_DIR="$(pwd)"
MODE="${1:-worship-phone}"
case "$MODE" in worship|worship-phone) ;; *) echo "모드는 worship 또는 worship-phone 입니다."; exit 1 ;; esac

DESK="$HOME/Desktop"
FILES="$DESK/이번주 예배"
mkdir -p "$FILES"
LAUNCHER="$DESK/예배 시작.command"

cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
# 예배 시작: 더블클릭하면 실행됩니다. 끝낼 때는 이 터미널 창을 닫거나 Control + C.
# (make-desktop-shortcut.sh 가 만든 파일입니다. 지워도 다시 만들 수 있습니다.)
cd "$APP_DIR" || { echo "프로그램 폴더를 찾을 수 없습니다: $APP_DIR"; read -rp "Enter를 누르면 닫힙니다"; exit 1; }
clear
echo "=== 호바트한인교회 예배 통역 시작 ==="
echo

# 1) 새 버전 받기 (인터넷이 안 되거나 실패하면 지금 있는 버전으로 그대로 진행)
if [ -d .git ]; then
  echo "새 버전 확인 중…"
  if GIT_TERMINAL_PROMPT=0 git pull --ff-only -q 2>/dev/null; then
    echo "  최신 버전입니다."
  else
    echo "  (새 버전을 받지 못했습니다. 지금 버전으로 진행합니다.)"
  fi
fi

# 2) 이번 주 설교 원고: "이번주 예배" 폴더에서 이름에 script 가 들어간 .json 중 가장 마지막 것
SCRIPT_FILE="\$(ls -1 "$FILES"/*script*.json 2>/dev/null | sort | tail -n 1 || true)"
if [ -n "\$SCRIPT_FILE" ]; then
  echo "설교 원고: \$(basename "\$SCRIPT_FILE")"
  export SCRIPT="\$SCRIPT_FILE"
else
  echo "설교 원고 파일 없음 → 원고 없이 실시간 번역만 합니다."
fi
echo
echo "잠시 후 Chrome에 예배 발표기가 열립니다."
echo "  '예배 PPT 열기' → 바탕화면 '이번주 예배' 폴더의 pptx와 자막 파일(…slides.json)을 함께 고르세요."
echo

bash start-mac.sh $MODE
echo
read -rp "끝났습니다. Enter를 누르면 이 창이 닫힙니다." _
EOF
chmod +x "$LAUNCHER"

echo "만들었습니다:"
echo "  - 바탕화면 '예배 시작.command'  → 더블클릭으로 실행"
echo "  - 바탕화면 '이번주 예배' 폴더    → 이번 주 pptx·자막 파일·설교 원고를 여기에 넣으세요"
echo "모드: $MODE"
