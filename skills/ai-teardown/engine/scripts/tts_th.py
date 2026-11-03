#!/usr/bin/env python3
"""Thai narration (ภาษาไทย) → per-beat audio + build/timings.json, same output contract as tts_mimo.py.
泰语配音：输出格式与 tts_mimo.py 完全一样（audio/<beat>.wav|.mp3、narration.wav、timings.json），
所以 check_timings.py、speed.py、voice_post.py、fit_bgm.py、cine finish.py 都照常能用。

    python3 scripts/tts_th.py <narration.json> <out_dir> [--backend say|edge|gemini|mimo] [--voice NAME]
                              [--rate R] [--gap 0.2] [--lead 0.3] [--jobs 3] [--space-weight 1.5] [--qa] [--reuse]

Backends (narration.json "voice": {"engine": "say", "voice": "Kanya", "lang": "th"}; command line wins):
  say     macOS `say -v Kanya` — default. Free, offline, nothing leaves the machine. No word timestamps.
          --rate = words per minute passed to `say -r` (default: the voice's own rate).
  edge    edge-tts (`uvx --from edge-tts`, or the edge_tts module if importable). Free neural voices
          th-TH-NiwatNeural (default, male) / th-TH-PremwadeeNeural (female). It uses Microsoft Edge's online
          read-aloud service without an official API agreement: the text is sent to Microsoft, it can change or
          stop working at any time, and no SLA applies. Gives real word timestamps (WordBoundary).
          --rate = edge rate string, e.g. "-10%".
  gemini  Gemini API TTS with your own GEMINI_API_KEY (model $GEMINI_TTS_MODEL, default gemini-3.8-flash-tts;
          voice default "Kore"; narration "voice.style" becomes the speech_metadata style). The free tier is free
          of charge but rate limited per project, and Google's pricing page marks free-tier data as used to improve
          their products. Not tested here (no key on the machine this was written on).
  mimo    Xiaomi MiMo (same key handling as tts_mimo.py). Thai support is unverified.
Timing: edge → word boundaries mapped back onto the original text; everything else → proportional by Thai
display chars (grapheme clusters, engine/scripts/thtext.py), spaces weighted --space-weight display chars.
[[cue]] markers get the time of the first display char after them. Tone marks / floating vowels share their
consonant's time. timings.json gets voice.lang = "th" (cine shows Thai subtitles from it).
--qa: read back each beat with faster-whisper (Thai) via uvx if the model ($VK_WHISPER_MODEL, default "small")
is already in the Hugging Face cache; add --qa-download to allow the first download (~0.5 GB for small).
Skips cleanly when uvx or the model is missing.
"""
import base64
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import thtext  # noqa: E402
from tts_mimo import strip_cues, apply_lexicon, probe  # noqa: E402  (same cue / lexicon semantics as the Chinese path)

BACKENDS = ("say", "edge", "gemini", "mimo")
DEFAULT_VOICE = {"say": "Kanya", "edge": "th-TH-NiwatNeural", "gemini": "Kore", "mimo": "茉莉"}
GEMINI_MODEL = os.environ.get("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts")
GEMINI_URL = os.environ.get("GEMINI_TTS_URL", "https://generativelanguage.googleapis.com/v1beta/interactions")
PUNCT_RE = re.compile(r"[\sฯ๚๛，。！？；：、,.!?;:()\"'“”‘’…—-]")


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, **kw)


# ── synthesis: each returns (raw audio path, [word boundaries {text, t, d}] or None) ──
def synth_say(text, voice, rate, out):
    f = out.with_suffix(".raw.aiff")
    run(["say", "-v", voice, *(["-r", str(rate)] if rate else []), "-o", str(f), text])
    return f, None


