#!/usr/bin/env python3
"""prompt-to-midi CLI — init / doctor / new / render / analyze. 표준 라이브러리만 쓴다(시스템 python3로 실행).

    python3 scripts/studio.py init                  # 환경 구축(멱등)
    python3 scripts/studio.py doctor                # 환경 진단, 실패 시 종료코드 1
    python3 scripts/studio.py new <slug> [--from <기존곡>]
    python3 scripts/studio.py render <slug> [바리에이션...]
    python3 scripts/studio.py analyze <slug> [바리에이션...]   # 렌더된 MIDI 자동 점검
"""
import argparse
import platform
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv"
PY = VENV / "bin" / "python"
SF2 = ROOT / "soundfonts" / "GeneralUser-GS.sf2"
SF2_URL = "https://github.com/mrbumpy409/GeneralUser-GS/raw/main/GeneralUser-GS.sf2"
# 피아노 전용 고음질 사운드폰트(Salamander Grand, CC-BY 3.0). 없으면 곡은 GM 피아노로 렌더된다
PIANO = ROOT / "soundfonts" / "SalamanderGrandPiano.sf2"
PIANO_URL = "https://freepats.zenvoid.org/Piano/SalamanderGrandPiano/SalamanderGrandPiano-SF2-V3+20200602.tar.xz"
TEMPLATE = ROOT / "templates" / "song.py"
SONGS = ROOT / "songs"
PIP_DEPS = ["mido>=1.3"]
SYSTEM_BINS = ["fluidsynth", "ffmpeg", "ffprobe"]
# 템플릿이 쓰는 프리셋 (bank, program)
REQUIRED_PRESETS = {(0, 0): "Piano", (0, 24): "Nylon Guitar", (0, 32): "Acoustic Bass",
                    (0, 49): "Slow Strings", (128, 32): "Jazz kit", (128, 40): "Brush kit"}


def install_hint():
    if platform.system() == "Darwin":
        return "brew install fluid-synth ffmpeg"
    return "sudo apt install fluidsynth ffmpeg   # 또는 배포판 패키지 매니저"


def valid_sf2(path):
    if not path.exists():
        return False
    with open(path, "rb") as f:
        head = f.read(12)
    return head[:4] == b"RIFF" and head[8:12] == b"sfbk"


def presets(path):
    """사운드폰트 pdta/phdr 청크에서 (bank, program) 집합을 읽는다."""
    d = path.read_bytes()
    i = 12
    while i + 8 <= len(d):
        cid, size = d[i:i + 4], struct.unpack("<I", d[i + 4:i + 8])[0]
        if cid == b"LIST" and d[i + 8:i + 12] == b"pdta":
            j = i + 12
            while j < i + 8 + size:
                sid, ssize = d[j:j + 4], struct.unpack("<I", d[j + 4:j + 8])[0]
                if sid == b"phdr":
                    recs = d[j + 8:j + 8 + ssize]
                    return {struct.unpack("<HH", recs[k + 20:k + 24])[::-1] for k in range(0, ssize, 38)}
                j += 8 + ssize + ssize % 2
        i += 8 + size + size % 2
    return set()


def init(_):
    if not PY.exists():
        print("· 가상환경 생성")
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    print("· 파이썬 패키지 설치:", *PIP_DEPS)
    subprocess.run([str(PY), "-m", "pip", "install", "-q", "--disable-pip-version-check", *PIP_DEPS], check=True)
    if not valid_sf2(SF2):
        print("· 사운드폰트 다운로드(약 32MB):", SF2_URL)
        SF2.parent.mkdir(exist_ok=True)
        tmp = SF2.with_suffix(".part")
        urllib.request.urlretrieve(SF2_URL, tmp)
        if not valid_sf2(tmp):
            tmp.unlink()
            print("❌ 받은 파일이 SoundFont가 아님. URL을 확인할 것")
            return 1
        tmp.rename(SF2)
    if not valid_sf2(PIANO):
        print("· 피아노 사운드폰트 다운로드(약 300MB, 풀면 1.3GB):", PIANO_URL)
        archive, tmp = PIANO.with_name("piano.tar.xz.part"), PIANO.with_suffix(".part")
        urllib.request.urlretrieve(PIANO_URL, archive)
        with tarfile.open(archive) as tf:
            member = next((m for m in tf.getmembers() if m.name.endswith(".sf2")), None)
            if member:  # 경로를 쓰지 않고 내용만 꺼낸다(압축 경로 조작 방지)
                with tf.extractfile(member) as src, open(tmp, "wb") as dst:
                    shutil.copyfileobj(src, dst)
        archive.unlink()
        if not valid_sf2(tmp):
            tmp.unlink(missing_ok=True)
            print("❌ 피아노 사운드폰트를 찾지 못함. URL을 확인할 것")
            return 1
        tmp.rename(PIANO)
    missing = [b for b in SYSTEM_BINS if not shutil.which(b)]
    if missing:
        print(f"❌ 시스템 도구 없음: {', '.join(missing)}\n   설치(사용자 승인 후): {install_hint()}")
        return 1
    print("✅ init 완료. 다음: python3 scripts/studio.py doctor")
    return 0


