"""렌더된 MIDI 자동 점검 — AI가 소리를 듣지 못하는 대신 숫자로 기계적인 결함을 찾는다.

studio.py analyze가 .venv 파이썬으로 실행한다(mido 필요): python scripts/analyze.py <mid>...
song.py가 넣은 트랙 이름(역할)과 섹션 마커를 기준으로 본다.
"""
import statistics
import sys

import mido

NAMES = "C C# D Eb E F F# G Ab A Bb B".split()
LEADS, ACCOMP = ("lead1", "lead2"), ("comp", "pad")


def name(n):
    return f"{NAMES[n % 12]}{n // 12 - 1}"


def load(path):
    """역할별 [(시작, 끝, 음, 세기)]와 [(틱, 섹션 이름)]."""
    mid = mido.MidiFile(path)
    notes, marks = {}, []
    for tr in mid.tracks:
        t, held = 0, {}
        for m in tr:
            t += m.time
            if m.type == "marker":
                marks.append((t, m.text))
            elif m.type == "note_on" and m.velocity:
                held[m.note] = (t, m.velocity)
            elif m.type in ("note_on", "note_off") and m.note in held:
                s, v = held.pop(m.note)
                notes.setdefault(tr.name, []).append((s, t, m.note, v))
    return mid.ticks_per_beat, notes, sorted(marks)


def section_of(tick, marks):
    return next((n for t, n in reversed(marks) if t <= tick), "?")


def analyze(path):
    tpb, notes, marks = load(path)
    bar = 4 * tpb
    warns = []
    print(f"\n■ {path}")
    print("역할      음수   음역          세기 평균±편차(최소~최대)")
    for role, ns in notes.items():
        vel = [n[3] for n in ns]
        sd = statistics.pstdev(vel)
        lo, hi = min(n[2] for n in ns), max(n[2] for n in ns)
        print(f"{role:8} {len(ns):5}   {name(lo):>4}~{name(hi):<5}  {statistics.mean(vel):5.1f}±{sd:4.1f} ({min(vel)}~{max(vel)})")
        if role != "drums" and sd < 4:
            warns.append(f"{role}: 세기 변화가 거의 없음(편차 {sd:.1f}) → 기계적으로 들림")

    # 멜로디 시작 순간에 2반음 이내로 울리는 반주 음이 있으면 멜로디가 묻히거나 부딪힌다
    lead = [n for r in LEADS for n in notes.get(r, [])]
    acc = [n for r in ACCOMP for n in notes.get(r, [])]
    if lead and acc:
        hit = sum(any(a[0] <= s < a[1] and 0 < abs(a[2] - p) <= 2 for a in acc) for s, _, p, _ in lead)
        pct = 100 * hit / len(lead)
        print(f"멜로디-반주 2반음 이내 겹침: {pct:.0f}% ({hit}/{len(lead)}음)")
        if pct > 25:
            warns.append(f"멜로디와 반주 음역이 겹침({pct:.0f}%) → 반주 보이싱을 내리거나 멜로디를 올릴 것")

    # 반복: 마디 단위 음 배열이 앞에서 나온 마디와 똑같은 비율
    for label, roles in (("멜로디", LEADS), ("드럼", ("drums",))):
        bars = {}
        for r in roles:
            for s, _, p, _ in notes.get(r, []):
                bars.setdefault(s // bar, []).append((s, p))
        sigs = [tuple(p for _, p in sorted(v)) for _, v in sorted(bars.items())]
        if sigs:
            rep = 100 * (1 - len(set(sigs)) / len(sigs))
            print(f"{label} 마디 반복률: {rep:.0f}% ({len(sigs)}마디 중 서로 다른 마디 {len(set(sigs))}개)")
            if label == "드럼" and rep > 90:
                warns.append("드럼이 거의 한 마디 루프 → 필인·섹션별 변형 추가")

    # 섹션별 밀도·세기: 에너지 곡선이 평평한지 본다
    if marks:
        print("섹션     마디당 음수  평균 세기")
        rows = []
        for i, (t0, sec) in enumerate(marks):
            t1 = marks[i + 1][0] if i + 1 < len(marks) else max(n[1] for ns in notes.values() for n in ns)
            ns = [n for v in notes.values() for n in v if t0 <= n[0] < t1]
            if ns:
                rows.append(statistics.mean(n[3] for n in ns))
                print(f"{sec:8} {len(ns) / max(1, (t1 - t0) / bar):9.1f}  {rows[-1]:9.1f}")
        if len(rows) > 2 and max(rows) - min(rows) < 4:
            warns.append("섹션 간 세기 차이가 작음 → FORM 에너지(1~3)를 섹션마다 다르게")

    print("\n".join(f"⚠ {w}" for w in warns) or "경고 없음")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        analyze(p)