EDGE_HELPER = r"""
import asyncio, json, sys, edge_tts
a = json.loads(sys.stdin.read())
async def main():
    kw = {"boundary": "WordBoundary"}
    if a.get("rate"): kw["rate"] = a["rate"]
    c = edge_tts.Communicate(a["text"], a["voice"], **kw)
    marks = []
    with open(a["out"], "wb") as f:
        async for ch in c.stream():
            if ch["type"] == "audio": f.write(ch["data"])
            elif ch["type"] == "WordBoundary": marks.append({"text": ch["text"], "t": ch["offset"] / 1e7, "d": ch["duration"] / 1e7})
    print(json.dumps(marks, ensure_ascii=False))
asyncio.run(main())
"""


def synth_edge(text, voice, rate, out, tries=4):
    f = out.with_suffix(".raw.mp3")
    payload = json.dumps({"text": text, "voice": voice, "rate": rate, "out": str(f)}, ensure_ascii=False)
    try:
        import edge_tts  # noqa: F401
        cmd = [sys.executable, "-c", EDGE_HELPER]
    except Exception:  # noqa: BLE001
        if not shutil.which("uvx"):
            sys.exit("edge backend needs `uvx` (https://docs.astral.sh/uv/) or `pip install edge-tts`")
        cmd = ["uvx", "--from", "edge-tts", "python", "-c", EDGE_HELPER]
    last = ""
    for k in range(tries):
        r = subprocess.run(cmd, input=payload, capture_output=True, text=True)
        if r.returncode == 0 and f.exists() and f.stat().st_size > 0:
            return f, json.loads(r.stdout.strip().splitlines()[-1])
        last = (r.stderr or r.stdout)[-300:]
        time.sleep(2 * (k + 1))
    raise RuntimeError(f"edge-tts failed: {last}")


def synth_gemini(text, voice, style, out, tries=6):
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        sys.exit("gemini backend needs GEMINI_API_KEY (your own key from Google AI Studio)")
    item = {"type": "text", "text": text}
    if style:
        item["annotations"] = [{"type": "speech_metadata", "style": style}]
    body = {"model": GEMINI_MODEL, "input": [{"type": "user_input", "content": [item]}],
            "response_format": {"type": "audio"}, "generation_config": {"speech_config": [{"voice": voice}]}}
    last = ""
    for k in range(tries):
        req = urllib.request.Request(GEMINI_URL, data=json.dumps(body, ensure_ascii=False).encode(),
                                     headers={"x-goog-api-key": key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=240) as r:
                d = json.loads(r.read())
            audio = [c for s in d.get("steps", []) if s.get("type") == "model_output" for c in s.get("content", []) if c.get("type") == "audio"]
            if audio:
                f = out.with_suffix(".raw.wav")
                f.write_bytes(base64.b64decode(audio[-1]["data"]))
                return f, None
            last = json.dumps(d)[:300]
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read()[:300]!r}"
            if e.code not in (429, 500, 503):
                break
        except Exception as e:  # noqa: BLE001
            last = str(e)
        time.sleep(min(60, 10 * (k + 1)))
    raise RuntimeError(f"Gemini TTS failed: {last}")


def synth_mimo(text, voice, style, clone, base_dir, out):
    import tts_mimo
    key, base = tts_mimo.env()
    msgs = ([{"role": "user", "content": style}] if style else []) + [{"role": "assistant", "content": text}]
    if clone:
        ref = Path(clone) if Path(clone).is_absolute() else base_dir / clone
        body = {"model": "mimo-v2.5-tts-voiceclone", "messages": msgs,
                "audio": {"format": "wav", "voice": "data:audio/wav;base64," + base64.b64encode(ref.read_bytes()).decode()}}
    else:
        body = {"model": "mimo-v2.5-tts", "messages": msgs, "audio": {"format": "wav", "voice": voice}}
    d = tts_mimo.call(key, base, body)
    f = out.with_suffix(".raw.wav")
    f.write_bytes(base64.b64decode(d["choices"][0]["message"]["audio"]["data"]))
    return f, None


