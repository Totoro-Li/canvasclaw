## 附录 A：自动截图 / 录屏 / 视频制作工具链

本报告中的界面截图、操作录屏、机制讲解动画与 1 分钟讲解视频，全部在**无显示器的服务器（headless Linux）**上自动生成。以下是所用工具与命令，便于复现。

### A.1 环境准备（一次性）

```bash
# 无头浏览器（截图 + 录屏 + Motion Canvas 渲染都依赖它）
pip install playwright
python -m playwright install chromium          # 浏览器二进制（官方 CDN cdn.playwright.dev）
python -m playwright install-deps chromium     # 通过 apt 装齐 libnss3 / libX11 等系统库
apt-get install -y fonts-noto-cjk && fc-cache -f   # 中文字体，避免渲染成方框
# 视频拼接
#   ffmpeg（本项目用 imageio-ffmpeg 的静态 7.0.2）
# Motion Canvas（动画）需要 Node ≥18 + npm
```

### A.2 自动截图（Playwright + Streamlit）

无显示器下用 chromium 打开本地 Streamlit，按选择器等待元素稳定后截图：

```python
# tools/capture_ui.py（节选）
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox"])
    ctx = b.new_context(viewport={"width":1440,"height":900}, device_scale_factor=2)
    pg = ctx.new_page(); pg.goto("http://localhost:8501/")
    pg.wait_for_selector("text=快捷提问")          # 等 Streamlit 首屏渲染完
    pg.screenshot(path="01_home.png")
    pg.get_by_text("🔁 记忆 vs 检索增强").first.click()
    pg.wait_for_selector("text=来源")               # 等回答+出处渲染
    pg.screenshot(path="03_answer.png")
```
要点：`device_scale_factor=2` 出 2× 高清图；用 `wait_for_selector(text=...)` 而非定长 sleep；root 下 chromium 必须 `--no-sandbox`。

### A.3 录屏（Playwright 视频录制）

Playwright 的浏览器上下文可直接录制整段会话为 webm，再用 ffmpeg 转 mp4：

```python
ctx = b.new_context(record_video_dir="rec/", record_video_size={"width":1440,"height":900})
# ... 脚本化点击/等待 = 一段操作演示 ...
ctx.close()   # 关闭上下文时落盘 webm
```
```bash
ffmpeg -y -i rec/xxxx.webm -c:v libx264 -pix_fmt yuv420p -crf 20 ui_walkthrough.mp4
```

### A.4 机制动画（Motion Canvas，无头渲染）

用 Motion Canvas 写「Orchestrator–Worker 流水线」动画（`video/mc/src/scenes/agent.tsx`），无头渲染成帧序列再合成：

```bash
cd video/mc && npm install          # 注意 @motion-canvas/ffmpeg 需 vite@4.x
npm run serve                       # 启动编辑器 http://localhost:9000
```
```python
# tools/mc_render.py（节选）：用 playwright 点击编辑器里的 RENDER 按钮
pg.goto("http://localhost:9000/")
for e in pg.query_selector_all("button"):
    if (e.inner_text() or "").strip().upper() == "RENDER": e.click(); break
# 默认导出 PNG 帧到 video/mc/output/project/000000.png ...
```
```bash
# 帧序列 -> mp4
ffmpeg -y -framerate 30 -i video/mc/output/project/%06d.png \
  -c:v libx264 -pix_fmt yuv420p -crf 18 agent_anim.mp4
```
关键坑：vite 配置里 Motion Canvas 插件是 CJS，需用 `createRequire(import.meta.url)` 取 `.default`；中文文字要在 `Txt` 上指定带 CJK 字形的 `fontFamily`。

### A.5 合成 1 分钟讲解视频（ffmpeg）

把「录屏片段」与「动画片段」按脚本交错，统一分辨率/帧率后用 concat 合成：

```bash
# 统一为 1920x1080@30fps（每段先规整，避免 concat 花屏）
ffmpeg -i seg.mp4 -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:-1:-1:color=0x0d1117,fps=30" -c:v libx264 -crf 20 seg_norm.mp4
# concat
printf "file seg1.mp4\nfile seg2.mp4\n..." > list.txt
ffmpeg -y -f concat -safe 0 -i list.txt -c:v libx264 -pix_fmt yuv420p -crf 20 canvasclaw_explainer_1min.mp4
```

> 全流程零人工：截图、录屏、动画、合成均由脚本驱动，可纳入 CI 在每次发布前自动产出最新演示素材。