def test_render():
    """1음짜리 MIDI를 렌더링해 소리가 나는지 본다."""
    track = bytes.fromhex("00C000" "00903C64" "8360803C00" "00FF2F00")  # 피아노, C4 한 박
    mid = b"MThd" + struct.pack(">IHHH", 6, 0, 1, 480) + b"MTrk" + struct.pack(">I", len(track)) + track
    with tempfile.TemporaryDirectory() as d:
        mid_path, wav_path = Path(d) / "t.mid", Path(d) / "t.wav"
        mid_path.write_bytes(mid)
        r = subprocess.run(["fluidsynth", "-ni", "-r", "44100", "-F", str(wav_path), str(SF2), str(mid_path)],
                           capture_output=True)
        if r.returncode or not wav_path.exists():
            return False
        with wave.open(str(wav_path)) as w:
            return any(w.readframes(w.getnframes()))


def doctor(_):
    checks = [("Python 3.10+", sys.version_info >= (3, 10), "python3 업그레이드")]
    checks.append(("가상환경 + mido", PY.exists() and subprocess.run([str(PY), "-c", "import mido"],
                                                                     capture_output=True).returncode == 0,
                   "python3 scripts/studio.py init"))
    for b in SYSTEM_BINS:
        checks.append((f"{b} 설치", bool(shutil.which(b)), install_hint()))
    if shutil.which("ffmpeg"):
        enc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
        checks.append(("ffmpeg libx264(mp4용)", "libx264" in enc, "libx264 포함 ffmpeg로 재설치"))
    sf_ok = valid_sf2(SF2)
    checks.append(("사운드폰트", sf_ok, "python3 scripts/studio.py init"))
    if sf_ok:
        have = presets(SF2)
        miss = [n for k, n in REQUIRED_PRESETS.items() if k not in have]
        checks.append(("필수 프리셋", not miss, f"사운드폰트에 없음: {', '.join(miss)}"))
        if shutil.which("fluidsynth"):
            checks.append(("테스트 렌더링(소리 출력)", test_render(), "fluidsynth 오류 — 직접 실행해 메시지 확인"))
    for name, ok, hint in checks:
        print(f"{'✅' if ok else '❌'} {name}" + ("" if ok else f" — 조치: {hint}"))
    # 선택 항목: 없어도 렌더는 되므로 실패로 치지 않는다
    print("✅ 피아노 사운드폰트(Salamander)" if valid_sf2(PIANO) else
          "⚠ 피아노 사운드폰트(Salamander) 없음 — GM 피아노로 렌더됨. 받으려면: python3 scripts/studio.py init")
    ok = all(c[1] for c in checks)
    print("정상" if ok else "문제 있음: 위 조치 후 doctor 재실행")
    return 0 if ok else 1


def slug_type(s):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", s):
        raise argparse.ArgumentTypeError("slug는 소문자·숫자·하이픈만 (예: winter-lofi)")
    return s


def new(a):
    dst = SONGS / a.slug / "song.py"
    if dst.exists():
        print(f"❌ 이미 있음(덮어쓰지 않음): {dst}")
        return 1
    src = SONGS / a.src / "song.py" if a.src else TEMPLATE
    if not src.exists():
        print(f"❌ 원본 없음: {src}")
        return 1
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dst)
    print(f"✅ 생성: {dst.relative_to(ROOT)}")
    return 0


def render(a):
    song = SONGS / a.slug / "song.py"
    if not song.exists():
        print(f"❌ 곡 없음: {song.relative_to(ROOT)} — 먼저 new")
        return 1
    return subprocess.run([str(PY), str(song), *a.variants]).returncode


def analyze(a):
    out = SONGS / a.slug / "out"
    mids = [out / f"{v}.mid" for v in a.variants] or sorted(out.glob("*.mid"))
    missing = [m for m in mids if not m.exists()]
    if not mids or missing:
        print(f"❌ 렌더 결과 없음: {', '.join(m.name for m in missing) or out.relative_to(ROOT)} — 먼저 render")
        return 1
    return subprocess.run([str(PY), str(ROOT / "scripts" / "analyze.py"), *map(str, mids)]).returncode


def main():
    p = argparse.ArgumentParser(description="prompt-to-midi")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="환경 구축").set_defaults(fn=init)
    sub.add_parser("doctor", help="환경 진단").set_defaults(fn=doctor)
    n = sub.add_parser("new", help="새 곡 폴더 생성")
    n.add_argument("slug", type=slug_type)
    n.add_argument("--from", dest="src", type=slug_type, help="복제할 기존 곡 slug(생략 시 템플릿)")
    n.set_defaults(fn=new)
    r = sub.add_parser("render", help="곡 렌더링")
    r.add_argument("slug", type=slug_type)
    r.add_argument("variants", nargs="*", help="생략 시 전체 바리에이션")
    r.set_defaults(fn=render)
    z = sub.add_parser("analyze", help="렌더된 MIDI 자동 점검(음역 겹침·반복·세기)")
    z.add_argument("slug", type=slug_type)
    z.add_argument("variants", nargs="*", help="생략 시 out/의 전체 MIDI")
    z.set_defaults(fn=analyze)
    a = p.parse_args()
    sys.exit(a.fn(a))


if __name__ == "__main__":
    main()
