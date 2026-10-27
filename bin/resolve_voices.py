#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""消化"声音认人"笔记: 答案写在笔记标题末段(声音认人 · 说话人X · 名字),
读标题->声纹入库->删除已答笔记。标题纯文本, 无HTML解析问题。"""
import os, json, subprocess, datetime

ROOT = os.path.expanduser("~/sanxing")
LIB = os.path.join(ROOT, "data/state/声纹库.json")
PENDING = os.path.join(ROOT, "data/state/pending_voices.json")
PLACEHOLDER = {"改成名字", "填名字", "名字", "听音频后把这里改成名字", "听后把这里改成名字"}

pending = json.load(open(PENDING, encoding="utf-8")) if os.path.exists(PENDING) else {}
if not pending:
    raise SystemExit(0)

r = subprocess.run(["osascript", "-e",
    'tell application "Notes"\n'
    'set out to ""\n'
    'repeat with n in (notes of folder "三省" whose name starts with "声音认人")\n'
    'set out to out & (name of n) & linefeed\n'
    'end repeat\nreturn out\nend tell'], capture_output=True, text=True)
if r.returncode != 0:
    print("读取认人笔记失败:", r.stderr.strip()[:120])
    raise SystemExit(1)

lib = json.load(open(LIB, encoding="utf-8")) if os.path.exists(LIB) else {}
resolved = []
for title in r.stdout.splitlines():
    if not title.strip():
        continue
    entry = next((v for v in pending.values() if v.get("note", "").split(" · ")[0:2] == title.split(" · ")[0:2]), None)
    if not entry:
        continue
    parts = [p.strip() for p in title.split("·")]
    answer = "·".join(parts[2:]).strip() if len(parts) >= 3 else ""
    if not answer or answer in PLACEHOLDER or answer == entry["label"]:
        continue
    import glob as _g
    if answer in ("自己", "我", "本人"):
        # 用户标记"这是我自己" -> 写入声纹注册(认领'我:'标签), 不进人物库
        clip = sorted(_g.glob(os.path.join(ROOT, "data/state/voice_clips",
                                           entry["label"].replace("说话人", "spk") + "_*.m4a")))
        if clip:
            import subprocess as _sp
            _sp.run(["/opt/homebrew/bin/ffmpeg", "-y", "-v", "error", "-i", clip[-1],
                     "-ar", "16000", "-ac", "1", os.path.join(ROOT, "data/state/声纹注册.wav")],
                    check=True)
            print(f"✅ {entry['label']} = 我自己, 已写入声纹注册({os.path.basename(clip[-1])})")
        else:
            lib["我"] = entry["embedding"]
            print(f"✅ {entry['label']} = 我自己(音频缺失, 以库内'我'标记)")
    else:
        lib[answer] = entry["embedding"]
        print(f"✅ {entry['label']} = {answer}, 声纹已入库(说{entry['dur']/60:.0f}分钟的那位)")
    resolved.append((title, entry["label"], answer))
    subprocess.run(["osascript", "-e",
        f'tell application "Notes" to tell folder "三省" to delete (every note whose name is "{title}")'],
        capture_output=True, text=True)

if resolved:
    json.dump(lib, open(LIB, "w", encoding="utf-8"), ensure_ascii=False)
    done_prefixes = {tuple(t.split(" · ")[:2]) for t, _, _ in resolved}
    pending = {k: v for k, v in pending.items()
               if tuple(v.get("note", "").split(" · ")[:2]) not in done_prefixes}
    json.dump(pending, open(PENDING, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(os.path.join(ROOT, "data/commitments/台账.md"), "a", encoding="utf-8") as f:
        today = datetime.date.today().isoformat()
        f.write("\n## 联系人动态\n")
        for _, label, name in resolved:
            f.write(f"- {today} 声纹认人: {label} = {name}(已入库)\n")
    print(f"已消化{len(resolved)}条, 声纹库现有{len(lib)}人")
else:
    print("认人笔记暂无回答(听完音频后把笔记标题末尾改成名字, 再双击立即处理)")
