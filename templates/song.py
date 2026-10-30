"""<곡 제목> — <컨셉 한 줄: 분위기·장르·용도>

이 파일이 곡의 원본이다. 수정은 '곡 데이터' 블록에서만 한다(아래 엔진은 손대지 않아도 됨).
실행(저장소 루트에서): python3 scripts/studio.py render <slug> [바리에이션...]
결과: out/<바리에이션>.mid / .mp3 / .mp4(thumbnail.png가 있을 때만)
"""
import random
import re
import subprocess
import sys
from pathlib import Path

import mido

HERE = Path(__file__).resolve().parent
SOUNDFONT = HERE.parents[1] / "soundfonts" / "GeneralUser-GS.sf2"
OUT = HERE / "out"

# ───────────── 곡 데이터 ─────────────
SEED = 42  # 사람이 연주한 듯한 흔들림 고정값(같은 값이면 같은 결과)
GAIN = 1.3  # 전체 음량(fluidsynth 게인). 피크 경고가 뜨면 낮춘다

# 코드: 베이스 근음, 반주 보이싱
CHORDS = {
    "Fmaj9":  ("F",  ["A3", "C4", "E4", "G4"]),
    "Em7b5":  ("E",  ["G3", "Bb3", "D4"]),
    "A7b13":  ("A",  ["G3", "C#4", "F4"]),
    "Dm9":    ("D",  ["F3", "A3", "C4", "E4"]),
    "Cm9":    ("C",  ["Eb3", "G3", "Bb3", "D4"]),
    "F13":    ("F",  ["Eb3", "A3", "D4"]),
    "Bbmaj9": ("Bb", ["D3", "F3", "A3", "C4"]),
    "Bbm6":   ("Bb", ["Db3", "F3", "G3", "C4"]),
    "Am7":    ("A",  ["G3", "C4", "E4"]),
    "D7b9":   ("D",  ["F#3", "C4", "Eb4"]),
    "Gm9":    ("G",  ["F3", "A3", "Bb3", "D4"]),
    "C9":     ("C",  ["E3", "Bb3", "D4"]),
    "C13":    ("C",  ["E3", "A3", "Bb3", "D4"]),
    "C9sus":  ("C",  ["Bb3", "D4", "F4"]),
}

# 진행: (코드, 박 수)
PROG_INTRO = [("Bbmaj9", 4), ("Am7", 4), ("Gm9", 4), ("C9sus", 4)]
PROG_A = [("Fmaj9", 4), ("Em7b5", 2), ("A7b13", 2), ("Dm9", 4), ("Cm9", 2), ("F13", 2),
          ("Bbmaj9", 4), ("Bbm6", 4), ("Am7", 2), ("D7b9", 2), ("Gm9", 2), ("C9", 2)]
PROG_B = [("Bbmaj9", 4), ("Am7", 4), ("Gm9", 4), ("C13", 4),
          ("Fmaj9", 4), ("Dm9", 4), ("Gm9", 4), ("C9sus", 4)]
PROG_OUTRO = [("Bbmaj9", 4), ("Bbm6", 4), ("Am7", 4), ("Gm9", 4), ("C9sus", 4), ("Fmaj9", 8)]

# 멜로디: "음 박수" 나열, R = 쉼표, | 는 마디 구분(가독용)
MEL_A = """
R 1  A4 .5 C5 .5 E5 1.5 D5 .5 | C5 1.5 Bb4 .5 A4 1 G4 1 | F4 1 A4 .5 E5 2.5 | R .5 Eb5 .5 D5 .5 C5 .5 A4 1 R 1 |
D5 1.5 C5 .5 A4 1 F4 1 | Db5 1.5 C5 .5 Bb4 1 G4 1 | C5 1 G4 .5 E4 .5 F#4 1 A4 1 | Bb4 .5 A4 .5 G4 2 R 1
"""
MEL_B = """
F5 1.5 E5 .5 D5 1 C5 1 | E5 2.5 R .5 C5 .5 D5 .5 | D5 1.5 Bb4 .5 A4 2 | G4 1 A4 1 Bb4 1 D5 1 |
E5 1.5 C5 .5 A4 2 | R .5 F4 .5 A4 .5 C5 .5 E5 2 | D5 1.5 C5 .5 Bb4 1 A4 1 | G4 3 R 1
"""
MEL_OUTRO = "R 16 | R 2 G4 1 Bb4 1 | A4 8"

