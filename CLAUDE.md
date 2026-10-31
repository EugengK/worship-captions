# worship-captions

호바트한인교회 예배의 실시간 통역(휴대폰 음성) + 프로젝터 번역 자막 프로젝트.

## 기억할 사실
- 교회 이름: **호바트한인교회** (교회 통합으로 "호바트한인장로교회"에서 변경됨 — 옛 이름 사용 금지). 영어 명칭은 미확정, 임시로 "Hobart Korean Church".
- 사용자는 담임목사. 대화는 한국어. 확인되지 않은 정보는 사실처럼 말하지 말고 출처·확실성을 밝힐 것.
- 기획 결정 사항은 `docs/01`~`docs/16`에 순서대로 있음. 새 작업 전에 최신 문서부터 읽을 것.

## 현재 결정 요약
- 환경: **예배·개발용 맥 = 목사님의 다른 MacBook** (기종·macOS 버전 확인 대기, macOS 12+ 필요). 기존 교회 MacBook Air(2013~14, Big Sur)는 처음엔 제외했으나 **2026-10-31 예배용으로 쓰기로 함**(설치·발표기 동작 확인). 프로젝터 1920×1200, 듀얼 모니터 운영. OBS·생방송 없음.
- 입력: 목사님 무선 핀마이크(USB 수신기) → 맥 직결. **2026-10-30: 아이폰을 맥 마이크로 쓰는 연속성 카메라 기능(시스템 설정 → 사운드 → 입력에 아이폰 표시)이 목사님 맥에서 동작 확인** → 핀마이크 구매 전 이것으로 시험 중(설교 길이 안정성·음질 미확인). **예배 맥은 교회 MacBook Air(macOS 11)로 결정(2026-10-31)** — 연속성 마이크 불가 → **휴대폰 웹 마이크**(`hub/phone_mic.py`+`phone_mic.html`: 맥이 https:8443 자체 서명 인증서로 페이지 제공, 휴대폰이 16kHz PCM을 wss로 전송, `live_engine.py --phone`, `start-mac.sh worship-phone|phone-test`). 에어는 Python 3.12를 uv로 사용자 폴더에 설치(관리자 암호 모름), pip `--prefer-binary`(cryptography 49+는 인텔 맥 wheel 없음).
- 엔진: Google `gemini-3.5-live-translate-preview` 주 엔진 + OpenAI `gpt-realtime-translate` 선택/자동 대체. 엔진 교체형 구조.
- 언어: 태국어 최우선(화면 자막), 영어 기준으로 검증. 원고 기반 번역 + 운영자 없는 자동 원고 추적.
- 화면: 성도 휴대폰 웹페이지(`web/listener.html`). 프로젝터는 **자체 "예배 발표기"(이음오피스 pptx-engine/pptx-render를 떼어 씀) + 자막 띠 내장**이 주 방향(docs/14). 예배 PPT는 **PowerPoint로 제작(.pptx)** → 발표기가 그대로 재생(변환 불필요). 기존에는 그 pptx를 MacBook Air의 Keynote로 발표했음. 발표자 노트의 `[번역 ON]`/`[번역 OFF]`로 번역 자동 켜기/끄기(찬양·찬송·성경 봉독·신앙고백은 끔). 관문: 실제 예배 pptx 재현 품질. 실패 시 Keynote + 덮개 창(A안). `ieumoffice/` 패치는 보조.
- 코드 위치: `ieumoffice/`(이음오피스 자막 띠 패치 + 맥 설치 스크립트, 원본 커밋 고정), `hub/caption_hub.py`(맥에서 도는 자막 허브, ws://localhost:8765, `--demo`), `hub/live_engine.py`(마이크→`gemini-3.5-transcribe-live` 한국어 인식(말끝 감지 민감도 높음)→`gemini-3.5-flash`(생각 모드 끔) 용어집 번역→허브. 3.8 Live는 설교 연속 통역 불가(docs/13), 테스트 `hub/tests`), `web/captions.html`(브라우저용 자막 화면), `web/listener.html`(성도 휴대폰), `experiments/`(Gemini 시험).
- 예배 발표기: `player/`(브라우저용, 이음오피스 엔진 번들 `player/dist` 커밋됨, 재빌드 `player/build.sh`). 발표자 창 + 청중 창(BroadcastChannel), 노트 `[번역 ON/OFF]` → 허브 `control` 메시지 → 엔진이 꺼진 동안 소리 안 보냄. 실제 예배 pptx는 커밋 금지(`*.pptx` gitignore). 자막 언어: 기본 영어 + 중국어·태국어·베트남어 중 최대 3개(발표자 화면에서 고름). **준비된 자막** 파일(.json, 슬라이드 번호→언어별 글)을 예배마다 Claude가 만들어 줌 → 그 슬라이드는 실시간 번역 꺼짐.
- 번역 결정: 성경 구절 **NIV**(공식 본문에서 가져올 것, 기억으로 쓰지 말 것). 사도신경 영어는 목사님이 직접 만듦(자막 띠 X). 교독문은 슬라이드마다 영어를 자막 띠에. 설교·광고는 원고 미리 번역 + 실시간(원고 따라가기는 아직 미구현).
- 맥 실행: `start-mac.sh`(worship | player-demo | demo | file | live, 첫 실행 시 .venv 설치와 키 입력 → `.env`, 둘 다 gitignore), 안내서 `맥에서-시험하기.md`.
- API 키는 환경 변수 `GEMINI_API_KEY`, `OPENAI_API_KEY`. 절대 커밋하지 말 것.
