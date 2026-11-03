#!/usr/bin/env python3
"""Thai text helpers shared by tts_th.py, vibe-knowledge/tools/duration.py and selftest_th.py.
泰语文字工具（tts_th.py、duration.py、selftest_th.py 共用）。

Unit used everywhere for Thai: the **display character** = one extended grapheme cluster (UAX #29),
not counting whitespace or punctuation. Above/below vowels and tone marks (ั ิ ี ึ ื ุ ู ็ ่ ้ ๊ ๋ ์ …)
join the consonant they sit on, and so does SARA AM (ำ), which UAX #29 classes as SpacingMark.
Leading vowels (เ แ โ ใ ไ), SARA A (ะ) and SARA AA (า) are their own clusters.
This is exactly what `Intl.Segmenter(..., {granularity: "grapheme"})` returns in the browser
(kit/know.js and the cine engine count the same way), so budgets measured here hold on screen.

    ที่นี่  → ที่ | นี่            = 2 display chars (5 code points)
    กำลัง → กำ | ลั | ง        = 3
    เขียน → เ | ขี | ย | น    = 4

The `regex` module's \\X is used when it is installed; otherwise a small fallback gives the same
result for Thai (and for Chinese, Latin and digits): a cluster continues across Mn/Me/Cf marks,
ZWJ sequences, SARA AM and LAO AM.

Word segmentation (for line breaking) is dictionary based. Python has no Thai dictionary built in:
`words()` uses PyThaiNLP or PyICU when one is installed, otherwise it splits only at spaces (Thai
writers put a space between phrases) and never inside a grapheme cluster. Real line breaking of
on-screen text happens in the browser with `Intl.Segmenter("th", {granularity: "word"})`.
"""
import re
import unicodedata

try:  # optional, more complete UAX #29 implementation
    import regex as _regex  # type: ignore
except Exception:  # noqa: BLE001
    _regex = None

THAI_RE = re.compile(r"[฀-๿]")
_JOIN = {"ำ", "ຳ", "‍"}   # SARA AM, LAO AM, ZWJ (SpacingMark / Extend in UAX #29)


def has_thai(s):
    return bool(THAI_RE.search(s or ""))


def _fallback_clusters(s):
    out, start = [], 0
    for i in range(1, len(s) + 1):
        if i == len(s):
            out.append((start, i))
            break
        c, prev = s[i], s[i - 1]
        joins = unicodedata.category(c) in ("Mn", "Me", "Mc") or c in _JOIN or prev == "‍" \
            or (unicodedata.category(c) == "Cf" and c != "​") or (prev == "\r" and c == "\n")
        if not joins:
            out.append((start, i))
            start = i
    return out if s else []


def clusters(s, use_regex=True):
    """[(i0, i1), …] code-point spans of the extended grapheme clusters of s."""
    if use_regex and _regex is not None:
        return [(m.start(), m.end()) for m in _regex.finditer(r"\X", s)]
    return _fallback_clusters(s)


def _counts(seg):
    c = seg[0]
    return not c.isspace() and not unicodedata.category(c).startswith("P") and c != "​"


def display_len(s, use_regex=True):
    """Display characters: grapheme clusters minus whitespace and punctuation (see module doc)."""
    return sum(1 for a, b in clusters(s, use_regex) if _counts(s[a:b]))


def cluster_index(s):
    """For each code point i of s: the start index of the cluster it belongs to.
    Used for timing: a tone mark or floating vowel gets its base consonant's time."""
    base = [0] * len(s)
    for a, b in clusters(s):
        for i in range(a, b):
            base[i] = a
    return base


def weights(s, space_weight=0.0):
    """Per code point weight for proportional timing: 1 for the first code point of a counted cluster,
    space_weight for whitespace, 0 for everything else (marks, punctuation)."""
    w = [0.0] * len(s)
    for a, b in clusters(s):
        seg = s[a:b]
        if seg[0].isspace():
            w[a] = space_weight
        elif _counts(seg):
            w[a] = 1.0
    return w


def words(s):
    """[(i0, i1), …] word spans. PyThaiNLP → PyICU → spaces only (never splits a grapheme cluster)."""
    try:
        from pythainlp.tokenize import word_tokenize  # type: ignore
        out, pos = [], 0
        for w in word_tokenize(s, keep_whitespace=True):
            if w and not w.isspace():
                out.append((pos, pos + len(w)))
            pos += len(w)
        return out
    except Exception:  # noqa: BLE001
        pass
    try:
        import icu  # type: ignore
        bi = icu.BreakIterator.createWordInstance(icu.Locale("th"))
        bi.setText(s)
        out, a = [], 0
        for b in bi:
            if s[a:b].strip():
                out.append((a, b))
            a = b
        return out
    except Exception:  # noqa: BLE001
        pass
    return [(m.start(), m.end()) for m in re.finditer(r"\S+(?:\s+\u0E46)*", s)]   # keep ไม้ยมก ๆ with its word


def segmenter_name():
    for mod, name in (("pythainlp", "pythainlp"), ("icu", "pyicu")):
        try:
            __import__(mod)
            return name
        except Exception:  # noqa: BLE001
            continue
    return "spaces"


if __name__ == "__main__":
    import sys
    t = " ".join(sys.argv[1:]) or "ที่นี่ กำลัง เขียน"
    print(f"{t!r}: {display_len(t)} display chars, clusters {[t[a:b] for a, b in clusters(t)]}, "
          f"words ({segmenter_name()}) {[t[a:b] for a, b in words(t)]}")
