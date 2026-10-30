# worship-captions

호바트한인교회 예배의 실시간 통역(휴대폰 음성) + 프로젝터 번역 자막 프로젝트.

## 기억할 사실
- 교회 이름: **호바트한인교회** (교회 통합으로 "호바트한인장로교회"에서 변경됨 — 옛 이름 사용 금지). 영어 명칭은 미확정, 임시로 "Hobart Korean Church".
- 사용자는 담임목사. 대화는 한국어. 확인되지 않은 정보는 사실처럼 말하지 말고 출처·확실성을 밝힐 것.
- 기획 결정 사항은 `docs/01`~`docs/14`에 순서대로 있음. 새 작업 전에 최신 문서부터 읽을 것.

## 현재 결정 요약
- 환경: **예배·개발용 맥 = 목사님의 다른 MacBook** (기종·macOS 버전 확인 대기, macOS 12+ 필요). 기존 교회 MacBook Air(2013~14, Big Sur)는 **작업 대상에서 제외**(추후 교체 예정). 프로젝터 1920×1200, 듀얼 모니터 운영. OBS·생방송 없음.
- 입력: 목사님 무선 핀마이크(USB 수신기) → 맥 직결.
- 엔진: Google `gemini-3.5-live-translate-preview` 주 엔진 + OpenAI `gpt-realtime-translate` 선택/자동 대체. 엔진 교체형 구조.
- 언어: 태국어 최우선(화면 자막), 영어 기준으로 검증. 원고 기반 번역 + 운영자 없는 자동 원고 추적.
- 화면: 성도 휴대폰 웹페이지(`web/listener.html`). 프로젝터는 **자체 "예배 발표기"(이음오피스 pptx-engine/pptx-render를 떼어 씀) + 자막 띠 내장**이 주 방향(docs/14). Keynote로 작성 → pptx로 내보내 발표기로 재생. 발표자 노트의 `[번역 ON]`/`[번역 OFF]`로 번역 자동 켜기/끄기(찬양·찬송·성경 봉독·신앙고백은 끔). 관문: 실제 예배 pptx 재현 품질. 실패 시 Keynote + 덮개 창(A안). `ieumoffice/` 패치는 보조.
- 코드 위치: `ieumoffice/`(이음오피스 자막 띠 패치 + 맥 설치 스크립트, 원본 커밋 고정), `hub/caption_hub.py`(맥에서 도는 자막 허브, ws://localhost:8765, `--demo`), `hub/live_engine.py`(마이크→`gemini-3.5-transcribe-live` 한국어 인식(말끝 감지 민감도 높음)→`gemini-3.5-flash`(생각 모드 끔) 용어집 번역→허브. 3.8 Live는 설교 연속 통역 불가(docs/13), 테스트 `hub/tests`), `web/captions.html`(브라우저용 자막 화면), `web/listener.html`(성도 휴대폰), `experiments/`(Gemini 시험).
- 맥 실행: `start-mac.sh`(demo | file | live, 첫 실행 시 .venv 설치와 키 입력 → `.env`, 둘 다 gitignore), 안내서 `맥에서-시험하기.md`.
- API 키는 환경 변수 `GEMINI_API_KEY`, `OPENAI_API_KEY`. 절대 커밋하지 말 것.
