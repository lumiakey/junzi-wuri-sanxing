#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重试昨晚降级为统计版的录音: 复用已有转写(spk.txt/srt, 不重新转写/分离),
直接重跑 analyze.py 的GLM提取。条件: llm为空 + 语料>=10字 + 非短录音跳过。"""
import os, json, glob, subprocess, sys

ROOT = os.path.expanduser("~/sanxing")
TRANS = os.path.join(ROOT, "data/transcripts")
ARCH = os.path.join(ROOT, "data/archive/audio")
dates = sorted(os.path.basename(d) for d in glob.glob(os.path.join(ROOT, "data/analysis", "20*")))[-2:]
retried = 0
for d in dates:
    for f in sorted(glob.glob(os.path.join(ROOT, "data/analysis", d, "*.json"))):
        j = json.load(open(f, encoding="utf-8"))
        if j.get("llm") or j.get("trivial") or j.get("chars", 0) < 10:
            continue
        stem = os.path.basename(f)[:-5]
        srt = os.path.join(TRANS, stem + ".srt")
        txt = os.path.join(TRANS, stem + ".txt")
        audio = os.path.join(ARCH, stem + ".m4a")
        if not (os.path.exists(srt) and os.path.exists(txt)):
            print(f"缺转写文件, 跳过: {stem}")
            continue
        dur = "0"
        if os.path.exists(audio):
            r = subprocess.run(["/opt/homebrew/bin/ffprobe", "-v", "error", "-show_entries",
                                "format=duration", "-of", "csv=p=0", audio],
                               capture_output=True, text=True)
            dur = (r.stdout.strip().split(".") or ["0"])[0]
        print(f"重试GLM分析: {stem} ({j.get('chars')}字)")
        os.remove(f)
        subprocess.run([sys.executable, os.path.join(ROOT, "bin/analyze.py"),
                        txt, srt, dur, audio])
        retried += 1
print(f"重试完成: {retried}条" if retried else "无需重试(无降级条目)")
