# prompt-to-midi 인터페이스 명세

AI가 자연어 요청으로 곡을 만들고 고치는 작업 환경의 규약. 설치는 `INSTALL.md`, 작업 절차는 `SKILL.md`, 이 문서는 계약(폴더·명령·파일 형식)을 정의한다.

## 1. 지원 환경

| 항목 | 요구 |
|---|---|
| OS | macOS, Linux (Windows 미지원: `.venv/bin` 경로 가정) |
| Python | 3.10+ (`studio.py`는 표준 라이브러리만 사용) |
| 시스템 도구 | `fluidsynth`(MIDI→WAV), `ffmpeg`/`ffprobe`(mp3·mp4, libx264 포함) |
| 파이썬 패키지 | `mido>=1.3` (`.venv`에 설치) |
| 사운드폰트 | GeneralUser GS (`soundfonts/GeneralUser-GS.sf2`, 약 32MB, init이 다운로드) |

## 2. 폴더 구조

```
prompt-to-midi/                 ← 저장소 루트 = 스킬 루트
├── SKILL.md                    AI 작업 절차(스킬 진입점, 매 사용 시 로드 → 설치 내용 넣지 않음)
├── INSTALL.md                  처음 한 번 하는 설치(init·doctor·스킬 등록)
├── SPEC.md                     이 문서
├── README.md                   사람용 소개·설치
├── scripts/studio.py           CLI (init / doctor / new / render)
├── templates/song.py           새 곡 템플릿(동작하는 재즈 곡 하나)
├── songs/<slug>/
│   ├── song.py                 곡의 원본(유일한 진실 원천) — git 추적
│   ├── thumbnail.png           (선택) 영상 썸네일 — git 추적
│   └── out/                    렌더 결과 — git 제외, 언제든 재생성
├── .venv/                      git 제외(init이 생성)
└── soundfonts/                 git 제외(init이 다운로드)
```

`slug` 규칙: `[a-z0-9][a-z0-9-]*` (예: `autumn-cafe`, `winter-lofi-2`). 이 규칙 밖의 이름은 CLI가 거부한다(종료코드 2).

## 3. CLI — `python3 scripts/studio.py <명령>`

모든 명령은 저장소 루트 기준 경로를 쓰며, 어느 디렉터리에서 실행해도 된다.

| 명령 | 인자 | 동작 | 종료코드 | 멱등 |
|---|---|---|---|---|
| `init` | 없음 | `.venv` 생성 → `mido` 설치 → 사운드폰트 다운로드·검증(없을 때만) → 시스템 도구 확인. 시스템 도구는 **설치하지 않고** 설치 명령만 출력 | 0 완료 / 1 시스템 도구 누락·다운로드 실패 | 예 |
| `doctor` | 없음 | 아래 진단 항목을 ✅/❌로 출력, 실패 항목엔 `조치:` 표시 | 0 전부 정상 / 1 하나라도 실패 | 예(읽기 전용) |
| `new` | `<slug> [--from <slug>]` | `templates/song.py`(또는 기존 곡)를 `songs/<slug>/song.py`로 복사 | 0 생성 / 1 이미 있음·원본 없음 | 덮어쓰지 않음 |
| `render` | `<slug> [바리에이션...]` | `.venv` 파이썬으로 `songs/<slug>/song.py` 실행. 바리에이션 생략 시 전부 | song.py의 종료코드 | 예(결과 덮어씀) |

### doctor 진단 항목

1. Python 3.10+
2. `.venv` 존재 + `import mido` 성공
3. `fluidsynth`, `ffmpeg`, `ffprobe`가 PATH에 있음
4. ffmpeg에 `libx264` 인코더 있음(mp4용)
5. 사운드폰트 헤더가 `RIFF....sfbk`
6. 필수 프리셋 존재: Piano(0), Nylon Guitar(24), Acoustic Bass(32), Slow Strings(49), Jazz kit(128-32), Brush kit(128-40)
7. 테스트 렌더링: 1음 MIDI → fluidsynth → WAV가 무음이 아님

## 4. 곡 파일 계약 — `songs/<slug>/song.py`

자기완결형 파이썬 스크립트. 엔진 코드를 곡마다 복사해 두므로 템플릿이 바뀌어도 기존 곡은 깨지지 않는다.

**필수 구성**

| 이름 | 형식 | 의미 |
|---|---|---|
| 모듈 docstring 첫 줄 | `<제목> — <컨셉>` | 곡 식별·검색용 |
| `CHORDS` | `{코드명: (근음, [보이싱 음이름...])}` | 음이름 형식 `C4`, `Bb3`, `F#4` |
| `PROG_*` | `[(코드명, 박수), ...]` | 진행. 섹션 길이는 4박의 배수 |
| `MEL_*` | `"음 박수 음 박수 ..."` 문자열 | `R`=쉼표, `|`=마디 구분(무시됨) |
| `FORM` | `[(이름, 진행, 멜로디, 리드번호, 베이스, 드럼), ...]` | 곡 구성 순서 |
| `PALETTE` | `{악기명: dict(program, vol, pan)}` | GM 프로그램 번호 |
| `VARIANTS` | `{이름: dict(tempo, swing, comp, leads, drums, pad)}` | 바리에이션 = 출력 파일 단위 |
| `GAIN`, `SEED` | 숫자 | 전체 음량 / 연주 흔들림 고정값 |
| `check()` | 함수 | 멜로디 박 수 = 진행 박 수, 악기·패턴 존재 검증(assert) |

**실행 인터페이스**: `python song.py [바리에이션...]` — `check()` 후 렌더링. 없는 바리에이션 이름이면 목록을 출력하고 종료코드 1.

**출력**: `songs/<slug>/out/<바리에이션>.{mid,mp3,mp4}` 그리고 한 줄 요약
`완료: <바리에이션> (<초>초, 피크 <dB>dB[, 영상 포함])[  ⚠ 경고]`
- 피크 > -1dB → 클리핑 위험 경고(`GAIN` 낮춤)
- 피크 < -20dB → 소리가 작거나 없음 경고

## 5. 렌더 파이프라인(고정값)

| 단계 | 도구·설정 | 이유 |
|---|---|---|
| MIDI 생성 | mido, 480 TPB, 마지막에 6박 여유 | 잔향이 잘리지 않게 |
| 합성 | `fluidsynth -ni -g $GAIN -r 44100` | — |
| 음량 | **리미터/`loudnorm` 미사용**, `GAIN`으로 조절 | 1패스 loudnorm이 잡음을 만들었음 |
| mp3 | ffmpeg 256kbps | — |
| mp4 | 썸네일 1920×1080 정지 영상, 1fps, AAC 256k, `-t <오디오 길이>` | `-shortest`는 영상이 오디오보다 길게 남는 문제가 있었음 |

## 6. 저장 규약

- **원본은 `song.py` 하나.** mid/mp3/mp4는 산출물이라 git에 넣지 않는다(재생성 가능).
- 자연어 수정 1건 = `song.py` 수정 → render → 사용자 확인 → 커밋 1개.
- 커밋 메시지: `<slug>: <무엇을 바꿨는지>` (예: `autumn-cafe: 비브라폰 제거, 피아노 트리오 바리에이션 추가`)
- 마음에 드는 버전을 보존하면서 실험하려면 `VARIANTS`에 새 항목을 추가하거나, 구조가 크게 달라지면 `new <새slug> --from <slug>`로 갈라낸다.
- 공유·배포용 음원이 필요하면 `out/`에서 꺼내 쓴다(필요 시 GitHub Release 등 별도 보관).
