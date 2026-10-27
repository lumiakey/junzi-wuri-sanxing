#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""说话人分离 + whisper时间轴对齐 + 声纹库命名 + "我"认领
用法: diarize.py <wav16k单声道> <转写srt> [注册wav] [人数=3] [阈值=0.70] [源音频路径]
输出: <srt>.spk.txt        带标签转写 "[mm:ss] 我/老唐/说话人X: 原文"
      <srt>.spk.meta.json  各说话人时长/片段/声纹(供声音认人与入库)
依赖: ~/sanxing/venv (sherpa-onnx)"""
import os, sys, wave, re, json
import numpy as np

WAV, SRT = sys.argv[1], sys.argv[2]
ENROLL = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else os.path.expanduser("~/sanxing/data/state/声纹注册.wav")
NUM_SPK = int(sys.argv[4]) if len(sys.argv) > 4 else 3
THRESH = float(sys.argv[5]) if len(sys.argv) > 5 else 0.70
SRC_AUDIO = sys.argv[6] if len(sys.argv) > 6 else ""
ROOT = os.path.expanduser("~/sanxing")
SEG_MODEL = os.path.join(ROOT, "models/sherpa-onnx-pyannote-segmentation-3.0/model.int8.onnx")
EMB_MODEL = os.path.join(ROOT, "models/3dspeaker_speech_eres2netv2_sv_zh-cn_16k-common.onnx")
LIB = os.path.join(ROOT, "data/state/声纹库.json")

import sherpa_onnx as so


def read_wav(path):
    with wave.open(path) as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1, "需16k单声道wav"
        raw = w.readframes(w.getnframes())
        return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


samples = read_wav(WAV)

CACHE = f"/tmp/diar_{os.path.basename(WAV)}_{int(os.path.getmtime(WAV))}_{NUM_SPK}_{THRESH}.json"
if os.path.exists(CACHE):
    spk_segs = [tuple(s) for s in json.load(open(CACHE))]
    print("(命中分离缓存)")
else:
    cfg = so.OfflineSpeakerDiarizationConfig(
        segmentation=so.OfflineSpeakerSegmentationModelConfig(
            pyannote=so.OfflineSpeakerSegmentationPyannoteModelConfig(model=SEG_MODEL), num_threads=4),
        embedding=so.SpeakerEmbeddingExtractorConfig(model=EMB_MODEL, num_threads=4),
        clustering=so.FastClusteringConfig(num_clusters=NUM_SPK, threshold=THRESH))
    sd = so.OfflineSpeakerDiarization(cfg)
    res = sd.process(samples)
    spk_segs = [(s.start, s.end, s.speaker) for s in res.sort_by_start_time()]
    json.dump([list(s) for s in spk_segs], open(CACHE, "w"))
dur = len(samples) / 16000
spk_talk = {}
for a, b, k in spk_segs:
    spk_talk[k] = spk_talk.get(k, 0) + (b - a)
print(f"分离完成: {dur/60:.1f}分钟, {len(spk_talk)}位说话人, "
      + ", ".join(f"说话人{k} {spk_talk.get(k,0)/60:.1f}分" for k in sorted(spk_talk)))


def embed_of(arr):
    ex = so.SpeakerEmbeddingExtractor(so.SpeakerEmbeddingExtractorConfig(model=EMB_MODEL, num_threads=4))
    stream = ex.create_stream()
    stream.accept_waveform(16000, arr.tolist())
    e = ex.compute(stream)
    return np.array(e) if e else None


def top_segments(k, n=4, min_len=4.0):
    return sorted([s for s in spk_segs if s[2] == k and s[1] - s[0] >= min_len],
                  key=lambda x: -(x[1] - x[0]))[:n]


def cluster_embedding(k, min_sec=10.0):
    segs = top_segments(k, 6)
    buf, got = [], 0.0
    for a, b, _ in segs:
        buf.append(samples[int(a * 16000):int(b * 16000)])
        got += b - a
        if got >= min_sec:
            break
    if not buf:
        return None
    return embed_of(np.concatenate(buf))


def cos(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


# 每个有声线的簇算一次声纹
embeds = {}
for k in sorted(spk_talk):
    if spk_talk[k] >= 8:
        e = cluster_embedding(k)
        if e is not None:
            embeds[k] = e

# 声纹库命名: 命中且领先第二名0.05以上才用名, 防误标
labels = {k: f"说话人{k}" for k in spk_talk}
library = {}
if os.path.exists(LIB):
    try:
        library = {n: np.array(v) for n, v in json.load(open(LIB, encoding="utf-8")).items()}
    except Exception:
        library = {}
for k, e in embeds.items():
    scored = sorted(((cos(e, v), n) for n, v in library.items()), reverse=True)
    if scored and scored[0][0] > 0.55 and (len(scored) == 1 or scored[0][0] - scored[1][0] > 0.05):
        labels[k] = scored[0][1]
        print(f"  声纹库命中: 说话人{k} → {labels[k]} ({scored[0][0]:.3f})")

# 声纹注册认领"我"(优先级高于库)
if os.path.exists(ENROLL) and os.path.getsize(ENROLL) > 150000:  # >=5秒(认人片段约7-16秒)
    mine = embed_of(read_wav(ENROLL))
    if mine is not None:
        best_k, best_s = None, -1
        for k, e in embeds.items():
            s = cos(mine, e)
            if s > best_s:
                best_k, best_s = k, s
        if best_k is not None and best_s > 0.45:
            labels[best_k] = "我"
            print(f"✅ 已认领: 说话人{best_k} 是「我」(相似度{best_s:.3f})")


def ts2sec(t):
    t = t.replace(",", ".")
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


# 合并whisper时间轴
out_lines = []
raw = open(SRT, encoding="utf-8").read().splitlines()
cur_ts, buf = None, []
for ln in raw + [""]:
    if "-->" in ln:
        if buf and cur_ts:
            out_lines.append((cur_ts, "".join(buf)))
        cur_ts = ln.split("-->")[0].strip()
        buf = []
        continue
    if ln.strip() == "" or re.match(r"^\d+$", ln.strip()):
        continue
    buf.append(ln.strip())
if buf and cur_ts:
    out_lines.append((cur_ts, "".join(buf)))

merged = []
for ts, text in out_lines:
    t0 = ts2sec(ts)
    best_k, best_ov = None, 0
    for a, b, k in spk_segs:
        ov = min(b, t0 + 2) - max(a, t0)
        if ov > best_ov:
            best_k, best_ov = k, ov
    who = labels.get(best_k, "未知") if best_k is not None else "未知"
    merged.append(f"[{ts[:5]}] {who}: {text}")

out_path = re.sub(r"\.srt$", "", SRT) + ".spk.txt"
with open(out_path, "w", encoding="utf-8") as f:
    f.write("\n".join(merged) + "\n")

# 元数据导出(声音认人用)
meta = {"source_audio": SRC_AUDIO, "speakers": {}}
for k in spk_talk:
    item = {"dur": round(spk_talk[k], 1), "segs": [[round(a, 1), round(b, 1)] for a, b, _ in top_segments(k)]}
    if k in embeds:
        item["embedding"] = [round(float(x), 6) for x in embeds[k]]
    meta["speakers"][labels.get(k, f"说话人{k}")] = item
json.dump(meta, open(re.sub(r"\.srt$", "", SRT) + ".spk.meta.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

me_chars = sum(len(re.findall(r"[\u4e00-\u9fff]", l.split(":", 1)[1]))
               for l in merged if "] 我: " in l)
named = [l for l in labels.values() if l not in ("我",) and not l.startswith("说话人")]
print(f"已写出: {out_path.split('/')[-1]} ({len(merged)}句, 我的语料{me_chars}字"
      + (f", 声纹库命名: {'、'.join(named)}" if named else "") + ")")
