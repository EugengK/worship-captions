# 이음오피스 + 예배 자막 띠

이음오피스(https://github.com/pblsketch/openoffice, Apache-2.0)의 **슬라이드쇼 화면 맨 아래에 실시간 번역 자막 띠**를 넣는 패치입니다.

## 바뀌는 것 (패치 내용)
- 새 파일 `apps/slides/src/renderer/components/CaptionBar.tsx` — 자막 띠
- `AudienceView.tsx`(프로젝터 청중 화면), `SlideShowView.tsx`(화면 1개 발표)에 각각 `<CaptionBar />` 한 줄씩 추가
- 원본의 다른 동작은 바꾸지 않습니다. **자막 허브가 꺼져 있으면 자막 띠도 나타나지 않아** 원래 이음오피스와 똑같이 동작합니다.

## 동작 방식
- 자막 띠는 이 맥의 `ws://localhost:8765`(자막 허브)에 연결합니다. 이음오피스의 보안 설정(CSP)이 이미 `ws://localhost`를 허용하므로 보안 설정은 건드리지 않습니다.
- 자막이 오면 표시하고, **8초 동안 새 자막이 없으면 서서히 사라집니다**(찬양·침묵 시간에 화면을 가리지 않음).
- 언어별 최대 2줄. 첫 줄 흰색(예: 영어), 둘째 줄 연한 노랑(예: 태국어).

## 검증한 것 (클라우드 개발 환경, 2026-10-27)
- 원본 커밋 `UPSTREAM_COMMIT`에 패치 적용 후 slides 앱 **타입 검사(tsc) 통과, ESLint 통과**
- 자막 띠 컴포넌트를 1920×1200 화면에 띄우고 데모 허브와 연결 → **영어/태국어 표시, 8초 후 자동 숨김 확인**
- **아직 못 한 것:** 실제 이음오피스 앱 안에서의 실행(맥 필요), 프로젝터 2화면 발표 모드에서의 확인

## 목사님 맥에서 시험하는 순서
1. 이 저장소를 맥에 받습니다: `git clone https://github.com/EugengK/worship-captions.git`
2. 자막 허브를 데모 모드로 켭니다 (터미널 창 1):
   ```bash
   cd worship-captions/hub
   python3 -m pip install websockets
   python3 caption_hub.py --demo
   ```
3. 자막 패치를 적용한 이음오피스를 빌드하고 실행합니다 (터미널 창 2, 처음 한 번은 시간이 걸림):
   ```bash
   bash worship-captions/ieumoffice/setup-mac.sh
   ```
   - Node.js 22 이상과 Rust가 필요합니다. 없으면 스크립트가 설치 주소를 알려 줍니다.
4. 이음오피스에서 주일 pptx를 열고 **발표 시작** → 4초마다 영어·태국어 데모 자막이 화면 아래에 나오면 성공입니다.
5. 다음부터는 `bash worship-captions/ieumoffice/setup-mac.sh --run`으로 바로 실행합니다.

## 원본 업데이트 반영
`UPSTREAM_COMMIT`을 새 커밋으로 바꾸고 `setup-mac.sh`를 다시 실행합니다. 패치가 작아서(파일 1개 + 두 줄) 충돌 가능성은 낮지만, 충돌하면 Claude에게 패치 갱신을 요청하세요.
