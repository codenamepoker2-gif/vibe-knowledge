#!/usr/bin/env python3
"""按选题复杂度给时长建议（规则见 references/13-duration.md）。
python3 duration.py --scores 概念,前置,因果链,证据,分歧 [--template A-F] [--pick 档名或秒数] [--json]
五项各 0–2 分。输出复杂度、推荐档、四个时长选项（推荐档排第一，可直接放进 AskUserQuestion）。
--pick 传用户选的档（速览/精讲/标准/深挖）或秒数，检查跟复杂度是否差太多，差两级以上会打印提醒。

Thai / ภาษาไทย:  python3 duration.py --scores 1,0,2,2,1 --lang th [--backend say|edge-f|edge-m] [--speed 1.0] [--cps 9.5]
  เกณฑ์เดียวกัน แต่นับเป็น "ตัวอักษรที่แสดงผล" (display chars = grapheme clusters ไม่นับวรรณยุกต์/สระลอยแยก ไม่นับช่องว่าง)
  และใช้ความเร็วพูดที่วัดจริงของเสียงแต่ละตัว (tools/measure_th_rate.py, 2026-11-03, macOS):
    say (Kanya, ค่าเริ่มต้น -r)      7.2–8.8  เฉลี่ย 8.2 ตัว/วินาที
    edge-f (PremwadeeNeural, +0%)  11.9–14.4 เฉลี่ย 13.1
    edge-m (NiwatNeural, +0%)      11.2–12.4 เฉลี่ย 11.6
  ช่วงตัวอักษร = วินาทีต่ำสุด × ความเร็วต่ำสุด ถึง วินาทีสูงสุด × ความเร็วสูงสุด, คูณ --speed ถ้าจะเร่งด้วย speed.py
  --cps กำหนดความเร็วเองเป็นตัวเดียว (เช่นเสียง Gemini/MiMo ที่ยังไม่ได้วัด)"""
import json
import sys

DIMS = ["概念数", "前置知识", "因果链", "证据密度", "分歧/反转"]
TIERS = [
    {"name": "速览", "range": "45–60 秒", "sec": (45, 60), "beats": "5–7", "dots": "●○○○",
     "can": "一个钩子 + 一个结论 + 一个例子 + 回问", "cut": "前情、出处展开、对照组，反转最多一句"},
    {"name": "精讲", "range": "1:30–2:00", "sec": (90, 120), "beats": "7–9", "dots": "●●○○",
     "can": "主线讲完 + 1 个关键证据 + 1 次反转", "cut": "第二条证据、历史对照、误区纠正"},
    {"name": "标准", "range": "2:30–3:00", "sec": (150, 180), "beats": "10–12", "dots": "●●●○",
     "can": "主线 + 2–3 个证据 + 1 次反转 + 对照组 + 回问", "cut": "因果链里的次要环节，两说并列只留一处"},
    {"name": "深挖", "range": "3:30–5:00", "sec": (210, 300), "beats": "14–20", "dots": "●●●●",
     "can": "完整因果链（每步一个画面证据）+ 两说并列 + 误区纠正 + 延伸", "cut": "基本不砍，每章一个王炸防疲劳"},
]
HABIT = {"A": "猜谜概念片惯例 3:30–4:30", "B": "两难选择片系列惯例约 2:55", "C": "痛点原理片惯例 2:00–2:30",
         "D": "一条主线片惯例约 3:00", "E": "闯关片惯例 4–6 分钟", "F": "六面轮转片惯例 45–60 秒"}
CPS = 5.5  # 成片字/秒（下限），上限 6


# ── Thai mode (--lang th) ──  measured with tools/measure_th_rate.py: 6 paragraphs, per-paragraph min–max, mean
TH_RATES = {"say": (7.2, 8.8, 8.2, "macOS say -v Kanya"), "edge-f": (11.9, 14.4, 13.1, "edge-tts th-TH-PremwadeeNeural"),
            "edge-m": (11.2, 12.4, 11.6, "edge-tts th-TH-NiwatNeural")}
