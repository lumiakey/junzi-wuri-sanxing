#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""声音认人: 对陌生说话人建《声音认人 · X · 改成名字》笔记(标题即答案区),
内嵌一段可播放原声; 用户听完把标题末段改成名字, resolve_voices 消化后声纹永久入库"""
import os, json, glob, subprocess, datetime

ROOT = os.path.expanduser("~/sanxing")
TRANS = os.path.join(ROOT, "data", "transcripts")
PENDING = os.path.join(ROOT, "data", "state", "pending_voices.json")
FFMPEG = "/opt/homebrew/bin/ffmpeg"
MIN_TALK = 120.0   # 说话人至少2分钟才值得问
MAX_ASK = 3

pending = json.load(open(PENDING, encoding="utf-8")) if os.path.exists(PENDING) else {}
metas = sorted(glob.glob(os.path.join(TRANS, "*.spk.meta.json")), key=os.path.getmtime)[-8:]
asks = []
for mp in metas:
    meta = json.load(open(mp, encoding="utf-8"))
    src = meta.get("source_audio", "")
    if not src or not os.path.exists(src):
        continue
    for label, info in meta.get("speakers", {}).items():
        if label == "我" or not label.startswith("说话人"):
            continue
        if info.get("dur", 0) < MIN_TALK or "embedding" not in info:
            continue
        key = f"{label}|{os.path.basename(mp)}"
        if key in pending:
            continue
        segs = info.get("segs", [])
        if not segs:
            continue
        asks.append({"key": key, "label": label, "dur": info["dur"], "segs": segs,
                     "src": src, "embedding": info["embedding"],
                     "note": f"声音认人 · {label} · 改成名字"})
        if len(asks) >= MAX_ASK:
            break
    if len(asks) >= MAX_ASK:
        break

if not asks:
    print("无新的陌生说话人需要认人")
    raise SystemExit(0)

for a in asks:
    clip_dir = os.path.join(ROOT, "data", "state", "voice_clips")
    os.makedirs(clip_dir, exist_ok=True)
    s, e = a["segs"][0]
    e = min(e, s + 16)
    cp = os.path.join(clip_dir, (a["key"].split("|")[0] + "_" + a["key"].split("|")[1][:12] + ".m4a").replace("说话人", "spk"))
    r = subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", str(s), "-t", str(e - s),
                        "-i", a["src"], cp], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(cp) or os.path.getsize(cp) < 10000:
        print(f"{a['label']}: 截取音频失败, 跳过")
        continue
    # 表格排版: 指引放原生表格(结构化块元素), 音频附件跟在表格后
    title = a["note"].replace("改成名字", "听后把这里改成名字")
    mins = f"{a['dur']/60:.0f}"
    html = ("<table border='1'>"
            '<tr><td>🎤 ' + a['label'] + ' · 说了 ' + mins + ' 分钟</td></tr>'
            '<tr><td>① 点下方 ▶ 播放音频</td></tr>'
            '<tr><td>② 听出是谁后, 把本笔记标题末尾「听后把这里改成名字」改成他的名字</td></tr>'
            '<tr><td>③ 双击「立即处理」生效, 本笔记自动消失</td></tr>'
            '</table><div><br></div>')
    ascript = f'''
tell application "Notes"
	if not (exists folder "三省") then make new folder with properties {{name:"三省"}}
	tell folder "三省"
		set n to make new note with properties {{name:"{title}", body:"{html}"}}
		delay 1
		tell n
			make new attachment with data (POSIX file "{cp}" as alias)
		end tell
	end tell
end tell'''
    r = subprocess.run(["osascript", "-e", ascript], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"{a['label']}: 建笔记失败 {r.stderr.strip()[:120]}")
        continue
    pending[a["key"]] = {"note": title, "label": a["label"], "dur": a["dur"],
                         "embedding": a["embedding"], "created": datetime.date.today().isoformat()}
    print(f"✅ 认人笔记已建: {title} (说了{a['dur']/60:.0f}分钟)")

json.dump(pending, open(PENDING, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
