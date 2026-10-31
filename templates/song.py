"""<곡 제목> — <컨셉 한 줄: 분위기·장르·용도>

이 파일이 곡의 원본이다. 수정은 '곡 데이터' 블록에서만 한다(아래 엔진은 손대지 않아도 됨).
실행(저장소 루트에서): python3 scripts/studio.py render <slug> [바리에이션...]
결과: out/<바리에이션>.mid / .mp3 / .mp4(thumbnail.png가 있을 때만)
"""
import math
import random
import re
import subprocess
import sys
from pathlib import Path

import mido

HERE = Path(__file__).resolve().parent
SOUNDFONT = HERE.parents[1] / "soundfonts" / "GeneralUser-GS.sf2"
PIANO_SF = HERE.parents[1] / "soundfonts" / "UprightPianoKW.sf2"  # 있으면 피아노(0)만 이 음색으로
OUT = HERE / "out"

# ───────────── 곡 데이터 ─────────────
SEED = 42  # 사람이 연주한 듯한 흔들림 고정값(같은 값이면 같은 결과)
LOUDNESS = -14  # 목표 음량(LUFS). 유튜브·스트리밍 기준 -14, 잔잔한 곡에서 리미터가 많이 눌리면 -16

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

# 구성: (이름, 진행, 멜로디, 멜로디 담당(0=lead1, 1=lead2), 베이스, 드럼, 에너지)
# 에너지 1 잔잔 / 2 보통 / 3 고조(세기↑, 재즈 반주면 워킹베이스). 섹션 사이 드럼 필인은 자동
FORM = [
    ("intro", PROG_INTRO, None,      None, False, False, 1),
    ("A1",    PROG_A,     MEL_A,     0,    True,  True,  1),
    ("A2",    PROG_A,     MEL_A,     1,    True,  True,  2),
    ("B1",    PROG_B,     MEL_B,     0,    True,  True,  3),
    ("A3",    PROG_A,     MEL_A,     1,    True,  True,  2),
    ("B2",    PROG_B,     None,      None, True,  True,  3),   # 쉬어가는 반주 구간(워킹베이스)
    ("A4",    PROG_A,     MEL_A,     0,    True,  True,  2),
    ("outro", PROG_OUTRO, MEL_OUTRO, 0,    True,  True,  1),
]

# 악기 팔레트: GM 프로그램 번호, 볼륨
# 주의: 이 사운드폰트의 4 Tine EP(Rhodes)·11 비브라폰은 어택이 금속성이라 '깨지는 소리'로 들린다는 피드백이 있었음
PALETTE = {
    "piano":   dict(program=0,  vol=75),    # 업라이트 피아노(Upright KW)
    "guitar":  dict(program=24, vol=110),   # 나일론 기타
    "bass":    dict(program=32, vol=108),   # 어쿠스틱 베이스
    "strings": dict(program=49, vol=60),    # 느린 현악 패드
    "brush":   dict(program=40, vol=80),    # 드럼: 브러시 킷 (이름 = DRUMS 패턴 이름)
    "bossa":   dict(program=32, vol=72),    # 드럼: 재즈 킷
}