TH_DIMS = ["จำนวนแนวคิด", "ความรู้พื้นฐาน", "ห่วงโซ่เหตุผล", "ความหนาแน่นของหลักฐาน", "ข้อถกเถียง/จุดพลิก"]
TH_TIERS = [
    {"name": "สรุปไว", "range": "45–60 วินาที", "can": "ฮุก 1 + ข้อสรุป 1 + ตัวอย่าง 1 + ถามปิดท้าย", "cut": "ที่มา การขยายแหล่งอ้างอิง กลุ่มเปรียบเทียบ จุดพลิกได้แค่ประโยคเดียว"},
    {"name": "เจาะประเด็น", "range": "1:30–2:00", "can": "เล่าเส้นเรื่องหลักจบ + หลักฐานสำคัญ 1 ชิ้น + จุดพลิก 1 ครั้ง", "cut": "หลักฐานชิ้นที่สอง การเทียบกับประวัติศาสตร์ การแก้ความเข้าใจผิด"},
    {"name": "มาตรฐาน", "range": "2:30–3:00", "can": "เส้นเรื่องหลัก + หลักฐาน 2–3 ชิ้น + จุดพลิก 1 ครั้ง + กลุ่มเปรียบเทียบ + ถามปิดท้าย", "cut": "ขั้นรองในห่วงโซ่เหตุผล ความเห็นสองฝ่ายเหลือไว้จุดเดียว"},
    {"name": "เจาะลึก", "range": "3:30–5:00", "can": "ห่วงโซ่เหตุผลครบ (ทุกขั้นมีภาพหลักฐาน) + สองความเห็นคู่กัน + แก้ความเข้าใจผิด + ต่อยอด", "cut": "แทบไม่ตัด ให้มีช็อตเด็ดทุกบทกันคนดูล้า"},
]
TH_HABIT = {"A": "แบบทายแนวคิด มักยาว 3:30–4:30", "B": "แบบให้เลือกทางแยก ซีรีส์มักยาวราว 2:55", "C": "แบบปัญหาใกล้ตัว + หลักการ มักยาว 2:00–2:30",
            "D": "แบบเส้นเรื่องเดียว มักยาวราว 3:00", "E": "แบบผ่านด่าน มักยาว 4–6 นาที", "F": "แบบหกมุมมอง มักยาว 45–60 วินาที"}
TH_LEVEL = {0: "ง่าย", 1: "ปานกลาง", 2: "ซับซ้อน"}


def words(t):
    a, b = t["sec"]
    return f"{round(a * CPS / 10) * 10}–{round(b * 6 / 10) * 10}"


def level(score):
    return (0, "简单") if score <= 3 else (1, "中等") if score <= 6 else (2, "复杂")


def recommend(score, evid):
    lv = level(score)[0]
    if lv == 0:
        return 0 if evid == 0 else 1
    return 2 if lv == 1 else 3


def tier_of(pick):
    for i, t in enumerate(TIERS):
        if pick == t["name"]:
            return i
    s = float(pick)
    return min(range(4), key=lambda i: 0 if TIERS[i]["sec"][0] <= s <= TIERS[i]["sec"][1] else min(abs(s - x) for x in TIERS[i]["sec"]))


