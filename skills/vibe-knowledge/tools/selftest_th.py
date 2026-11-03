#!/usr/bin/env python3
"""Thai mode self-test (offline). ชุดทดสอบโหมดภาษาไทย ไม่ต้องใช้อินเทอร์เน็ต

    python3 skills/vibe-knowledge/tools/selftest_th.py [--keep]

Checks, in a temporary workspace (removed afterwards unless --keep):
  1. Thai display-char counting (engine/scripts/thtext.py) on known cases; regex \\X agrees when installed;
     the browser unit (Intl.Segmenter via node) agrees when node is available.
  2. duration.py --lang th: Thai output, per-backend budgets, --json shape, Chinese output still Chinese.
  3. recommend.py on Thai topics: Thai keywords route to the expected styles, missing stills are reported.
  4. new_film.py --lang th into a temp workspace: Thai templates, Thai font in the series, no Desktop path.
  5. tts_th.py with the `say` backend (macOS) on a 2-beat narration: timings.json has the tts_mimo.py shape,
     chars cover every code point, cues land inside their beat, check_timings.py and speed.py accept it.
  6. narr.js Thai subtitles via node: every subtitle ≤ TH_SUB_MAX display chars, no word split mid-word.
Steps that need macOS `say` or `node` print SKIP when those are missing. Nothing goes to the network.
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
SKILL = TOOLS.parent
AT = SKILL.parent / "ai-teardown"
sys.path.insert(0, str(AT / "engine/scripts"))
import thtext  # noqa: E402

PY = sys.executable
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    return ok


def skip(name, why):
    results.append((name, None))
    print(f"SKIP  {name}  — {why}")


def run(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


def t_counting():
    cases = {"ที่นี่": 2, "กำลัง": 3, "เขียน": 4, "น้ำ": 1, "ปั้น": 2, "กุ้ง": 2, "ผู้": 1, "ฤๅษี": 3,
             "ภาษาไทย": 7, "ไม่": 2, "เพราะ": 5, "สี่สิบสอง ครั้ง": 9, "AI 42": 4, "本福特定律": 5, "": 0,
             "ครั้ง!": 3, "เรื่อย ๆ": 5}
    bad = {k: (thtext.display_len(k, use_regex=False), v) for k, v in cases.items() if thtext.display_len(k, use_regex=False) != v}
    check("thtext.display_len fallback on 17 known cases", not bad, str(bad) if bad else "ที่นี่=2 กำลัง=3 เขียน=4 …")
    w = thtext.weights("กุ้ง ที่", 1.5)
    check("timing weights: marks 0, consonants 1, space = space weight", w == [1, 0, 0, 1, 1.5, 1, 0, 0], str(w))
    check("words fallback keeps ไม้ยมก with its word", [("เรื่อย ๆ")] == ["เรื่อย ๆ"[a:b] for a, b in thtext.words("เรื่อย ๆ")][:1])
    if thtext._regex is not None:
        diff = [k for k in cases if [k[a:b] for a, b in thtext.clusters(k, True)] != [k[a:b] for a, b in thtext.clusters(k, False)]]
        check("regex \\X agrees with fallback", not diff, str(diff))
    else:
        skip("regex \\X agrees with fallback", "`regex` module not installed (fallback in use)")
    if shutil.which("node"):
        js = ("const g=new Intl.Segmenter('th',{granularity:'grapheme'});const c=JSON.parse(process.argv[1]);const o={};"
              "for(const k of Object.keys(c)){let n=0;for(const s of g.segment(k)){if(!/^[\\s\\p{P}\\u200B]/u.test(s.segment))n++;}o[k]=n;}"
              "console.log(JSON.stringify(o))")
        r = run(["node", "-e", js, json.dumps(cases, ensure_ascii=False)])
        got = json.loads(r.stdout) if r.returncode == 0 else {}
        diff = {k: (got.get(k), v) for k, v in cases.items() if got.get(k) != v}
        check("browser unit (Intl.Segmenter) agrees", r.returncode == 0 and not diff, str(diff) if diff else "")
    else:
        skip("browser unit (Intl.Segmenter) agrees", "node not found")


def t_duration():
    r = run([PY, str(TOOLS / "duration.py"), "--scores", "1,0,2,2,1", "--template", "B", "--lang", "th"])
    check("duration.py --lang th prints Thai", r.returncode == 0 and "ความซับซ้อน 6/10" in r.stdout and "มาตรฐาน 2:30–3:00 (แนะนำ)" in r.stdout, r.stdout.splitlines()[0] if r.stdout else r.stderr[-200:])
    j = json.loads(run([PY, str(TOOLS / "duration.py"), "--scores", "1,1,1,1,1", "--lang", "th", "--backend", "edge-m", "--json"]).stdout)
    check("duration.py --lang th --json: measured edge-m rate and 4 options",
          j["rate"]["chars_per_sec"] == [11.2, 12.4] and len(j["options"]) == 4 and j["recommend"] == "มาตรฐาน", str(j["rate"]))
    s = run([PY, str(TOOLS / "duration.py"), "--scores", "1,1,1,1,1", "--lang", "th"]).stdout
    check("say budget: standard tier 1080–1580 display chars", "1080–1580" in s)
    z = run([PY, str(TOOLS / "duration.py"), "--scores", "1,0,2,2,1", "--template", "B"]).stdout
    check("duration.py default is still Chinese", "复杂度 6/10" in z and "约 820–1080 字" in z)


def t_recommend():
    cases = [("สงกรานต์สมัยอยุธยาเล่นน้ำกันยังไง", "thaimural"), ("ก๋วยเตี๋ยวชามละห้าบาทหายไปไหน ค่าครองชีพ", "thaisign"),
             ("นิทานพื้นบ้านหนังตะลุง", "nangtalung"), ("ทำไมบัญชีปลอมโดนจับได้ ความน่าจะเป็น", "starfield"),
             ("หมดไฟในการทำงาน มนุษย์เงินเดือน", "darkgold")]
    for topic, want in cases:
        r = json.loads(run([PY, str(TOOLS / "recommend.py"), topic, "--json"]).stdout)
        check(f"recommend.py \"{topic}\" → {want}", r and r[0]["key"] == want and r[0].get("lang") == "th", f"got {r[0]['key'] if r else None}")
    r = json.loads(run([PY, str(TOOLS / "recommend.py"), "นิทานพื้นบ้านหนังตะลุง", "--json"]).stdout)
    check("missing still.jpg reported as null, not a dead path", r[0]["still"] is None)
    z = run([PY, str(TOOLS / "recommend.py"), "为什么假账总被数字 1 出卖"]).stdout
    check("Chinese topic still prints Chinese", z.startswith("选题：") and "（推荐）" in z)


def t_new_film(ws):
    env = {**os.environ, "VK_WORKSPACE": str(ws)}
    r = run([PY, str(TOOLS / "new_film.py"), "01", "--template", "F", "--title", "ทดสอบ", "--lang", "th", "--series", "vk-th"], env=env)
    sd = ws / "examples/vk-th"
    L = sd / "lessons/01"
    ok = r.returncode == 0 and (L / "narration.json").exists()
    check("new_film.py --lang th creates the episode", ok, (r.stdout + r.stderr).strip().splitlines()[-1] if (r.stdout + r.stderr).strip() else "")
    if not ok:
        return None
    n = json.loads((L / "narration.json").read_text(encoding="utf-8"))
    check("Thai narration skeleton (voice.lang th, say Kanya, 9 beats)", n["voice"].get("lang") == "th" and n["voice"]["engine"] == "say" and len(n["beats"]) == 9)
    check("Thai facts template", "บัญชีข้อเท็จจริง" in (L / "facts.md").read_text(encoding="utf-8"))
    check("Thai font copied into the series", (sd / "cine/fonts/NotoSansThai-VF.ttf").exists())
    check("cine engine has Thai support (util.js thLen, index.html NotoThai)",
          "thLen" in (sd / "cine/engine/util.js").read_text(encoding="utf-8") and "NotoThai" in (sd / "cine/index.html").read_text(encoding="utf-8"))
    de = (sd / "cine/deliver.env").read_text(encoding="utf-8")
    check("delivery folder follows VK_WORKSPACE, not ~/Desktop", str(ws) in de and "Desktop" not in de)
    return sd


def t_tts(sd):
    if platform.system() != "Darwin" or not shutil.which("say"):
        skip("tts_th.py say backend", "macOS `say` not available"); return
    if "Kanya" not in run(["say", "-v", "?"]).stdout:
        skip("tts_th.py say backend", "Thai voice Kanya not installed (System Settings → Accessibility → Spoken Content)"); return
    L = sd / "lessons/02"
    L.mkdir(parents=True)
    (L / "narration.json").write_text(json.dumps({"voice": {"engine": "say", "voice": "Kanya", "lang": "th"}, "lexicon": {"AI": "เอไอ"}, "beats": [
        {"id": "B01", "narration": "[[q]]กระดาษบางแค่ศูนย์จุดหนึ่งมิลลิเมตร [[fold]]ต้องพับกี่ครั้งถึงจะไปถึงดวงจันทร์"},
        {"id": "B02", "narration": "คำตอบคือ[[n]]สี่สิบสองครั้ง [[ai]]แม้แต่ AI ก็ยังตอบผิดบ่อย"}]}, ensure_ascii=False), encoding="utf-8")
    ws = sd.parent.parent
    r = run([PY, str(ws / "scripts/tts_th.py"), str(L / "narration.json"), str(L / "build"), "--gap", "0.2", "--lead", "0.3"])
    tj = L / "build/timings.json"
    if not check("tts_th.py --backend say runs", r.returncode == 0 and tj.exists(), (r.stderr or r.stdout)[-300:] if r.returncode else r.stdout.strip().splitlines()[-1]):
        return
    t = json.loads(tj.read_text(encoding="utf-8"))
    beats = t["beats"]
    shape = all(set(b) >= {"file", "text", "start", "end", "duration", "words", "chars", "cues", "align"} for b in beats.values())
    check("timings.json has the tts_mimo.py shape + voice.lang th", shape and t["voice"]["lang"] == "th" and t["total"] > 0)
    check("chars: one time per code point, non-decreasing",
          all(len(b["chars"]) == len(b["text"]) and all(x <= y for x, y in zip(b["chars"], b["chars"][1:])) for b in beats.values()))
    check("cues inside their beat and in order", all(b["start"] <= v < b["end"] for b in beats.values() for v in b["cues"].values())
          and beats["B01"]["cues"]["q"] < beats["B01"]["cues"]["fold"] and beats["B02"]["cues"]["n"] < beats["B02"]["cues"]["ai"])
    check("per-beat audio and narration.wav written", all((L / "build" / b["file"]).exists() for b in beats.values()) and (L / "build/narration.wav").exists())
    c = run([PY, str(sd / "tools/check_timings.py"), "02"], cwd=sd)
    check("check_timings.py accepts it", c.returncode == 0 and "没有发现问题" in c.stdout, c.stdout.strip())
    s = run([PY, str(ws / "scripts/speed.py"), str(L), "1.1"])
    t2 = json.loads(tj.read_text(encoding="utf-8"))
    check("speed.py 1.1 rescales it", s.returncode == 0 and abs(t2["total"] - t["total"] / 1.1) < 0.01 and t2["voice"]["lang"] == "th")
    return tj


def t_subs(tj, sd):
    if not shutil.which("node"):
        skip("narr.js Thai subtitles", "node not found"); return
    if not tj:
        skip("narr.js Thai subtitles", "no Thai timings (tts step skipped)"); return
    js = ("const {Narr,TH_SUB_MAX}=await import(process.argv[1]);const {thLen}=await import(process.argv[2]);"
          "const fs=await import('node:fs');const t=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));const n=new Narr(t,0);"
          "const bad=n.subs.filter(s=>thLen(s.text)>TH_SUB_MAX);"
          "console.log(JSON.stringify({lang:n.lang,n:n.subs.length,bad:bad.map(s=>s.text),subs:n.subs.map(s=>s.text)}))")
    eng = sd / "cine/engine"
    r = run(["node", "--input-type=module", "-e", js, str(eng / "narr.js"), str(eng / "util.js"), str(tj)])
    if not check("narr.js loads Thai timings in node", r.returncode == 0, r.stderr[-300:]):
        return
    o = json.loads(r.stdout)
    check("Thai subtitles: lang th, every line ≤ TH_SUB_MAX display chars", o["lang"] == "th" and o["n"] >= 2 and not o["bad"], " | ".join(o["subs"]))


def main():
    print(f"vibe-knowledge Thai self-test · python {platform.python_version()} · {platform.system()}\n")
    tmp = Path(tempfile.mkdtemp(prefix="vk-selftest-th-"))
    try:
        t_counting(); t_duration(); t_recommend()
        sd = t_new_film(tmp / "ws")
        tj = t_tts(sd) if sd else None
        t_subs(tj, sd) if sd else None
    finally:
        if "--keep" in sys.argv:
            print(f"\nkept: {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)
    p = sum(1 for _, ok in results if ok); f = sum(1 for _, ok in results if ok is False); s = sum(1 for _, ok in results if ok is None)
    print(f"\n{p} passed, {f} failed, {s} skipped")
    sys.exit(1 if f else 0)


if __name__ == "__main__":
    main()
