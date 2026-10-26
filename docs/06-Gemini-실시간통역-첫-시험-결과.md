# Gemini 실시간 통역 첫 시험 결과 (2026-10-26)

## 시험 방법
1. Gemini TTS(`gemini-3.8-flash-tts`)로 **한국어 설교 문장 약 35초**를 음성으로 만들었습니다 (`experiments/make_korean_test_audio.py`).
   - 실제 목사님 음성이 아니라 **AI 합성 음성**입니다. 실제 예배 마이크 음성으로 다시 시험해야 합니다.
2. 이 음성을 실시간 속도(0.1초 단위)로 `gemini-3.5-live-translate-preview`에 보내고, 한국어 원문 인식·번역 텍스트·번역 음성을 받았습니다 (`experiments/gemini_live_translate_test.py`).

## 확인된 사실 [이번 시험으로 직접 확인]
| 항목 | 결과 |
|---|---|
| 우리 API 키로 모델 사용 가능 | ✅ `gemini-3.5-live-translate-preview` 사용 가능 |
| **태국어(th) 출력** | ✅ **된다** (번역 음성 + 태국어 텍스트) |
| 영어(en) 출력 | ✅ 된다 |
| **한국어 원문 텍스트**(원고 추적용) | ✅ 같은 연결에서 함께 나옴 → 원고 추적기 설계가 가능함 |
| 첫 번역 텍스트까지 걸린 시간 | 영어 4.3초, 태국어 5.0초 (말 시작부터) |
| 별도 실시간 인식 모델 | `gemini-3.5-transcribe-live`도 목록에 있음 (아직 시험 안 함) |

## 번역 내용 (원문 → 영어)
> The Lord said to Abram, "Now, go from your country, your people, and your father's household to the land I will show you. God is a covenant-making God. We are justified only by faith. The Heidelberg Catechism, Question 1, asks: Whether in life or death, what is your only comfort?

- 영어는 매우 자연스럽고 신학 용어도 정확했습니다(covenant, justified by faith, Heidelberg Catechism Question 1). 창세기 12:1은 NIV 문장과 거의 같았습니다. [Claude 판단]

## 발견된 문제 → 설계에 반영할 점
1. **한국어 인식 오류:** "아브람"을 "아브라함"으로 인식했습니다. 다만 영어 번역은 Abram으로 맞게 나왔습니다.
   → **원고·용어집이 필요하다는 근거**입니다.
2. **태국어 용어:** "하이델베르크 요리문답"이 태국어로 "คำสารภาพความเชื่อไฮเดลเบิร์ก"(직역하면 '하이델베르크 신앙고백')으로 나왔습니다. **요리문답(Catechism)과 신앙고백(Confession)은 다른 문서**이므로 용어집으로 고정해야 합니다.
   - 그 밖의 태국어 용어(ปฐมกาล=창세기, พันธสัญญา=언약, ผู้ชอบธรรม=의인)는 제가 아는 범위에서 맞아 보입니다. 다만 **태국어 품질은 제가 보증할 수 없습니다.**
3. **실시간 통역 모델에는 용어집을 넣는 설정이 없습니다**(SDK 설정 항목은 `target_language_code`, `echo_target_language`뿐).
   → 용어집은 **화면 자막 쪽(원고 + 텍스트 모델)**에서 적용하는 기존 설계가 맞습니다.
4. TTS가 "차분한 설교 톤으로 읽어 주세요"라는 지시문까지 읽어 버려서, 그것도 번역되었습니다. 시험 음성 제작상의 문제이며 통역 품질과는 무관합니다.

## 다음 시험
- [ ] **목사님 실제 목소리** 녹음(휴대폰 녹음도 가능)으로 재시험
- [ ] 긴 설교(30분 이상)에서 연결 유지와 세션 시간 제한 확인
- [ ] OpenAI 키 재확인 후 같은 음성으로 비교 (현재 401 인증 오류)
- [ ] 원고 추적기 시제품: 원고 + 한국어 인식 텍스트 → 문장 맞추기