# ── audio post: trim head/tail silence (same -45 dB rule as tts_mimo), keep the offset for word timestamps ──
def trim(raw, wav):
    dur = probe(raw)
    r = subprocess.run(["ffmpeg", "-nostats", "-i", str(raw), "-af", "silencedetect=n=-45dB:d=0.05", "-f", "null", "-"], capture_output=True, text=True)
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    head = ends[0] - 0.05 if starts and starts[0] <= 0.01 and ends else 0.0
    tail = dur
    if starts and (len(ends) < len(starts) or ends[-1] >= dur - 0.02) and starts[-1] > head + 0.1:
        tail = min(dur, starts[-1] + 0.08)
    head = max(0.0, head)
    run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af", f"atrim={head:.4f}:{tail:.4f},asetpts=PTS-STARTPTS",
         "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)])
    return head


# ── timing ──
def char_map(clean, say):
    """index in the spoken text (after lexicon) → index in clean (replaced runs map proportionally)"""
    m = [None] * len(say)
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, clean, say, autojunk=False).get_opcodes():
        for j in range(j1, j2):
            if op == "equal":
                m[j] = i1 + (j - j1)
            elif i2 > i1:
                m[j] = i1 + (j - j1) * (i2 - i1) // (j2 - j1)
            else:
                m[j] = min(i1, len(clean) - 1) if clean else None
    return m


def timing(clean, say, dur, marks, head, space_weight):
    w = thtext.weights(clean, space_weight)
    known, spans = {}, []
    if marks:
        cmap, cur = char_map(clean, say), 0
        for mk in marks:
            j = say.find(mk["text"], cur)
            if j < 0:
                continue
            cur = j + len(mk["text"])
            idx = [cmap[k] for k in range(j, cur) if cmap[k] is not None and w[cmap[k]] == 1.0]
            if not idx:
                continue
            spans.append((min(idx), max(idx) + 1))
            t0, t1 = mk["t"] - head, mk["t"] - head + mk["d"]
            tot = sum(w[i] for i in idx)
            acc = 0.0
            for i in dict.fromkeys(idx):
                known[i] = max(0.0, min(dur, t0 + (t1 - t0) * acc / tot))
                acc += w[i]
    # monotonic anchors, then fill by weight between anchors: char i in (a, b) starts at
    # ta + (tb - ta) * weight(a .. i-1) / weight(a .. b-1)   (a = -1 means the beat start)
    anchors, last = [(-1, 0.0)], 0.0
    for i in sorted(known):
        last = max(last, known[i]); anchors.append((i, last))
    anchors.append((len(clean), dur))
    rel = [0.0] * len(clean)
    for (a, ta), (b, tb) in zip(anchors, anchors[1:]):
        lo = max(a, 0)
        tot = sum(w[lo:b]) or 1.0
        acc = w[a] if a >= 0 else 0.0
        for i in range(a + 1, b):
            rel[i] = ta + (tb - ta) * acc / tot
            acc += w[i]
        if b < len(clean):
            rel[b] = tb
    base = thtext.cluster_index(clean)
    rel = [rel[base[i]] for i in range(len(clean))]            # marks share their consonant's time
    for i in range(1, len(rel)):                                 # keep it non-decreasing
        rel[i] = max(rel[i], rel[i - 1])
    counted = sum(1 for x in w if x == 1.0)
    if spans:   # extend each word span over the marks of its last cluster
        cl = thtext.clusters(clean)
        ends = {a: b for a, b in cl}
        spans = [(a, max(ends.get(k, k + 1) for k in range(a, b) if k in ends)) for a, b in spans]
    return rel, (len(known) / counted if counted else 0.0), spans


# ── optional readback (faster-whisper, Thai) ──
WHISPER_HELPER = r"""
import json, sys
from faster_whisper import WhisperModel
a = json.loads(sys.stdin.read())
m = WhisperModel(a["model"], device="cpu", compute_type="int8")
out = {}
for f in a["files"]:
    segs, _ = m.transcribe(f, language="th", beam_size=5, initial_prompt=a.get("prompt") or None)
    out[f] = "".join(s.text for s in segs)
print(json.dumps(out, ensure_ascii=False))
"""


