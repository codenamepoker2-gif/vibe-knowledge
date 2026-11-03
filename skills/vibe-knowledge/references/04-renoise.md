# 04 · Renoise 增强层：图、视频、配乐、音效

## 自带生成器（Bring your own generator · ใช้เครื่องมือสร้างภาพของตัวเอง）

增强档不一定要用 Renoise。镜头里要的只是**一张图或一段视频文件**，用什么工具生成都行：手动在网页上做、命令行工具、本地 ComfyUI、别的 MCP，或者 Renoise。assets.json 每一项用 `engine` 记下用了哪种：

| engine | 意思 |
|---|---|
| `manual` | 你自己在任何网页 / App 里生成，然后把文件放进来（默认） |
| `codex-imagen` | 用 Codex 一类的命令行 / 代理工具调用图像模型 |
| `grok` | 用 Grok Imagine（网页或 CLI）出图 / 出短视频 |
| `comfyui` | 本地或自己的服务器上跑 ComfyUI 工作流（Flux、Wan 等开源模型） |
| `renoise` | 走下面的 Renoise MCP 流程（按积分计费，先报价后生成） |

通用流程（四种都一样）：
1. 按「提示词写法」一节写好提示词（风格前缀 + 内容 + `no text, no letters, no watermark`），记进 assets.json 的 `prompt`。
2. 用你选的工具生成。**只有 `renoise` 需要先报价确认**；其他工具如果也收费，同样先跟用户说清楚再做。
3. 图片放进 `lessons/NN/assets/img/`，视频放进 `lessons/NN/assets/clips/`，文件名照 assets.json 的 `file`，`status` 改 `done`。
4. 视频拆帧：`python3 tools/clip2frames.py assets/clips/v01.mp4 assets/clips/v01 --fps 30` → film.js 里 `vclip(s, { dir: A("clips/v01"), n })`；图片直接 `plate(s, { src: A("img/a01.jpg") })`。
5. 画面角标照旧写「AI 示意图 / AI 生成画面」（泰文：`tag: "ภาพ AI"`），facts.md 记下用了哪个工具。

ภาษาไทย: ช็อต "เพิ่มพลัง" ต้องการแค่ไฟล์ภาพหรือวิดีโอ จะสร้างด้วยเครื่องมืออะไรก็ได้ ใส่ชื่อเครื่องมือไว้ในช่อง `engine` ของ assets.json (`manual` / `codex-imagen` / `grok` / `comfyui` / `renoise`) แล้วทำตามขั้นตอนเดียวกัน: เขียนพรอมต์ → สร้างภาพ → วางไฟล์ใน `assets/img/` หรือ `assets/clips/` ตามชื่อใน `file` → วิดีโอให้แตกเฟรมด้วย `clip2frames.py` → ใส่ใน film.js ด้วย `plate` / `vclip` และติดป้าย "ภาพ AI" ทุกครั้ง ข้อความภาษาไทยบนภาพให้โค้ดเขียนทับเสมอ เพราะตัวอักษรไทยที่ AI วาดมักผิด

所有生成都走 Renoise MCP（工具名 `mcp__…__estimate_cost / create_tasks / wait_tasks / download_results`）。
**花积分的硬规矩**：把整期的 assets.json 列成一张表（模型、提示词、参数、数量、estimate_cost 总价、余额）发给用户，**等用户在对话里明确说可以**才 create_tasks。宿主的工具授权弹窗不算确认；之前说过「直接生成」也不算。改了任何提示词、模型、数量就要重新报价确认。

## 接入 Renoise（基础档不需要；做增强档时缺了才引导）

**判断有没有**：直接调 `get_account`。
- 成功 → 一句话带过「Renoise 已连接，余额 X 积分」，继续干活。
- 工具不存在 / 报未连接 → 缺，按下面引导。
- 报「disabled in connector settings」→ 不是没装，是工具被关了，让用户去连接器设置里打开。
- 报未登录 / 授权过期 → 不用重装，重新登录授权（Claude 连接器点「Connect」；Codex `codex mcp login renoise`）。

