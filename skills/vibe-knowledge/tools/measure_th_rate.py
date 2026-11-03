#!/usr/bin/env python3
"""วัดความเร็วพูดภาษาไทย (display chars / second) ของเสียงฟรีแต่ละตัว — วิธีวัดที่ใช้ได้ตัวเลขใน duration.py --lang th
Measure the Thai speaking rate of each free TTS backend, in display chars per second.

    python3 measure_th_rate.py [--backends say,edge-f,edge-m] [--text paras.txt] [--out /tmp/vk-rate]

- Text: one paragraph per line (default: the six built-in paragraphs below; one has digits + an English term).
- Each paragraph is synthesised whole, leading/trailing silence trimmed with the same ffmpeg filter
  tts_mimo.py / tts_th.py use (-45 dB), pauses inside the paragraph are kept (they are part of the pace).
- Rate = display_len(paragraph) / trimmed duration. display_len = grapheme clusters minus spaces and
  punctuation (engine/scripts/thtext.py), the same unit duration.py and know.js count.
- say: macOS `say -v Kanya` at its default rate (no -r). edge-f / edge-m: edge-tts th-TH-PremwadeeNeural /
  th-TH-NiwatNeural at rate +0% via `uvx --from edge-tts` (online, unofficial use of Microsoft's read-aloud service).
Prints per-paragraph rates, mean (total chars / total seconds) and range.
"""
import shutil
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ai-teardown/engine/scripts"))
import thtext  # noqa: E402

PARAS = [
    "ลองนึกภาพว่าคุณมีกระดาษแผ่นหนึ่ง บางแค่ศูนย์จุดหนึ่งมิลลิเมตร ถ้าพับครึ่งไปเรื่อย ๆ ต้องพับกี่ครั้งถึงจะสูงไปถึงดวงจันทร์ คำตอบอาจทำให้คุณประหลาดใจ เพราะใช้แค่สี่สิบสองครั้งเท่านั้น",
    "ในสมัยก่อนที่ยังไม่มีตู้เย็น คนกรุงเทพฯ เก็บอาหารให้อยู่ได้นานด้วยการตากแห้ง หมักเกลือ และดองน้ำปลา วิธีเหล่านี้ไม่ได้เกิดขึ้นเพราะความบังเอิญ แต่เป็นความรู้ที่สะสมต่อกันมาหลายร้อยปี",
    "ทำไมนักบัญชีถึงจับบัญชีปลอมได้จากตัวเลขหลักแรก กฎของเบนฟอร์ดบอกว่าในข้อมูลจริงหลายชนิด เลขหนึ่งจะขึ้นต้นบ่อยเกือบหนึ่งในสามของทั้งหมด ส่วนเลขเก้าขึ้นต้นไม่ถึงห้าเปอร์เซ็นต์",
    "ช้างไทยตัวหนึ่งกินอาหารวันละประมาณสองร้อยกิโลกรัม และดื่มน้ำอีกหลายสิบลิตร ถ้าเลี้ยงในเมือง ค่าอาหารต่อเดือนจึงสูงกว่าที่หลายคนคิดไว้มาก",
    "ปี 2026 มีคนใช้ AI ช่วยเขียนโค้ดมากกว่าเดิมหลายเท่า แต่เครื่องมือที่ดีที่สุดก็ยังต้องมีคนตรวจงาน เพราะโมเดลภาษาตอบผิดได้อย่างมั่นใจ",
    "ลองหยุดคิดสักครู่ ถ้าคุณต้องเลือกระหว่างเงินหนึ่งล้านบาทวันนี้ กับเงินที่เพิ่มขึ้นเท่าตัวทุกวันเป็นเวลาหนึ่งเดือน โดยเริ่มจากหนึ่งสตางค์ คุณจะเลือกอะไร",
]
EDGE = {"edge-f": "th-TH-PremwadeeNeural", "edge-m": "th-TH-NiwatNeural"}
TRIM = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,areverse,"
        "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,areverse")


def arg(n, d):
    return sys.argv[sys.argv.index(n) + 1] if n in sys.argv else d


def dur(src, td):
    out = Path(td) / (Path(src).stem + ".trim.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-af", TRIM, "-ar", "48000", "-ac", "1", str(out)], check=True)
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
                                capture_output=True, text=True, check=True).stdout)


def synth(backend, text, out):
    if backend == "say":
        subprocess.run(["say", "-v", "Kanya", "-o", str(out) + ".aiff", text], check=True)
        return str(out) + ".aiff"
    subprocess.run(["uvx", "--from", "edge-tts", "edge-tts", "--voice", EDGE[backend], "--text", text,
                    "--write-media", str(out) + ".mp3"], check=True, capture_output=True)
    return str(out) + ".mp3"


def main():
    paras = Path(arg("--text", "")).read_text(encoding="utf-8").splitlines() if "--text" in sys.argv else PARAS
    paras = [p.strip() for p in paras if p.strip()]
    backends = arg("--backends", "say,edge-f,edge-m").split(",")
    keep = arg("--out", None)
    td = keep or tempfile.mkdtemp(prefix="vk-rate-")
    Path(td).mkdir(parents=True, exist_ok=True)
    for be in backends:
        if be == "say" and not shutil.which("say"):
            print(f"{be}: skipped (no macOS say)"); continue
        if be.startswith("edge") and not shutil.which("uvx"):
            print(f"{be}: skipped (no uvx)"); continue
        rates, C, D = [], 0, 0.0
        for i, p in enumerate(paras, 1):
            f = synth(be, p, Path(td) / f"{be}_{i}")
            c, d = thtext.display_len(p), dur(f, td)
            rates.append(c / d); C += c; D += d
        print(f"{be:7s} mean {C / D:5.2f} display chars/s  range {min(rates):.2f}–{max(rates):.2f}  "
              f"median {statistics.median(rates):.2f}  ({len(paras)} paragraphs, {C} chars, {D:.1f} s)  per-paragraph: "
              + " ".join(f"{r:.2f}" for r in rates))
    if not keep:
        shutil.rmtree(td, ignore_errors=True)


if __name__ == "__main__":
    main()
