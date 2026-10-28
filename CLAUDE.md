# worship-captions

호바트한인교회 예배의 실시간 통역(휴대폰 음성) + 프로젝터 번역 자막 프로젝트.

## 기억할 사실
- 교회 이름: **호바트한인교회** (교회 통합으로 "호바트한인장로교회"에서 변경됨 — 옛 이름 사용 금지). 영어 명칭은 미확정, 임시로 "Hobart Korean Church".
- 사용자는 담임목사. 대화는 한국어. 확인되지 않은 정보는 사실처럼 말하지 말고 출처·확실성을 밝힐 것.
- 기획 결정 사항은 `docs/01`~`docs/11`에 순서대로 있음. 새 작업 전에 최신 문서부터 읽을 것.

## 현재 결정 요약
- 환경: **예배·개발용 맥 = 목사님의 다른 MacBook** (기종·macOS 버전 확인 대기, macOS 12+ 필요). 기존 교회 MacBook Air(2013~14, Big Sur)는 **작업 대상에서 제외**(추후 교체 예정). 프로젝터 1920×1200, 듀얼 모니터 운영. OBS·생방송 없음.
- 입력: 목사님 무선 핀마이크(USB 수신기) → 맥 직결.
- 엔진: Google `gemini-3.5-live-translate-preview` 주 엔진 + OpenAI `gpt-realtime-translate` 선택/자동 대체. 엔진 교체형 구조.
- 언어: 태국어 최우선(화면 자막), 영어 기준으로 검증. 원고 기반 번역 + 운영자 없는 자동 원고 추적.
- 화면: 성도 휴대폰 웹페이지(`web/listener.html`). 프로젝터는 **이음오피스(pblsketch/openoffice) 포크의 청중 화면에 자막 띠 통합**이 주안(docs/10). macOS 12+ 필요 → 위의 다른 MacBook 사용. 1단계(이음오피스로 주일 pptx 재생 시험) 실패 시 Keynote + 투명 오버레이(A안)로 복귀.
- 코드 위치: `ieumoffice/`(이음오피스 자막 띠 패치 + 맥 설치 스크립트, 원본 커밋 고정), `hub/caption_hub.py`(맥에서 도는 자막 허브, ws://localhost:8765, `--demo`), `web/listener.html`(성도 휴대폰), `experiments/`(Gemini 시험).
- API 키는 환경 변수 `GEMINI_API_KEY`, `OPENAI_API_KEY`. 절대 커밋하지 말 것.