# 구성: (이름, 진행, 멜로디, 멜로디 담당(0=lead1, 1=lead2), 베이스, 드럼)
FORM = [
    ("intro", PROG_INTRO, None,      None, False, False),
    ("A1",    PROG_A,     MEL_A,     0,    True,  True),
    ("A2",    PROG_A,     MEL_A,     1,    True,  True),
    ("B1",    PROG_B,     MEL_B,     0,    True,  True),
    ("A3",    PROG_A,     MEL_A,     1,    True,  True),
    ("B2",    PROG_B,     None,      None, True,  True),   # 쉬어가는 반주 구간
    ("A4",    PROG_A,     MEL_A,     0,    True,  True),
    ("outro", PROG_OUTRO, MEL_OUTRO, 0,    True,  True),
]

# 악기 팔레트: GM 프로그램 번호, 볼륨, 팬(0 왼쪽~127 오른쪽)
# 주의: 이 사운드폰트의 4 Tine EP(Rhodes)·11 비브라폰은 어택이 금속성이라 '깨지는 소리'로 들린다는 피드백이 있었음
PALETTE = {
    "piano":   dict(program=0,  vol=100, pan=58),
    "guitar":  dict(program=24, vol=110, pan=80),   # 나일론 기타
    "bass":    dict(program=32, vol=108, pan=64),   # 어쿠스틱 베이스
    "strings": dict(program=49, vol=60,  pan=64),   # 느린 현악 패드
    "brush":   dict(program=40, vol=80,  pan=64),   # 드럼: 브러시 킷 (이름 = DRUMS 패턴 이름)
    "bossa":   dict(program=32, vol=72,  pan=64),   # 드럼: 재즈 킷
}

# 바리에이션: 템포, 스윙(0=스트레이트, 1/6=셔플), 반주 악기·주법, 멜로디 악기 2개, 드럼, 패드
VARIANTS = {
    "piano-trio":  dict(tempo=76,  swing=1/6, comp=("piano", "jazz"),   leads=("piano", "piano"),
                        drums="brush", pad=None),
    "guitar-cafe": dict(tempo=80,  swing=1/6, comp=("piano", "jazz"),   leads=("guitar", "piano"),
                        drums="brush", pad=None),
    "bossa":       dict(tempo=104, swing=0,   comp=("guitar", "bossa"), leads=("piano", "piano"),
                        drums="bossa", pad=None),
    "snow-ballad": dict(tempo=62,  swing=0,   comp=("piano", "ballad"), leads=("piano", "piano"),
                        drums=None, pad="strings"),
}
# ─────────────────────────────────────

TPB = 480
PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
CH = {"comp": 0, "bass": 1, "lead1": 2, "lead2": 3, "pad": 4, "drums": 9}

# 반주 주법: 한 코드 안에서 (시작 박, 길이, 세기)
COMP = {
    "jazz":   lambda beats: [(0, 1.8, 50)] if beats == 2 else [(0, 2.4, 52), (3.5, 0.5, 42)] if beats == 4
              else [(0, beats, 50)],
    "bossa":  lambda beats: [(o, d, v) for o, d, v in [(0, 1, 56), (1.5, 1, 48), (3, 0.5, 50)] if o < beats]
              if beats < 8 else [(0, beats, 52)],
    "ballad": lambda beats: [(0, beats, 46)],
}
ROLL = {"jazz": 0.03, "bossa": 0.01, "ballad": 0.18}  # 화음을 굴리는 간격(박)

