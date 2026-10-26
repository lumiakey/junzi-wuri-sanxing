#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""消化"声音认人"笔记: 读取《声音认人 · X》笔记里的 X=名字 回答 ->
声纹写入 声纹库.json(此后所有录音自动带此真名) -> 删除已答笔记"""
import os, re, json, subprocess, datetime
import contacts_lib as cl

ROOT = os.path.expanduser("~/sanxing")
LIB = os.path.join(ROOT, "data/state/声纹库.json")
PENDING = os.path.join(ROOT, "data/state/pending_voices.json")

pending = json.load(open(PENDING, encoding="utf-8")) if os.path.exists(PENDING) else {}
if not pending:
    raise SystemExit(0)

# 读所有认人笔记正文
r = subprocess.run(["osascript", "-e",
    'tell application "Notes"\n'
    'set out to ""\n'
    'repeat with n in (notes of folder "三省" whose name starts with "声音认人")\n'
    'set out to out & (name of n) & (character id 9) & (body of n) & "###REC###"\n'
    'end repeat\nreturn out\nend tell'], capture_output=True, text=True)
if r.returncode != 0:
    print("读取认人笔记失败:", r.stderr.strip()[:120])
    raise SystemExit(1)

lib = json.load(open(LIB, encoding="utf-8")) if os.path.exists(LIB) else {}
resolved = []
for rec in r.stdout.split("###REC###"):
    if "\t" not in rec:
        continue
    title, body = rec.split("\t", 1)
    entry = next((v for v in pending.values() if v.get("note") == title), None)
    if not entry:
        continue
    text = re.sub(r"<[^>]+>", "", body)
    m = re.search(re.escape(entry["label"]) + r"\s*[=＝]\s*([^\s<]{1,40})", text)
    if not m:
        continue
    name = m.group(1).strip()
    # 填空行紧跟答案行时会抓成"说话人X=名字", 取最后一段
    name = re.split(r"[=＝]", name)[-1].strip()
    if not name or name.startswith("说话人"):
        continue
    lib[name] = entry["embedding"]
    resolved.append((title, entry["label"], name))
    print(f"✅ {entry['label']} = {name}, 声纹已入库(此人说{entry['dur']/60:.0f}分钟的那段)")
    subprocess.run(["osascript", "-e",
        f'tell application "Notes" to tell folder "三省" to delete (every note whose name is "{title}")'],
        capture_output=True, text=True)

if resolved:
    json.dump(lib, open(LIB, "w", encoding="utf-8"), ensure_ascii=False)
    done_notes = {t for t, _, _ in resolved}
    pending = {k: v for k, v in pending.items() if v.get("note") not in done_notes}
    json.dump(pending, open(PENDING, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # 台账留痕
    with open(os.path.join(ROOT, "data/commitments/台账.md"), "a", encoding="utf-8") as f:
        f.write("\n## 联系人动态\n")
        today = datetime.date.today().isoformat()
        for _, label, name in resolved:
            f.write(f"- {today} 声纹认人: {label} = {name}(已入库)\n")
    print(f"已消化{len(resolved)}条, 声纹库现有{len(lib)}人")
else:
    print("认人笔记暂无回答(在备忘录填 名字 后双击立即处理)")
