#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""声音认人: 扫描近期 .spk.meta.json, 对"陌生且说了足够多话"的说话人,
从原始音频截2段声音, 建备忘录笔记《声音认人 · X》(附件可直接播放)+填空行,
等用户填名字; 声纹存 pending_voices.json, 由 resolve_voices.py 消化入库"""
import os, re, json, glob, subprocess, datetime, time

ROOT = os.path.expanduser("~/sanxing")
BIN = os.path.join(ROOT, "bin")
TRANS = os.path.join(ROOT, "data", "transcripts")
PENDING = os.path.join(ROOT, "data", "state", "pending_voices.json")
MIN_TALK = 120.0   # 说话人至少2分钟才值得问
MAX_ASK = 3        # 每次最多问3人, 防刷屏

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
            continue  # 已命名或我
        if info.get("dur", 0) < MIN_TALK or "embedding" not in info:
            continue
        key = f"{label}|{os.path.basename(mp)}"
        if key in pending:
            continue
        segs = info.get("segs", [])
        if len(segs) < 1:
            continue
        asks.append({"key": key, "label": label, "dur": info["dur"], "segs": segs,
                     "src": src, "embedding": info["embedding"],
                     "note": f"声音认人 · {label} · {datetime.date.today().strftime('%m%d')}"})
        if len(asks) >= MAX_ASK:
            break
    if len(asks) >= MAX_ASK:
        break

if not asks:
    print("无新的陌生说话人需要认人")
    raise SystemExit(0)

for a in asks:
    # 截2段每段6-14秒的原声
    clip_dir = os.path.join(ROOT, "data", "state", "voice_clips")
    os.makedirs(clip_dir, exist_ok=True)
    clips = []
    for i, (s, e) in enumerate(a["segs"][:2]):
        e2 = min(e, s + 14)
        if e2 - s < 4:
            continue
        cp = os.path.join(clip_dir, f"{a['key'].split('|')[0]}_{i}.m4a").replace("说话人", "spk")
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(s), "-t", str(e2 - s),
                            "-i", a["src"], cp], capture_output=True, text=True)
        if r.returncode == 0 and os.path.getsize(cp) > 10000:
            clips.append(cp)
    if not clips:
        print(f"{a['label']}: 截取音频失败, 跳过")
        continue
    # 建带音频附件的认人笔记
    esc_note = a["note"].replace('"', '')
    html = (f'<div>🎤 这位在你录音里说了 {a["dur"]/60:.0f} 分钟, 听听是谁?</div>'
            '<div>👇点击下方音频播放</div>'
            '<div><br></div>'
            '<div>是谁? 在下一行等号后写名字(如 老X/王总/张三):</div>'
            f'<div>{a["label"]}=</div>')
    ascript = f'''
tell application "Notes"
	if not (exists folder "三省") then make new folder with properties {{name:"三省"}}
	tell folder "三省"
		set n to make new note with properties {{name:"{esc_note}", body:"{html}"}}
		delay 1
		tell n
'''
    for cp in clips:
        ascript += f'\t\t\tmake new attachment with data (POSIX file "{cp}" as alias)\n'
    ascript += '''
		end tell
	end tell
end tell'''
    r = subprocess.run(["osascript", "-e", ascript], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"{a['label']}: 建笔记失败 {r.stderr.strip()[:120]}")
        continue
    pending[a["key"]] = {"note": a["note"], "label": a["label"], "dur": a["dur"],
                         "embedding": a["embedding"], "created": datetime.date.today().isoformat()}
    print(f"✅ 已建认人笔记: {a['note']} (说了{a['dur']/60:.0f}分钟, {len(clips)}段音频)")

json.dump(pending, open(PENDING, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
