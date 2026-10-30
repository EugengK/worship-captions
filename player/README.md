# 예배 발표기 (worship player)

PowerPoint로 만든 예배 `.pptx`를 브라우저에서 바로 발표하고, 프로젝터 화면 아래에 실시간 번역 자막을 띄웁니다.
pptx 해석·배치·그리기는 [이음오피스](https://github.com/pblsketch/openoffice)(Apache-2.0)의
`pptx-engine`, `pptx-render`, 슬라이드 그리기 부품(`SlideThumb`)을 그대로 씁니다
(고정 커밋: `../ieumoffice/UPSTREAM_COMMIT`). 라이선스 사본은 `licenses/`.

## 실행 (맥)
저장소 맨 위에서 `bash start-mac.sh worship` (실제 번역) 또는 `bash start-mac.sh player-demo` (데모 자막).
자세한 사용법은 `../맥에서-시험하기.md`.

## 구조
| 파일 | 역할 |
|---|---|
| `index.html` → `src/presenter.tsx` | 발표자 창(노트북): pptx 열기, 현재/다음 슬라이드, 노트, 슬라이드 목록, 키·클리커, 음악, 번역 켜기/끄기 |
| `audience.html` → `src/audience.tsx` | 청중 창(프로젝터): 슬라이드 + 자막 띠. 발표자 창이 연 덱을 `window.opener`에서 받아 그림 |
| `src/deck.ts` | pptx 열기 → 1920폭 그리기 정보, 그림 주소(blob URL), 포함 글꼴, 음악, 노트 |
| `src/markers.ts` | 노트의 `[번역 ON]`/`[번역 OFF]` 해석, 자동 재생 음악 찾기 (시험: `test/`) |
| `src/fonts.ts` | 포함 글꼴 등록, 브라우저 캔버스로 글자 폭 측정, 윈도 글꼴(굴림 등)의 맥 대체 글꼴 |
| `src/link.ts`, `src/CaptionBand.tsx` | 자막 허브(ws://localhost:8765) 연결, 자막 띠 |
| `src/shims/` | 엔진의 Node 전용 부분(저장·해시) 브라우저용 대체 |

창 사이 연결: `BroadcastChannel('worship-player')` (현재 슬라이드, 번역 상태, 화면 가림, 프로젝터 창의 키 입력).
번역 켜기/끄기: 발표자 창 → 허브에 `{"type":"control","translate":bool,"slide":n}` → `hub/live_engine.py`가
꺼진 동안 마이크 소리를 Google에 보내지 않음.

## 다시 빌드 (개발자용)
`dist/`는 저장소에 들어 있어 맥에는 Node가 필요 없습니다. 코드를 고친 뒤에만:
```bash
bash player/build.sh          # 이음오피스 고정 커밋을 player/.ieum에 받아 빌드 (Node 22+)
node --experimental-strip-types --test player/test/markers.test.ts
```
