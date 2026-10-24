#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日报渲染器: 汇总当天所有录音的分析JSON -> 一份md报告(覆盖) + 备忘录笔记(更新)
三类分节: 📖传不习乎·分析表达 / 🤝与朋友交而不信乎·承诺记录 / 🪞吾日三省·自省报告"""
import os, re, json, glob, subprocess, datetime

ROOT = os.path.expanduser("~/sanxing")
REPORTS = os.path.join(ROOT, "data", "reports")
COMMIT = os.path.join(ROOT, "data", "commitments", "台账.md")
today = datetime.date.today().isoformat()
ADIR = os.path.join(ROOT, "data", "analysis", today)


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline(s):
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc(s))
    return re.sub(r"`(.+?)`", r"<code>\1</code>", s)


def html_of_md_lines(lines):
    """渲染器自己生成的markdown子集 -> HTML"""
    html, i = [], 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            html.append("<table border=1 cellspacing=0 cellpadding=4>")
            for r, cells in enumerate(rows):
                tag = "th" if r == 0 else "td"
                html.append("<tr>" + "".join(f"<{tag}>{inline(c)}</{tag}>" for c in cells) + "</tr>")
            html.append("</table>")
            continue
        if ln.startswith("- "):
            html.append("<ul>")
            while i < len(lines) and lines[i].startswith("- "):
                html.append(f"<li>{inline(lines[i][2:])}</li>")
                i += 1
            html.append("</ul>")
            continue
        if ln.startswith("> "):
            html.append(f"<p><i>{inline(ln[2:])}</i></p>")
        elif ln.startswith("### "):
            html.append(f"<h3>{inline(ln[4:])}</h3>")
        elif ln.startswith("## "):
            html.append(f"<h2>{inline(ln[3:])}</h2>")
        elif ln.strip():
            html.append(f"<p>{inline(ln)}</p>")
        i += 1
    return "".join(html)


files = sorted(glob.glob(os.path.join(ADIR, "*.json")))
if not files:
    print("今日无分析数据, 跳过发布")
    raise SystemExit(0)

recs = [json.load(open(f, encoding="utf-8")) for f in files]
main = [r for r in recs if not r.get("trivial")]
triv = [r for r in recs if r.get("trivial")]
n_dur = sum(r["duration"] for r in recs)
n_cjk = sum(r["chars"] for r in recs)
triv_dur = sum(r["duration"] for r in triv)
triv_cjk = sum(r["chars"] for r in triv)

# 聚合填充词
agg = {}
for r in main:
    for w, c in (r.get("fillers") or {}).items():
        agg[w] = agg.get(w, 0) + c
top = sorted(agg.items(), key=lambda x: -x[1])

# 聚合LLM结果
promises, memorize, highlights, cactions = [], [], [], []
obs_set, pat_set = [], []
sanxing = {}


def key(s):
    return re.sub(r"\s", "", s or "")


seen = set()
for r in main:
    L = r.get("llm") or {}
    for p in L.get("promises", []):
        if key(p.get("quote")) and key(p["quote"]) not in seen:
            seen.add(key(p["quote"]))
            promises.append(p)
    for m in L.get("memorize", []):
        if key(m.get("text")) and key(m["text"]) not in seen:
            seen.add(key(m["text"]))
            memorize.append(m)
    for q in L.get("quote_highlights", []):
        if q and q not in highlights:
            highlights.append(q)
    for v in (L.get("filler_obs") or "").strip(), :
        if v and v not in obs_set:
            obs_set.append(v)
    v = (L.get("patterns") or "").strip()
    if v and v not in pat_set:
        pat_set.append(v)
    for k2, v2 in (L.get("sanxing") or {}).items():
        if v2:
            sanxing.setdefault(k2, [])
            if v2 not in sanxing[k2]:
                sanxing[k2].append(v2)
    cactions += r.get("contact_actions") or []

# ---------- markdown ----------
M = []
M.append(f"# 三省 · {today}")
M.append("")
M.append(f"> {len(recs)}段录音 · {n_dur // 60}分{n_dur % 60}秒语料 · {n_cjk}字 ｜ "
         f"有效分析{len(main)}段" + (f"，另有{len(triv)}条短录音({triv_cjk}字)未达分析门槛" if triv else ""))
M.append("")
M.append("## 📖 传不习乎 · 分析表达")
M.append("")
M.append("### 填充词")
M.append("")
if top:
    M.append("| 词 | 次数 | 每千字 |")
    M.append("|---|---|---|")
    for w, c in top[:10]:
        M.append(f"| {w} | {c} | {c * 1000 / max(n_cjk - triv_cjk, 1):.1f} |")
else:
    M.append("(未检测到常见填充词)")
M.append("")
M.append("### 表达观察")
M.append("")
M.extend("".join(obs_set) if obs_set else ["(今日无观察)"])
if pat_set:
    M.append("")
    M.extend(pat_set)
M.append("")
M.append("## 🤝 与朋友交而不信乎 · 承诺记录")
M.append("")
if promises:
    for p in promises:
        imp = "‼️" if p.get("importance") == "high" else ""
        M.append(f"- {imp}→ **{p.get('to', '?')}**: “{p.get('quote', '')}” (期限: {p.get('deadline_display', '无')})")
else:
    M.append("今日未识别到对他人的承诺")
if memorize:
    M.append("")
    M.append("### 要记住的事")
    M.append("")
    for m in memorize:
        M.append(f"- {m.get('text', '')} — {m.get('why', '')}")
if cactions:
    M.append("")
    M.append("### 联系人动态")
    M.append("")
    for c in cactions:
        M.append(f"- {c}")
M.append("")
M.append("## 🪞 吾日三省 · 自省报告")
M.append("")
M.append(f"- **为人谋而不忠乎**: {' '.join(sanxing.get('为人谋', [])) or '(今日无)'}")
M.append(f"- **与朋友交而不信乎**: {' '.join(sanxing.get('与朋友交', [])) or '(今日无)'}")
M.append(f"- **传不习乎**: {' '.join(sanxing.get('传习', [])) or '(今日无)'}")
if highlights:
    M.append("")
    M.append("### 原话摘录")
    M.append("")
    for q in highlights[:8]:
        M.append(f"> {q}")

md_path = os.path.join(REPORTS, f"{today}.md")
os.makedirs(REPORTS, exist_ok=True)
with open(md_path, "w", encoding="utf-8") as f:
    f.write("\n".join(M) + "\n")
print("日报md已生成(覆盖):", md_path)

# ---------- 备忘录 ----------
tail = []
if os.path.exists(COMMIT):
    tail = open(COMMIT, encoding="utf-8").read().splitlines()[-15:]
    tail = [t for t in tail if t.strip()]
body = []
body.append(f"<h1>三省 · {today}</h1>")
body.append("<p>" + inline(M[2].lstrip("> ")) + "</p>")
body.append("<hr>")
sec1 = M[M.index("## 📖 传不习乎 · 分析表达"):M.index("## 🤝 与朋友交而不信乎 · 承诺记录")]
sec2 = M[M.index("## 🤝 与朋友交而不信乎 · 承诺记录"):M.index("## 🪞 吾日三省 · 自省报告")]
sec3 = M[M.index("## 🪞 吾日三省 · 自省报告"):]
body.append(html_of_md_lines(sec1))
body.append("<hr>")
body.append(html_of_md_lines(sec2))
if tail:
    body.append("<h3>承诺台账(近15条)</h3>" + html_of_md_lines(tail))
body.append("<hr>")
body.append(html_of_md_lines(sec3))

r = subprocess.run(["osascript", os.path.join(ROOT, "bin", "as_note_upsert.applescript"),
                    f"三省 · {today}", "".join(body)], capture_output=True, text=True)
if r.returncode != 0:
    print("备忘录写入失败:", r.stderr.strip()[:300])
else:
    print(f"备忘录已更新: 三省 · {today}")