# 믹스: 역할별 팬(0 왼쪽~127 오른쪽), 리버브 보내기(0~127). 저음·드럼은 잔향을 적게 해야 탁해지지 않는다
MIX = {
    "comp":  dict(pan=44, rev=40),
    "bass":  dict(pan=64, rev=8),
    "lead1": dict(pan=76, rev=45),
    "lead2": dict(pan=70, rev=45),
    "pad":   dict(pan=64, rev=70),
    "drums": dict(pan=64, rev=25),
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
ENERGY = {1: 0.85, 2: 1.0, 3: 1.12}  # 섹션 에너지 → 세기 배율
FEEL = {"comp": 10, "bass": 0, "lead1": 6, "lead2": 6, "pad": 0, "drums": -6}  # 역할별 박 앞뒤 고정 오프셋(틱)

# 반주 주법: 코드 길이(박)별 후보 패턴, 코드마다 하나를 고른다. 패턴 = [(시작 박, 길이, 세기)]
COMP = {
    "jazz":   {4: [[(0, 2.4, 52), (3.5, 0.5, 42)], [(0, 1.4, 50), (1.5, 2, 46)], [(0, 0.9, 52), (2.5, 1.5, 46)]],
               2: [[(0, 1.8, 50)], [(0.5, 1.5, 46)]]},
    "bossa":  {4: [[(0, 1, 56), (1.5, 1, 48), (3, 0.5, 50)], [(0, 1, 56), (1.5, 1, 48), (2.5, 1.5, 50)]],
               2: [[(0, 1, 56), (1.5, 0.5, 48)]]},
    "ballad": {4: [[(0, 4, 46)]], 2: [[(0, 2, 46)]]},
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
# 필인: 다음 섹션으로 넘어가기 전 마지막 마디를 대신한다(DRUMS와 같은 이름)
FILLS = {
    "brush": [(0, 51, 44), (1, 51, 44), (2, 38, 34), (2.5, 38, 38), (3, 38, 44), (3.5, 38, 50), (0, 36, 36)],
    "bossa": [(o / 2, 42, 38) for o in range(4)]
             + [(2, 45, 50), (2.5, 45, 46), (3, 43, 50), (3.5, 41, 54), (0, 36, 40)],
}
CRASH = 49  # 에너지 3 섹션 첫 박


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
    for name, prog, mel, *_, energy in FORM:
        assert length(prog) % 4 == 0, f"{name}: 진행이 마디 단위가 아님"
        assert energy in ENERGY, f"{name}: 에너지는 1~3"
        if mel:
            got = sum(b for _, b in parse_melody(mel))
            assert got == length(prog), f"{name}: 멜로디 {got}박 ≠ 진행 {length(prog)}박"
    for root, voicing in CHORDS.values():
        [midi(n) for n in voicing], bass_note(root)
    assert fifth(40, {7, 10, 2}) == 52  # Em7b5: 베이스 5도 B가 Bb와 부딪혀 옥타브 E로
    for name, v in VARIANTS.items():
        for inst in (v["comp"][0], *v["leads"], v["drums"], v["pad"]):
            assert inst is None or inst in PALETTE, f"{name}: 팔레트에 없는 악기 {inst}"
        assert v["comp"][1] in COMP and (v["drums"] is None or v["drums"] in DRUMS and v["drums"] in FILLS)


def fifth(r, pcs):
    """5도가 화음 음과 반음으로 부딪히면(예: Em7b5의 Bb vs B) 옥타브로 대신한다."""
    return r + 12 if any((r + 7 - p) % 12 in (1, 11) for p in pcs) else r + 7


def bass_line(beats, r, next_r, style, pcs, walk):
    f = fifth(r, pcs)
    if style == "bossa" and beats == 4:
        return [(0, 1.5, r), (1.5, 0.5, f), (2, 1.5, f), (3.5, 0.5, r)]
    if beats == 2:
        return [(0, 1, r), (1, 1, f)]
    if beats == 4 and style == "ballad":
        return [(0, 4, r)]
    if beats == 4 and walk and next_r is not None:
        third = next((r + i for i in (3, 4) if (r + i) % 12 in pcs), r + 2)
        return [(0, 1, r), (1, 1, third), (2, 1, f), (3, 1, next_r - 1)]
    if beats == 4 and next_r is not None:
        return [(0, 2, r), (2, 1, f), (3, 1, next_r - 1)]  # 다음 근음 반음 아래 접근음
    if beats == 4:
        return [(0, 2, r), (2, 2, f)]
    return [(0, beats, r)]


def melody_vel(pitch, beat):
    """높은 음일수록, 마디 첫 박·정박일수록 세게 — 프레이즈에 굴곡을 준다."""
    return 68 + (pitch - 67) * 2 // 3 + (4 if beat % 4 == 0 else 1 if beat % 1 == 0 else -3)


def build(v):
    rnd = random.Random(SEED)
    roles = {"comp": v["comp"][0], "bass": "bass", "lead1": v["leads"][0], "lead2": v["leads"][1],
             "pad": v["pad"], "drums": v["drums"]}
    events = {role: [] for role, inst in roles.items() if inst}
    style, kit = v["comp"][1], v["drums"]
    drift, offsets = dict.fromkeys(CH, 0.0), {}

    def sw(beat):
        """스윙: 박 안의 시간을 휘어 8분 뒷박을 뒤로 민다(음 끝도 같이 휘므로 길이가 맞는다)."""
        whole, frac = divmod(beat, 1)
        s = v["swing"]
        return whole + (frac * (1 + 2 * s) if frac <= 0.5 else 0.5 + s + (frac - 0.5) * (1 - 2 * s))

    def tick(role, beat):
        # 사람 연주의 흔들림: 역할별 고정 밀고 당김 + 천천히 변하는 오차. 같은 박에 친 화음은 같이 움직인다
        if (role, beat) not in offsets:
            drift[role] = drift[role] * 0.8 + rnd.gauss(0, 4)
            offsets[role, beat] = FEEL[role] + round(drift[role])
        return round(sw(beat) * TPB) + offsets[role, beat]

    def note(role, beat, dur, pitch, vel, roll=0.0):
        start = max(0, tick(role, beat) + round(roll * TPB))
        end = max(start + 30, tick(role, beat) + round((sw(beat + dur) - sw(beat)) * TPB) - 20)
        vel = max(1, min(127, round(vel) + rnd.randint(-4, 4)))
        events[role] += [(start, mido.Message("note_on", channel=CH[role], note=pitch, velocity=vel)),
                         (end, mido.Message("note_off", channel=CH[role], note=pitch, velocity=0))]

    def cc(role, beat, control, value):
        events[role].append((round(sw(beat) * TPB), mido.Message("control_change", channel=CH[role],
                                                                 control=control, value=value)))

    starts = [sum(length(f[1]) for f in FORM[:i]) for i in range(len(FORM))]
    chords = [(s + sum(b for _, b in prog[:i]), c, b, sec)
              for sec, (s, (_, prog, *_)) in enumerate(zip(starts, FORM)) for i, (c, b) in enumerate(prog)]
    pedal = style != "bossa" and PALETTE[roles["comp"]]["program"] < 8  # 피아노류 반주만 페달
    for i, (at, chord, beats, sec) in enumerate(chords):
        _, _, _, _, has_bass, _, energy = FORM[sec]
        e = ENERGY[energy]
        root, voicing = CHORDS[chord]
        pcs = {midi(p) % 12 for p in voicing}
        if pedal:  # 코드가 바뀔 때 떼었다가 바로 다시 밟는다
            cc("comp", at, 64, 0)
            cc("comp", at + 0.1, 64, 127)
        pats = COMP[style].get(beats, [[(0, beats, 50)]])
        for off, d, vel in rnd.choice(pats):
            for k, p in enumerate(voicing):
                top = 6 if k == len(voicing) - 1 else 0  # 맨 윗음을 살짝 드러낸다
                note("comp", at + off, d, midi(p), (vel + top) * e, k * ROLL[style])
        if "pad" in events:
            for p in voicing:
                note("pad", at, beats, midi(p), 40 * e)  # 한 옥타브 위는 멜로디 음역과 겹쳐서 반주 음역에 둔다
            for j in range(beats * 2):  # 코드마다 부풀었다 가라앉는 익스프레션
                cc("pad", at + j / 2, 11, round(80 + 30 * math.sin(math.pi * j / (beats * 2))))
        if has_bass:
            nxt = bass_note(CHORDS[chords[i + 1][1]][0]) if i + 1 < len(chords) else None
            walk = energy == 3 and style == "jazz"
            for off, d, p in bass_line(beats, bass_note(root), nxt, style, pcs, walk):
                note("bass", at + off, d, p, 76 * e)

    for sec, (t, (name, prog, mel, lead, _, has_drums, energy)) in enumerate(zip(starts, FORM)):
        e = ENERGY[energy]
        if has_drums and "drums" in events:
            bars = length(prog) // 4 - (2 if name == "outro" else 0)  # 엔딩 화음 2마디는 비움
            fill = sec + 1 < len(FORM) and FORM[sec + 1][5]
            for bar in range(bars):
                for off, p, vel in FILLS[kit] if fill and bar == bars - 1 else DRUMS[kit]:
                    note("drums", t + bar * 4 + off, 0.5, p, vel * e)
            if energy == 3:
                note("drums", t, 2, CRASH, 50 * e)
        if mel:
            pos = t
            for p, d in parse_melody(mel):
                if p != "R":
                    note(f"lead{lead + 1}", pos, d, midi(p), melody_vel(midi(p), pos - t) * e)
                pos += d

    t = starts[-1] + length(FORM[-1][1])
    meta = [(round(sw(s) * TPB), mido.MetaMessage("marker", text=f[0])) for s, f in zip(starts, FORM)]
    meta.append((0, mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(v["tempo"]))))
    for j in range(16):  # 마지막 네 마디는 조금씩 느려진다(리타르단도)
        meta.append((round((t - 16 + j) * TPB), mido.MetaMessage(
            "set_tempo", tempo=mido.bpm2tempo(v["tempo"] * (1 - 0.25 * (j + 1) / 16)))))
    mid = mido.MidiFile(ticks_per_beat=TPB)
    end_tick = round((t + 6) * TPB)  # 마지막 잔향이 잘리지 않도록 여유
    for role, evs_ in events.items():
        cfg, ch = PALETTE[roles[role]], CH[role]
        evs = [(0, mido.MetaMessage("track_name", name=role)),
               (0, mido.Message("program_change", channel=ch, program=cfg["program"])),
               (0, mido.Message("control_change", channel=ch, control=7, value=cfg["vol"])),
               (0, mido.Message("control_change", channel=ch, control=10, value=MIX[role]["pan"])),
               (0, mido.Message("control_change", channel=ch, control=91, value=MIX[role]["rev"]))]
        if role == "comp":
            evs += meta
        evs += sorted(evs_, key=lambda e: (e[0], e[1].type == "note_on"))
        evs.append((end_tick, mido.Message("control_change", channel=ch, control=64, value=0)))
        evs.sort(key=lambda e: e[0])  # 안정 정렬: 같은 틱 안의 순서는 유지
        track, last = mido.MidiTrack(), 0
        for tk, msg in evs:
            track.append(msg.copy(time=tk - last))
            last = tk
        mid.tracks.append(track)
    return mid


def loudness(path):
    """ffmpeg ebur128로 (통합 음량 LUFS, 트루피크 dB)를 잰다."""
    log = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    summary = log[log.rfind("Summary:"):]
    return (float(re.search(r"I:\s+(-?[\d.]+) LUFS", summary)[1]),
            float(re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", summary)[1]))


def render(name):
    OUT.mkdir(exist_ok=True)
    mid_path, wav, mp3, mp4 = (OUT / f"{name}.{e}" for e in ("mid", "wav", "mp3", "mp4"))
    mid = build(VARIANTS[name])
    mid.save(mid_path)
    # 뒤에 읽은 사운드폰트가 우선한다 → 업라이트가 있으면 피아노(0)만 그걸로, 나머지는 GeneralUser
    fonts = [SOUNDFONT] + [PIANO_SF] * PIANO_SF.exists()
    subprocess.run(["fluidsynth", "-ni", "-O", "float", "-r", "44100", "-F", str(wav), *fonts, str(mid_path)],
                   check=True, capture_output=True)
    # 마스터링: 측정한 음량 차만큼 올리고 리미터로 피크를 막는다.
    # 1패스 loudnorm은 조용한 구간·잔향을 따로 끌어올려 잡음을 만들었으므로 고정 게인 + 리미터만 쓴다
    raw_lufs, raw_peak = loudness(wav)
    gain = LOUDNESS - raw_lufs
    chain = (f"highpass=f=30,volume={gain:.2f}dB,aresample=176400,"
             "alimiter=limit=0.84:attack=5:release=80:level=false:latency=1,aresample=44100,"
             f"afade=t=out:st={mid.length - 1:.2f}:d=1")
    # 탐 샘플 등은 들리지 않는 꼬리가 수십 초 이어져서 MIDI 길이에서 자른다
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-af", chain, "-t", f"{mid.length:.2f}",
                    "-b:a", "256k", str(mp3)], check=True)
    lufs, peak = loudness(mp3)
    squash = max(0.0, raw_peak + gain + 1.5)  # 리미터가 깎은 양(대략)
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
    warn = ("  ⚠ 소리가 없음" if raw_lufs < -60 else
            "  ⚠ 리미터가 많이 눌림: LOUDNESS를 낮출 것" if squash > 6 else
            "  ⚠ 피크가 높음" if peak > -0.5 else "")
    print(f"완료: {name} ({float(dur):.0f}초, {lufs:.1f} LUFS, 피크 {peak:.1f}dB, 리미터 -{squash:.1f}dB"
          f"{'' if PIANO_SF.exists() else ', GM 피아노'}{', 영상 포함' if thumb.exists() else ''}){warn}")


if __name__ == "__main__":
    check()
    names = sys.argv[1:] or list(VARIANTS)
    unknown = [n for n in names if n not in VARIANTS]
    if unknown:
        sys.exit(f"없는 바리에이션: {', '.join(unknown)} (가능: {', '.join(VARIANTS)})")
    for name in names:
        render(name)