def main_th(a, sc, tpl):
    be = a[a.index("--backend") + 1] if "--backend" in a else "say"
    speed = float(a[a.index("--speed") + 1]) if "--speed" in a else 1.0
    if "--cps" in a:
        c = float(a[a.index("--cps") + 1]); lo = hi = mean = c; src = "--cps (กำหนดเอง)"
    else:
        if be not in TH_RATES:
            sys.exit("--backend ต้องเป็น " + " / ".join(TH_RATES))
        lo, hi, mean, src = TH_RATES[be]
    lo, hi, mean = lo * speed, hi * speed, mean * speed
    total = sum(sc); lv = level(total)[0]; lname = TH_LEVEL[lv]; rec = recommend(total, sc[3])
    order = [rec] + [i for i in range(4) if i != rec]
    opts = []
    for i in order:
        t, z = TH_TIERS[i], TIERS[i]
        a0, b0 = z["sec"]
        desc = (f"ประมาณ {round(a0 * lo / 10) * 10}–{round(b0 * hi / 10) * 10} ตัวอักษร · {z['beats']} ช่วง · ความละเอียด {z['dots']}"
                f"｜เล่าได้ถึง: {t['can']}｜ต้องตัด: {t['cut']}")
        if i == rec and tpl in TH_HABIT:
            desc += f"｜{TH_HABIT[tpl]}"
        if i == rec and lv == 2:
            desc += "｜หรือแตกเป็นสองตอน ตอนละแบบมาตรฐาน"
        if abs(i - rec) >= 2:
            desc += "｜⚠ ห่างจากความซับซ้อนของหัวข้อมาก"
        opts.append({"label": f"{t['name']} {t['range']}" + (" (แนะนำ)" if i == rec else ""), "description": desc})
    out = {"lang": "th", "score": total, "level": lname, "detail": dict(zip(TH_DIMS, sc)),
           "rate": {"backend": be if "--cps" not in a else "custom", "source": src, "chars_per_sec": [round(lo, 2), round(hi, 2)], "mean": round(mean, 2), "speed": speed},
           "question": f"หัวข้อนี้ค่อนข้าง{lname} ({total}/10) อยากได้คลิปยาวเท่าไร", "recommend": TH_TIERS[rec]["name"], "options": opts}
    if "--pick" in a:
        pk = a[a.index("--pick") + 1]
        p = next((i for i, t in enumerate(TH_TIERS) if t["name"] == pk), None)
        p = tier_of(pk) if p is None else p
        if abs(p - rec) >= 2:
            out["warning"] = ("เล่าได้แค่ข้อสรุป ส่วน \"ทำไม\" แทบไม่ได้เล่า คอมเมนต์มักจะมีคนบอกว่าไม่เข้าใจ" if p < rec else
                              "เนื้อหาไม่พอสำหรับความยาวนี้ จะมีช่วงซ้ำและภาพนิ่งนาน แนะนำให้สั้นลงหนึ่งระดับ หรือเพิ่มหัวข้อย่อยที่เกี่ยวข้อง")
    if "--json" in a:
        print(json.dumps(out, ensure_ascii=False, indent=1)); return
    print(f"ความซับซ้อน {total}/10 · {lname}　(" + ", ".join(f"{k} {v}" for k, v in out["detail"].items()) + ")")
    print(f"ความเร็วพูดที่ใช้คำนวณ: {lo:.1f}–{hi:.1f} ตัวอักษร/วินาที (เฉลี่ย {mean:.1f}) · {src}" + (f" × speed {speed}" if speed != 1 else ""))
    print(f"แนะนำ: {out['recommend']}\nคำถาม: {out['question']}")
    for o in opts:
        print(f"- {o['label']}\n    {o['description']}")
    if "warning" in out:
        print(f"⚠ เตือน: {out['warning']}")


def main():
    a = sys.argv
    if "--scores" not in a:
        sys.exit(__doc__)
    sc = [int(x) for x in a[a.index("--scores") + 1].split(",")]
    if len(sc) != 5 or any(x not in (0, 1, 2) for x in sc):
        sys.exit("--scores 要 5 个 0–2 的整数，顺序：" + "、".join(DIMS))
    tpl = a[a.index("--template") + 1].upper() if "--template" in a else None
    if "--lang" in a and a[a.index("--lang") + 1] == "th":
        return main_th(a, sc, tpl)
    total = sum(sc); lv, lname = level(total); rec = recommend(total, sc[3])
    order = [rec] + [i for i in range(4) if i != rec]
    opts = []
    for i in order:
        t = TIERS[i]
        desc = f"约 {words(t)} 字 · {t['beats']} 拍 · 细腻度 {t['dots']}｜能讲到：{t['can']}｜要砍掉：{t['cut']}"
        if i == rec and tpl in HABIT:
            desc += f"｜{HABIT[tpl]}"
        if i == rec and lv == 2:
            desc += "｜也可以拆成两期，每期标准档"
        if abs(i - rec) >= 2:
            desc += "｜⚠ 跟复杂度差得较远"
        opts.append({"label": f"{t['name']} {t['range']}" + ("（推荐）" if i == rec else ""), "description": desc})
    out = {"score": total, "level": lname, "detail": dict(zip(DIMS, sc)),
           "question": f"这个选题偏{lname}（{total}/10），想做多长？", "recommend": TIERS[rec]["name"], "options": opts}
    if "--pick" in a:
        p = tier_of(a[a.index("--pick") + 1]); want = rec
        if abs(p - want) >= 2:
            out["warning"] = ("只能讲到结论，「为什么」基本讲不到，评论区容易出现「没听懂」。" if p < want else
                              "内容撑不满这个时长，会出现重复和长时间静止的画面；建议往短调一档，或者加一个相关子话题。")
    if "--json" in a:
        print(json.dumps(out, ensure_ascii=False, indent=1)); return
    print(f"复杂度 {total}/10 · {lname}　（" + "，".join(f"{k} {v}" for k, v in out["detail"].items()) + "）")
    print(f"推荐：{out['recommend']}\n问题：{out['question']}")
    for o in opts:
        print(f"- {o['label']}\n    {o['description']}")
    if "warning" in out:
        print(f"⚠ 提醒：{out['warning']}")


if __name__ == "__main__":
    main()