def whisper_cached(model):
    hub = Path(os.environ.get("HF_HOME", Path.home() / ".cache/huggingface")) / "hub"
    return any(hub.glob(f"models--*--faster-whisper-{model}")) or Path(model).exists()


def readback(files, allow_download=False):
    model = os.environ.get("VK_WHISPER_MODEL", "small")
    if not shutil.which("uvx"):
        return None, "readback skipped: uvx not found"
    if not (allow_download or whisper_cached(model)):
        return None, f"readback skipped: faster-whisper model '{model}' not in the Hugging Face cache (add --qa-download to fetch it once)"
    r = subprocess.run(["uvx", "--from", "faster-whisper", "python", "-c", WHISPER_HELPER],
                       input=json.dumps({"model": model, "files": [str(f) for f in files]}), capture_output=True, text=True)
    if r.returncode != 0:
        return None, "readback skipped: faster-whisper failed: " + (r.stderr or r.stdout)[-200:]
    return json.loads(r.stdout.strip().splitlines()[-1]), f"readback: faster-whisper {model}"


def similarity(a, b):
    f = lambda s: [s[x:y] for x, y in thtext.clusters(PUNCT_RE.sub("", s))]
    return difflib.SequenceMatcher(None, f(a), f(b), autojunk=False).ratio()


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    data = json.loads(src.read_text(encoding="utf-8"))
    vcfg = data.get("voice", {}) or {}
    backend = arg("--backend", vcfg.get("engine") if vcfg.get("engine") in BACKENDS else "say")
    if backend not in BACKENDS:
        sys.exit(f"--backend must be one of {BACKENDS}")
    voice = arg("--voice", vcfg.get("voice") if vcfg.get("engine") == backend and vcfg.get("voice") else DEFAULT_VOICE[backend])
    rate = arg("--rate", vcfg.get("rate"))
    style = vcfg.get("style", "") if backend in ("gemini", "mimo") else ""
    clone = vcfg.get("clone") if backend == "mimo" else None
    gap, lead = float(arg("--gap", 0.2)), float(arg("--lead", 0.3))
    jobs = int(arg("--jobs", 3 if backend == "say" else 2))
    space_w = float(arg("--space-weight", 1.5))
    if backend == "say" and not shutil.which("say"):
        sys.exit("say backend needs macOS (`say -v Kanya`); use --backend edge elsewhere")
    lexicon = data.get("lexicon", {})
    (out / "audio").mkdir(parents=True, exist_ok=True)
    t_start = time.time()

    J = []
    for b in data["beats"]:
        clean, cue_pos = strip_cues(b["narration"])
        say = apply_lexicon(clean, lexicon)
        digest = hashlib.md5(json.dumps([backend, voice, rate, style, clone, say], ensure_ascii=False).encode()).hexdigest()
        a = out / "audio" / b["id"]
        J.append({"b": b, "clean": clean, "say": say, "cue_pos": cue_pos, "digest": digest,
                  "wav": a.with_suffix(".wav"), "mp3": a.with_suffix(".mp3"), "key": a.with_suffix(".key"), "marks": a.with_suffix(".marks.json")})

    def synth(j):
        t0 = time.time()
        reuse = j["wav"].exists() and ("--reuse" in sys.argv or (j["key"].exists() and j["key"].read_text() == j["digest"]))
        if not reuse:
            base = j["wav"].with_suffix("")
            if backend == "say":
                raw, marks = synth_say(j["say"], voice, rate, base)
            elif backend == "edge":
                raw, marks = synth_edge(j["say"], voice, rate, base)
            elif backend == "gemini":
                raw, marks = synth_gemini(j["say"], voice, style, base)
            else:
                raw, marks = synth_mimo(j["say"], voice, style, clone, src.parent, base)
            head = trim(raw, j["wav"])
            raw.unlink()
            j["marks"].write_text(json.dumps({"head": head, "marks": marks}, ensure_ascii=False), encoding="utf-8")
            j["key"].write_text(j["digest"])
        run(["ffmpeg", "-v", "error", "-y", "-i", str(j["wav"]), "-b:a", "160k", str(j["mp3"])])
        mk = json.loads(j["marks"].read_text(encoding="utf-8")) if j["marks"].exists() else {"head": 0, "marks": None}
        j["dur"] = probe(j["wav"])
        j["rel"], j["cover"], j["spans"] = timing(j["clean"], j["say"], j["dur"], mk["marks"], mk["head"], space_w)
        j["mode"] = "word-boundary" if mk["marks"] else "proportional"
        j["reused"], j["synth_s"] = reuse, time.time() - t0

    with ThreadPoolExecutor(jobs) as ex:
        list(ex.map(synth, J))

    qa_note, heard = "", {}
    if "--qa" in sys.argv:
        res, qa_note = readback([j["wav"] for j in J], "--qa-download" in sys.argv)
        heard = res or {}

    timings = {"voice": {"engine": backend, "voice": voice, "rate": rate, "lang": "th", "style": style or None,
                         "clone": str(clone) if clone else None}, "beats": {}}
    t, parts, report = lead, [], []
    for j in J:
        b, clean, dur = j["b"], j["clean"], j["dur"]
        starts = [round(t + x, 3) for x in j["rel"]]
        end = round(t + dur, 3)
        words = []
        for i0, i1 in (j["spans"] or thtext.words(clean)):   # edge: its own word boundaries; else thtext.words
            nxt = next((starts[k] for k in range(i1, len(clean)) if starts[k] > starts[i0] and not clean[k].isspace()), end)
            words.append({"text": clean[i0:i1], "start": starts[i0], "end": min(nxt, end), "i0": i0, "i1": i1})
        w = thtext.weights(clean)
        cues = {}
        for name, k in j["cue_pos"].items():
            nxt = next((i for i in range(k, len(clean)) if w[i] > 0), None)
            cues[name] = starts[nxt] if nxt is not None else end
        timings["beats"][b["id"]] = {"file": f"audio/{b['id']}.mp3", "text": clean, "start": round(t, 3), "end": end,
                                     "duration": round(dur, 3), "words": words, "chars": starts, "cues": cues,
                                     "align": round(j["cover"], 3), "timing": j["mode"]}
        n = thtext.display_len(clean)
        status = "reused" if j["reused"] else f"synth {j['synth_s']:.1f}s"
        line = f"{b['id']}  {dur:5.2f}s  {n:3d} display chars  {n / dur:5.2f}/s  {j['mode']} {j['cover']:.0%}  {status}"
        h = heard.get(str(j["wav"]))
        if h is not None:
            ratio = similarity(clean, h)
            line += f"  readback {ratio:.0%}" + ("  ⚠ check this beat" if ratio < 0.85 else "")
            report.append({"beat": b["id"], "heard": h, "ratio": round(ratio, 3)})
        print(line)
        parts.append((j["mp3"], t))
        t += dur + max(gap, b.get("gap", 0), b.get("min_hold_s", 0))
    total = round(t - gap + lead, 3)
    timings["total"] = total

    inputs, filters = [], []
    for i, (mp3, start) in enumerate(parts):
        inputs += ["-i", str(mp3)]
        filters.append(f"[{i}:a]aresample=48000,adelay={int(start * 1000)}:all=1[a{i}]")
    filters.append("".join(f"[a{i}]" for i in range(len(parts))) + f"amix=inputs={len(parts)}:normalize=0,apad=whole_dur={total},atrim=0:{total}[out]")
    run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(filters), "-map", "[out]", "-ac", "1", "-ar", "48000", str(out / "narration.wav")])
    (out / "timings.json").write_text(json.dumps(timings, ensure_ascii=False, indent=1), encoding="utf-8")
    if report:
        (out / "qa.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    if qa_note:
        print(qa_note)
    print(f"total {total:.2f}s → {out / 'timings.json'}  (backend {backend}, voice {voice}, {time.time() - t_start:.0f}s, jobs {jobs})")


if __name__ == "__main__":
    main()
