#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""说话人分离 + 与whisper转写对齐 + 声纹注册认领"我"
用法: diarize.py <wav16k单声道> <转写srt> [注册音频wav16k]
输出: <srt同目录/同名>.spk.txt  每行 "[mm:ss] 我/说话人B: 原文"
      注册音频不存在时全部标"说话人X", 并在stdout提示注册方法
依赖: ~/sanxing/venv (sherpa-onnx)"""
import os, sys, wave, re, json
import numpy as np

WAV, SRT = sys.argv[1], sys.argv[2]
ENROLL = sys.argv[3] if len(sys.argv) > 3 else os.path.expanduser("~/sanxing/data/state/声纹注册.wav")
NUM_SPK = int(sys.argv[4]) if len(sys.argv) > 4 else 3  # 默认按3人对话/会议场景, 可改
THRESH = float(sys.argv[5]) if len(sys.argv) > 5 else 0.70
ROOT = os.path.expanduser("~/sanxing")
SEG_MODEL = os.path.join(ROOT, "models/sherpa-onnx-pyannote-segmentation-3.0/model.int8.onnx")
EMB_MODEL = os.path.join(ROOT, "models/3dspeaker_speech_eres2netv2_sv_zh-cn_16k-common.onnx")

import sherpa_onnx as so


def read_wav(path):
    with wave.open(path) as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1, "需16k单声道wav"
        raw = w.readframes(w.getnframes())
        return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


samples = read_wav(WAV)

CACHE = f"/tmp/diar_{os.path.basename(WAV)}_{int(os.path.getmtime(WAV))}_{NUM_SPK}_{THRESH}.json"
if os.path.exists(CACHE):
    spk_segs, n_spk = json.load(open(CACHE))
    spk_segs = [tuple(s) for s in spk_segs]
    print(f"(命中缓存)")
else:
    cfg = so.OfflineSpeakerDiarizationConfig(
        segmentation=so.OfflineSpeakerSegmentationModelConfig(
            pyannote=so.OfflineSpeakerSegmentationPyannoteModelConfig(model=SEG_MODEL), num_threads=4),
        embedding=so.SpeakerEmbeddingExtractorConfig(model=EMB_MODEL, num_threads=4),
        clustering=so.FastClusteringConfig(num_clusters=NUM_SPK, threshold=THRESH))
    sd = so.OfflineSpeakerDiarization(cfg)
    res = sd.process(samples)
    n_spk = res.num_speakers
    spk_segs = [(s.start, s.end, s.speaker) for s in res.sort_by_start_time()]
    json.dump([list(s) for s in spk_segs], open(CACHE, "w"))
dur = len(samples) / 16000
spk_talk = {}
for a, b, k in spk_segs:
    spk_talk[k] = spk_talk.get(k, 0) + (b - a)
print(f"分离完成: {dur/60:.1f}分钟, {n_spk}位说话人, "
      + ", ".join(f"说话人{k} {spk_talk.get(k,0)/60:.1f}分" for k in sorted(spk_talk)))


def embed_of(arr):
    ex = so.SpeakerEmbeddingExtractor(so.SpeakerEmbeddingExtractorConfig(model=EMB_MODEL, num_threads=4))
    stream = ex.create_stream()
    stream.accept_waveform(16000, arr.tolist())
    emb = ex.compute(stream)
    return np.array(emb) if emb else None


def cluster_embedding(k, min_sec=8.0):
    """取该说话人最长的几段拼接出>=min_sec样本求声纹均值"""
    segs = sorted([s for s in spk_segs if s[2] == k], key=lambda x: -(x[1] - x[0]))
    buf, got = [], 0.0
    for a, b, _ in segs:
        buf.append(samples[int(a * 16000):int(b * 16000)])
        got += b - a
        if got >= min_sec:
            break
    if not buf:
        return None
    return embed_of(np.concatenate(buf))


# 声纹认领"我"
me_label = None
if os.path.exists(ENROLL) and os.path.getsize(ENROLL) > 400000:  # 至少~12秒有效音频
    mine = embed_of(read_wav(ENROLL))
    if mine is not None:
        best_k, best_s = None, -1
        for k in sorted(spk_talk):
            if spk_talk.get(k, 0) < 5:
                continue  # 太碎的簇声纹不可信
            e = cluster_embedding(k)
            if e is None:
                continue
            s = float(np.dot(mine, e) / (np.linalg.norm(mine) * np.linalg.norm(e) + 1e-9))
            print(f"  说话人{k} 与注册声纹相似度: {s:.3f}")
            if s > best_s:
                best_k, best_s = k, s
        if best_s > 0.45:
            me_label = best_k
            print(f"✅ 已认领: 说话人{best_k} 是「我」(相似度{best_s:.3f})")
        else:
            print(f"⚠️ 最高相似度{best_s:.3f}不足0.45, 本次录音可能没有我本人, 全部标匿名")
else:
    print("未找到有效声纹注册音频(~/sanxing/data/state/声纹注册.wav), 全部标注为匿名说话人")


def label_of(k):
    if me_label is not None and k == me_label:
        return "我"
    return f"说话人{k}"


# 合并whisper时间轴
def ts2sec(t):
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s.replace(",", "."))


out_lines = []
raw = open(SRT, encoding="utf-8").read().splitlines()
cur_ts = None
buf = []
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
    t0 = ts2sec(ts[:5] + ",000" if "," not in ts else ts)
    best_k, best_ov = None, 0
    for a, b, k in spk_segs:
        ov = min(b, t0 + 2) - max(a, t0)
        if ov > best_ov:
            best_k, best_ov = k, ov
    who = label_of(best_k) if best_k is not None else "未知"
    merged.append(f"[{ts[:5]}] {who}: {text}")

out_path = re.sub(r"\.srt$", "", SRT) + ".spk.txt"
with open(out_path, "w", encoding="utf-8") as f:
    f.write("\n".join(merged) + "\n")
me_chars = sum(len(re.findall(r"[\u4e00-\u9fff]", l.split(":", 1)[1])) for l in merged if l.split("] ", 1)[-1].startswith("我:"))
print(f"已写出: {out_path} ({len(merged)}句, 其中我的语料{me_chars}字)")
