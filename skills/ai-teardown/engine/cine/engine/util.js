// 时间、缓动、随机数：全片所有动画都是「时间 t 的纯函数」，这里的工具都没有内部状态。
export let TL = null;

export async function loadTimeline() {
  TL = await (await fetch("timeline.json")).json();
  return TL;
}

export const B = (bar) => bar * TL.bar;          // 小节 → 秒
export const toBar = (t) => t / TL.bar;          // 秒 → 小节

// 「ft」段的时间拖动：真实时间 → 场景时间（倒放、定格、快进），表由 tools/timeline.py 生成，配乐用的是同一张表
export function warp(t) {
  const w = TL.warp;
  if (t <= w.from || t >= w.to) return t;
  const x = (t - w.from) * w.rate, i = Math.floor(x), f = x - i;
  const a = w.table[i], b = w.table[Math.min(i + 1, w.table.length - 1)];
  return a + (b - a) * f;
}

export const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const lerp = (a, b, k) => a + (b - a) * k;
export const inv = (x, a, b) => clamp((x - a) / (b - a));
export const smooth = (x) => x * x * (3 - 2 * x);
export const eOutExpo = (x) => (x >= 1 ? 1 : 1 - Math.pow(2, -10 * x));
export const eInExpo = (x) => (x <= 0 ? 0 : Math.pow(2, 10 * x - 10));
export const eInOutExpo = (x) => (x <= 0 ? 0 : x >= 1 ? 1 : x < 0.5 ? Math.pow(2, 20 * x - 10) / 2 : (2 - Math.pow(2, -20 * x + 10)) / 2);
export const eOutCubic = (x) => 1 - Math.pow(1 - x, 3);
export const eInCubic = (x) => x * x * x;
export const eInOutCubic = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
export const eOutQuint = (x) => 1 - Math.pow(1 - x, 5);
export const eInOutQuint = (x) => (x < 0.5 ? 16 * x ** 5 : 1 - Math.pow(-2 * x + 2, 5) / 2);
export const eOutBack = (x, s = 1.70158) => 1 + (s + 1) * Math.pow(x - 1, 3) + s * Math.pow(x - 1, 2);

// 阻尼弹簧的阶跃响应：t 秒后从 0 走到 1，带过冲
export function spring(t, f = 2.2, z = 0.42) {
  if (t <= 0) return 0;
  const w = 2 * Math.PI * f, wd = w * Math.sqrt(1 - z * z);
  return 1 - Math.exp(-z * w * t) * (Math.cos(wd * t) + ((z * w) / wd) * Math.sin(wd * t));
}

// 一次性冲击的包络：at 之后快速起、指数衰减
export const hit = (t, at, decay = 9) => (t < at ? 0 : Math.exp(-(t - at) * decay));

export function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ── 泰语（ภาษาไทย）──
// 泰文的「显示字符」= 字素簇（Intl.Segmenter grapheme，上下元音、声调符号、ำ 跟着辅音算一个），不算空格和标点；
// 与 engine/scripts/thtext.py 的 display_len 同一个口径。Thai display chars = grapheme clusters minus spaces/punctuation.
const TH_RE = /[\u0E00-\u0E7F]/;
export const hasThai = (s) => TH_RE.test(String(s ?? ""));
const _seg = {};
const seg = (g) => (_seg[g] ||= new Intl.Segmenter("th", { granularity: g }));
export function thLen(s) {
  let n = 0;
  for (const { segment: c } of seg("grapheme").segment(String(s ?? ""))) if (!/^[\s\p{P}\u200B]/u.test(c)) n++;
  return n;
}
// 按泰语词边界切开：每个词一个不换行的 span，词之间放 <wbr>，所以只会在词边界换行（不会把一个词、一个字素簇拆到两行）
// Thai has no spaces between words: wrap each Intl.Segmenter word in a nowrap span with <wbr> between, so lines break only at word boundaries.
const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
export function thWrap(text) {
  const out = [];
  for (const { segment: w } of seg("word").segment(String(text))) out.push(/^\s+$/.test(w) ? w : `<span style="white-space:nowrap">${esc(w)}</span><wbr>`);
  return out.join("");
}
// 文字里有泰文：加 th 类（index.html 里 .th 把字距归零、用 Noto Sans Thai），纯文本再按词边界包起来
export function thai(node, html) {
  if (!hasThai(html)) return node;
  node.classList.add("th");
  if (!/[<&]/.test(html)) node.innerHTML = thWrap(html);
  return node;
}

// 小 DOM 工具
export function el(parent, cls = "", style = "", html = "") {
  const d = document.createElement("div");
  if (cls) d.className = cls;
  if (style) d.style.cssText = style;
  if (html) { d.innerHTML = html; thai(d, String(html)); }
  parent.appendChild(d);
  return d;
}

export function css(node, o) {
  for (const k in o) {
    const v = o[k];
    if (node.__s && node.__s[k] === v) continue;
    (node.__s ||= {})[k] = v;
    node.style[k] = v;
  }
}