# 드럼: 한 마디 안의 (박, 노트, 세기)
DRUMS = {
    "brush": [(0, 51, 44), (1, 51, 44), (1.5, 51, 32), (2, 51, 44), (3, 51, 44), (3.5, 51, 32),
              (1, 44, 40), (3, 44, 40), (1, 38, 30), (3, 38, 30), (0, 36, 36)],
    "bossa": [(o / 2, 42, 34 if o % 2 else 42) for o in range(8)]
             + [(0, 37, 44), (1.5, 37, 44), (3, 37, 44)]                       # 사이드스틱 클라베
             + [(0, 36, 40), (1.5, 36, 30), (2, 36, 40), (3.5, 36, 30)],
}


def midi(name):
    m = re.fullmatch(r"([A-G])([#b]?)(-?\d)", name)
    return PC[m[1]] + {"#": 1, "b": -1, "": 0}[m[2]] + 12 * (int(m[3]) + 1)


def bass_note(root):
    return 33 + (PC[root[0]] - (1 if root.endswith("b") else 0) - 33) % 12  # A1~G#2


def parse_melody(text):
    tok = text.replace("|", " ").split()
    return [(tok[i], float(tok[i + 1])) for i in range(0, len(tok), 2)]


def length(prog):
    return sum(b for _, b in prog)


def check():
    for name, prog, mel, *_ in FORM:
        assert length(prog) % 4 == 0, f"{name}: 진행이 마디 단위가 아님"
        if mel:
            got = sum(b for _, b in parse_melody(mel))
            assert got == length(prog), f"{name}: 멜로디 {got}박 ≠ 진행 {length(prog)}박"
    for root, voicing in CHORDS.values():
        [midi(n) for n in voicing], bass_note(root)
    for name, v in VARIANTS.items():
        for inst in (v["comp"][0], *v["leads"], v["drums"], v["pad"]):
            assert inst is None or inst in PALETTE, f"{name}: 팔레트에 없는 악기 {inst}"
        assert v["comp"][1] in COMP and (v["drums"] is None or v["drums"] in DRUMS)


def bass_line(beats, r, next_r, style):
    if style == "bossa" and beats == 4:
        return [(0, 1.5, r), (1.5, 0.5, r + 7), (2, 1.5, r + 7), (3.5, 0.5, r)]
    if beats == 2:
        return [(0, 1, r), (1, 1, r + 7)]
    if beats == 4 and style == "ballad":
        return [(0, 4, r)]
    if beats == 4 and next_r is not None:
        return [(0, 2, r), (2, 1, r + 7), (3, 1, next_r - 1)]  # 다음 근음 반음 아래 접근음
    if beats == 4:
        return [(0, 2, r), (2, 2, r + 7)]
    return [(0, beats, r)]