**还没有账号 → 先注册：[https://renoise.ai/mcp](https://renoise.ai/mcp)**。给用户时就给这条不带追踪参数的链接（本分支去掉了原链接里的 utm 追踪参数，也不再要求原样转发带追踪的链接）。（ภาษาไทย: ให้ลิงก์นี้แบบไม่มีพารามิเตอร์ติดตามเสมอ）全部走浏览器登录授权，不用复制 API key。

| 用的是 | 怎么装 |
|---|---|
| **Claude Code** | 依次输入 `/plugin marketplace add ArcoCodes/renoise-plugins-official`、`/plugin install renoise@renoise-plugins-official`，首次调用时浏览器登录 |
| **Claude 桌面端 / claude.ai 网页** | 设置 → 连接器 → Add custom connector → 名称 `Renoise`，地址 `https://renoise.ai/api/public/mcp` → 登录 renoise.ai 点同意 |
| **Codex（CLI / 桌面）** | `codex mcp add renoise --url https://renoise.ai/api/public/mcp`，再 `codex mcp login renoise` |
| **OpenClaw** | `openclaw plugins install renoise --marketplace ArcoCodes/renoise-plugins-official` |
| **其他支持远程 MCP 的客户端**（WorkBuddy、Cursor、Windsurf、Cline 等） | MCP 配置里加远程服务器 `https://renoise.ai/api/public/mcp`，常见写法 `{"mcpServers": {"renoise": {"url": "https://renoise.ai/api/public/mcp"}}}`（字段名以客户端文档为准） |
| **不确定 / 想看最新** | renoise.ai/plugin 列了各客户端的最新装法 |

把用户当前在用的那种放第一个并标「推荐」。装完：Claude 系要重开对话或在连接器里点重连，Codex 重开会话，然后再调一次 `get_account` 确认。

开工前：`get_account` 看余额；`load_skill model-routing` 读路由规则（下面是本 skill 用到的结论，模型以 list_models 实时为准）。

## 单价（2026-10-27 实测报价，以 estimate_cost 为准）

| 资产 | 模型 | 单价（积分） | 用在 |
|---|---|---|---|
| 场景 / 氛围配图 | `mj-v8.2` | 4 / 张 | 时代场景、主视觉、氛围（画风最好） |
| 带结构的示意图、地图底图、精确构图 | `gpt-image-2.5-sunburst` 1k | 13 / 张 | 地图、器物剖面、需要准确的布局 |
| 同一角色 / 同一场景多张一致 | `nano-banana-2` 1k | 8 / 张 | 系列角色、同一地点不同时刻 |
| 主视觉动态镜头 | `wan3.0-video` 720p 8s | 96 | 大多数动态镜头（首帧 = 已生成的配图） |
| 高难动态镜头（复杂运动、长镜头） | `seedance-2.5-byteplus` 720p 8s | 256（1080p 576） | 反转 / 高潮那一两个镜头 |
| 4K 单镜头 | `flux-3-video` 4K 8s | 656 | 只在需要 4K 母版时 |
| 全片配乐 | `lyria-pro` | 4 / 首 | **默认不用**：知识大赏强制用 vibe-bgm（SKILL.md「BGM」）；只有用户明确要求换曲才生成 |
| 单个音效 | `eleven-sfx-v2` | 0.4 / 秒 | 钟声、翻书、风、人群 |

账户活动：Wan 3.0、Seedance 2.5、Kling 4.0 Omni 的 480p/720p「免费通道」到 2026-11-02（报价不一定显示折扣，以实际扣费为准）。
**一期预算**：按 08-tiers.md 的增强等级（轻 ≈25–40 / 标准 ≈250–300 / 旗舰 ≈600–700）。只增强代码做不好的镜头，其余照样代码做。

## 流程

1. **写 assets.json**：每一项写清 `use`（哪一拍、做什么用）、`kind`、`model`、`ratio`、提示词。提示词 = `style_prefix` + 本张内容 + `no text, no letters, no watermark`。
2. **先图后视频**：动态镜头一律用已生成的配图做首帧（`references: [{ref: "task:<图的任务号>", role: "first_frame"}]`），保证动静一致；所以分两轮报价：第一轮图 + 配乐 + 音效，第二轮视频（第一轮出图后用户挑图）。也可以一次把两轮都列进预览、一次确认（预览里写明第二轮的首帧取自第一轮哪张）。
3. **create_tasks**（每次 ≤10 个）→ **wait_tasks** 直到 done → **download_results**（返回一条 curl 命令，在本机跑，下到 `lessons/NN/assets/_dl/`）→ 按 assets.json 的 `file` 改名放好，`status` 改 done，记下 task 号。
4. **视频进画面**（Wan 3.0 720p 实测输出顶部带 66 像素纯黑信箱边，clip2frames.py 会自动检测裁掉；拆完抽一帧确认首行不是黑的）：`python3 ~/.claude/skills/vibe-knowledge/tools/clip2frames.py assets/clips/v01.mp4 assets/clips/v01 --fps 30` → 打印帧数 n → film.js 里 `vclip(s, { dir: A("clips/v01"), n })`。原视频的环境声另存在 `assets/clips/v01/audio.wav`，要用就加一条 music：`{ src: P("clips/v01/audio.wav"), at, dur, gain: -20 }`。
5. **配乐**：默认 BGM 由 finish.py 的 bgm_force 钩子强制处理（自动补、按人声校准）；用户要求换曲时，那条 music 写 `bgm: true, user_request: "用户原话"`。
6. 不满意的单张：只重做那一张（新报价、新确认），别整批重来。

## 提示词写法

### 配图（Midjourney v8.2）
短句视觉描述，不写需求文档：
`[style_prefix], [主体], [环境], [光线], [构图：wide shot / low angle / negative space on the right for text], no text, no letters, no watermark`
- 给关键词留位置：写明 `negative space on the left/right/top`。
- 16:9；人物不写具体面部，写剪影 / 背影 / 远景，减少「像某个真人」的风险。

### 地图 / 示意（GPT Image 2.5 Sunburst）
```
USE: background plate for a documentary explainer
SCENE: antique paper map of Tang dynasty China, Yellow River and major prefectures as subtle ink lines
COMPOSITION: 16:9, map centered, wide margins, no labels
AVOID: any text, letters, numbers, legend, watermark
```
地名、数字全部由代码叠加（spread / keyword），不让模型写字。

### 动态镜头（Wan 3.0 / Seedance 2.5）
首帧模式，只写**变化**，不重复描述静态画面：
`[主体的动作 / 环境的变化], [一个镜头运动：slow push-in / slow dolly left], [光线变化], no text, no subtitles`
- 8 秒足够，一个镜头一个动作；需要多拍叙事或更长、更复杂的运动用 Seedance 2.5。
- 原生音频默认开着，可当环境声；不要对白。

### 配乐（Lyria Pro）
```
Genre/style: cinematic documentary underscore, minimal piano and warm strings, subtle analog synth pad
Mood: curious, intimate, then awe at the reveal
Tempo: 72 BPM
Vocals: instrumental
Target length: ~3 minutes
Structure: [Intro] sparse piano (0:00–0:15) → [Build] strings enter at the title (~0:15) → [Verse] steady pulse under narration → [Break] near silence (~2:00) → [Climax] full but soft → [Outro] solo piano, ends on an unresolved note
Production: wide stereo, low-mid kept clean for voice, no drums in the first 15 seconds
```
- 写明「留出人声频段」（low-mid kept clean for voice）。时长只是近似，实际用 loopbed / 剪切对齐。
- 一次出 2 版让用户挑。

### 音效（ElevenLabs SFX）
物理描述 + 真实长度：`a single temple bell struck once in a cold stone courtyard, long natural decay` · 3 秒。一条一个音效。

## 实测坑（第 01 期）

- Midjourney 每个任务只出 1 张 1456×816：要候选就多提交几个任务；放进成片前用 `~/tools/upscale-lab` 的 Real-ESRGAN x4plus 放大再缩到 1080p。
- 统一画风前缀会压过单张描述：时代不同的那张（如宋代书房）要换前缀，否则会被画成战国城楼。
- 首帧视频不一定照提示词演：v02 没有「关门」而是走进来一个斗篷人，先看片再决定用不用，别默认能用。
- Lyria 会严格按提示词里的时间点做段落（0:18 进鼓、1:45 抽空都对上了），提示词里一定写进旁白的真实时间。

## 安全

- 不生成在世真人的脸、不模仿品牌 logo；历史人物写「人物造型为示意」。
- 生成画面一律角标「AI 示意图 / AI 生成画面」（plate、vclip 默认带）。
- 不把用户的私人素材传给 Renoise，除非用户明确要用。
