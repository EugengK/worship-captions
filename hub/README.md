# 자막 허브 + 실시간 번역 엔진

> 가장 쉬운 실행 방법은 저장소 맨 위의 `start-mac.sh`입니다. 안내: `맥에서-시험하기.md`

```
핀마이크 → live_engine.py ──(자막)──> caption_hub.py ──> 이음오피스 자막 띠 / web/captions.html / (나중에) 성도 휴대폰
            │  Gemini: 한국어 인식 → 용어집 반영 번역(en, th …)
```

## 설치 (맥, 한 번만)
```bash
cd worship-captions/hub
python3 -m pip install -r requirements.txt
export GEMINI_API_KEY=...   # 키는 파일에 저장하거나 커밋하지 마세요
```

## 예배 때 실행
터미널 창 1 — 자막 허브:
```bash
python3 caption_hub.py
```
터미널 창 2 — 실시간 번역 엔진 (기본: 맥의 기본 입력 장치 = 핀마이크 수신기, 영어+태국어):
```bash
python3 live_engine.py --langs en,th
```
자막 화면: 이음오피스(자막 패치)로 발표하거나, 아무 브라우저에서 `web/captions.html`을 열어 전체 화면으로 띄웁니다.

## 시험
- 데모 자막만: `python3 caption_hub.py --demo`
- 녹음 파일로 실제 번역 시험: `python3 live_engine.py --file 설교녹음.wav`
- 코드 시험(인터넷·API 불필요): `python3 -m pytest tests`

## 파일
- `glossary.json` — 교회 용어집. 문장에 그 단어가 있을 때만 번역 지시에 들어갑니다. 태국어 항목은 확인 필요.
- `logs/` — 예배별 한국어 원문 + 번역 기록(JSON Lines). 저장소에는 올라가지 않습니다.

## 아직 검증하지 못한 것 (2026-10-28)
- Gemini 크레딧 소진으로 **실제 인식·번역을 이 엔진으로는 아직 돌려 보지 못했습니다.** 코드 시험은 번역 부분을 가짜로 바꿔 통과했습니다.
- Live 세션은 시간 제한이 있어 끊기면 자동으로 다시 연결하도록 만들었지만, 30분 이상 설교에서의 실제 동작은 확인 전입니다.
- 맥 마이크 입력(sounddevice)은 맥에서 확인해야 합니다.