def build(v):
    rnd = random.Random(SEED)
    roles = {"comp": v["comp"][0], "bass": "bass", "lead1": v["leads"][0], "lead2": v["leads"][1],
             "pad": v["pad"], "drums": v["drums"]}
    events = {role: [] for role, inst in roles.items() if inst}
    style = v["comp"][1]

    def note(role, beat, dur, pitch, vel):
        if v["swing"] and abs(beat % 1 - 0.5) < 1e-9:
            beat += v["swing"]
        start = max(0, round(beat * TPB) + rnd.randint(-8, 8))
        end = start + max(30, round(dur * TPB) - 20)
        vel = max(1, min(127, vel + rnd.randint(-6, 6)))
        events[role] += [(start, mido.Message("note_on", channel=CH[role], note=pitch, velocity=vel)),
                         (end, mido.Message("note_off", channel=CH[role], note=pitch, velocity=0))]

    t = 0.0
    for name, prog, mel, lead, has_bass, has_drums in FORM:
        flat = [(t + sum(b for _, b in prog[:i]), c, b) for i, (c, b) in enumerate(prog)]
        for i, (at, chord, beats) in enumerate(flat):
            root, voicing = CHORDS[chord]
            for off, d, vel in COMP[style](beats):
                for k, p in enumerate(voicing):
                    note("comp", at + off + k * ROLL[style], d - k * ROLL[style], midi(p), vel)
            if "pad" in events:
                for p in voicing:
                    note("pad", at, beats, midi(p) + 12, 40)
            if has_bass:
                nxt = bass_note(CHORDS[flat[i + 1][1]][0]) if i + 1 < len(flat) else None
                for off, d, p in bass_line(beats, bass_note(root), nxt, style):
                    note("bass", at + off, d, p, 76)
        if has_drums and "drums" in events:
            bars = length(prog) // 4 - (2 if name == "outro" else 0)  # 엔딩 화음 2마디는 비움
            for bar in range(bars):
                for off, p, vel in DRUMS[v["drums"]]:
                    note("drums", t + bar * 4 + off, 0.5, p, vel)
        if mel:
            pos = t
            for p, d in parse_melody(mel):
                if p != "R":
                    note(f"lead{lead + 1}", pos, d, midi(p), 72)
                pos += d
        t += length(prog)

    mid = mido.MidiFile(ticks_per_beat=TPB)
    end_tick = round((t + 6) * TPB)  # 마지막 잔향이 잘리지 않도록 여유
    for role, evs_ in events.items():
        cfg, ch = PALETTE[roles[role]], CH[role]
        evs = [(0, mido.Message("program_change", channel=ch, program=cfg["program"])),
               (0, mido.Message("control_change", channel=ch, control=7, value=cfg["vol"])),
               (0, mido.Message("control_change", channel=ch, control=10, value=cfg["pan"])),
               (0, mido.Message("control_change", channel=ch, control=91, value=70))]
        if role == "comp":
            evs.append((0, mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(v["tempo"]))))
        evs += sorted(evs_, key=lambda e: (e[0], e[1].type == "note_on"))
        evs.append((end_tick, mido.Message("control_change", channel=ch, control=64, value=0)))
        track, last = mido.MidiTrack(), 0
        for tick, msg in evs:
            track.append(msg.copy(time=tick - last))
            last = tick
        mid.tracks.append(track)
    return mid


def render(name):
    OUT.mkdir(exist_ok=True)
    mid_path, wav, mp3, mp4 = (OUT / f"{name}.{e}" for e in ("mid", "wav", "mp3", "mp4"))
    build(VARIANTS[name]).save(mid_path)
    # 리미터(loudnorm)는 잡음을 만들어서 쓰지 않고 합성 게인으로 음량을 맞춘다
    subprocess.run(["fluidsynth", "-ni", "-g", str(GAIN), "-r", "44100", "-F", str(wav),
                    str(SOUNDFONT), str(mid_path)], check=True, capture_output=True)
    stats = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(wav), "-af", "astats=measure_perchannel=none",
                            "-f", "null", "-"], capture_output=True, text=True).stderr
    peak = float(re.search(r"Peak level dB: (-?[\d.]+|-inf)", stats)[1])
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-b:a", "256k", str(mp3)], check=True)
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                          str(mp3)], check=True, capture_output=True, text=True).stdout.strip()
    thumb = HERE / "thumbnail.png"
    if thumb.exists():
        # -shortest는 정지 이미지 루프에서 영상이 길게 남으므로 오디오 길이로 자른다
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", "1",
                        "-i", str(thumb), "-i", str(mp3), "-t", dur, "-vf", "scale=1920:1080",
                        "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "256k", str(mp4)], check=True)
    wav.unlink()
    warn = "  ⚠ 클리핑 위험: GAIN을 낮출 것" if peak > -1 else "  ⚠ 소리가 작거나 없음" if peak < -20 else ""
    print(f"완료: {name} ({float(dur):.0f}초, 피크 {peak:.1f}dB{', 영상 포함' if thumb.exists() else ''}){warn}")


if __name__ == "__main__":
    check()
    names = sys.argv[1:] or list(VARIANTS)
    unknown = [n for n in names if n not in VARIANTS]
    if unknown:
        sys.exit(f"없는 바리에이션: {', '.join(unknown)} (가능: {', '.join(VARIANTS)})")
    for name in names:
        render(name)
