# 설치 (처음 한 번)

이 저장소를 처음 받은 AI·사람이 한 번 따르는 문서. 설치 후에는 `SKILL.md`만 보면 된다.

## 1. init

```bash
python3 scripts/studio.py init
```
- `.venv` 생성, `mido` 설치, 사운드폰트 다운로드·검증을 한다. 여러 번 실행해도 안전하다.
  - GeneralUser GS(약 32MB)
  - 피아노용 Salamander Grand(받기 약 300MB, 풀면 1.3GB). 디스크가 부족하면 이 단계가 실패해도 곡은 GM 피아노로 렌더된다
- 시스템 도구(fluidsynth, ffmpeg)가 없으면 설치 명령만 출력하고 종료코드 1로 끝난다.
  - macOS: `brew install fluid-synth ffmpeg`
  - Debian/Ubuntu: `sudo apt install fluidsynth ffmpeg`
- **AI는 시스템 패키지 설치 명령을 사용자에게 보여주고 승인받은 뒤 실행한다.** 컴퓨터 전체에 영향을 주기 때문이다. 설치 후 init을 다시 실행한다.

## 2. doctor로 확인

```bash
python3 scripts/studio.py doctor
```
- 모든 항목이 ✅이고 마지막에 "정상"이 나오면 끝이다. 마지막 "테스트 렌더링"은 실제로 소리가 나는지까지 확인한다.
- ❌ 항목은 `조치:`를 따른 뒤 다시 실행한다.

## 3. (선택) Claude Code 스킬로 등록

```bash
ln -s "$(pwd)" ~/.claude/skills/prompt-to-midi
```
- 이후 "카페 재즈 BGM 만들어줘"처럼 요청하면 `SKILL.md`가 자동으로 로드된다.
- 다른 AI 에이전트는 작업할 때 `SKILL.md`를 읽게 한다.
