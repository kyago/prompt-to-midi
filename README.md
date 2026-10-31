# prompt-to-midi

AI(Claude 등)와 자연어로 개인용 음악을 만드는 작업 환경.
AI가 곡을 Python 데이터(코드 진행·멜로디·구성·악기)로 작성하고, "템포 느리게", "기타로 바꿔" 같은 요청에 해당 부분만 고친다. 결과는 MIDI·MP3, 그리고 썸네일 이미지를 넣은 MP4 영상이다.

## 시작하기

1. **설치(처음 한 번)**: `INSTALL.md`를 따른다. AI에게 맡길 땐 "INSTALL.md대로 설치해줘".
2. **사용**: Claude Code 스킬로 등록했다면 "카페 재즈 BGM 만들어줘"처럼 요청한다. 다른 AI 에이전트에는 `SKILL.md`를 읽게 한다.

## 구성

| 경로 | 내용 |
|---|---|
| `INSTALL.md` | 처음 한 번 하는 설치(init·doctor·스킬 등록) |
| `SKILL.md` | AI 작업 절차: 실행 → 저장 (스킬 사용 시마다 로드) |
| `SPEC.md` | 명령·폴더·곡 파일 형식 명세 |
| `scripts/studio.py` | CLI (표준 라이브러리만 사용) |
| `scripts/analyze.py` | 렌더된 MIDI 자동 점검(`studio.py analyze`) |
| `templates/song.py` | 새 곡 템플릿 |
| `songs/autumn-cafe/` | 예제: 가을/겨울 카페 재즈, 바리에이션 4종 |

## 라이선스 참고

사운드폰트는 저장소에 포함하지 않고 `init`이 내려받는다. 사용 조건은 각 라이선스를 따른다.

- [GeneralUser GS](https://github.com/mrbumpy409/GeneralUser-GS): 피아노 외 전 악기
- [Upright Piano KW](https://freepats.zenvoid.org/Piano/acoustic-grand-piano.html#UprightKW) (FreePats): 피아노. CC0(퍼블릭 도메인)이라 출처 표기 없이 쓸 수 있다
