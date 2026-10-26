#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日报渲染器: 汇总某日全部录音的分析JSON -> 一份md报告(覆盖) + 备忘录笔记(更新)
无参数时渲染近2天内所有存在分析数据的日期(自动补跨零点/漏跑的日期)
三类分节: 📖传不习乎·分析表达 / 🤝与朋友交而不信乎·承诺记录 / 🪞吾日三省·自省报告"""
import os, re, json, glob, subprocess, datetime, sys

ROOT = os.path.expanduser("~/sanxing")
REPORTS = os.path.join(ROOT, "data", "reports")
COMMIT = os.path.join(ROOT, "data", "commitments", "台账.md")
ADIR_ROOT = os.path.join(ROOT, "data", "analysis")


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


def render(today):
    ADIR = os.path.join(ADIR_ROOT, today)
    files = sorted(glob.glob(os.path.join(ADIR, "*.json")))
    if not files:
        print(f"{today}: 无分析数据, 跳过")
        return
    recs = [json.load(open(f, encoding="utf-8")) for f in files]
    main = [r for r in recs if not r.get("trivial")]
    triv = [r for r in recs if r.get("trivial")]
    n_dur = sum(r["duration"] for r in recs)
    n_cjk = sum(r["chars"] for r in recs)
    triv_dur = sum(r["duration"] for r in triv)
    triv_cjk = sum(r["chars"] for r in triv)

    agg = {}
    for r in main:
        for w, c in (r.get("fillers") or {}).items():
            agg[w] = agg.get(w, 0) + c
    top = sorted(agg.items(), key=lambda x: -x[1])

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
        v = (L.get("filler_obs") or "").strip()
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

    # 跨录音聚合对话者洞察(带真名标签的他人)
    people = {}
    for r in main:
        for nm, pl in ((r.get("llm") or {}).get("people") or {}).items():
            tgt = people.setdefault(nm, {"viewpoint": [], "profile": [],
                                         "attitude": [], "expectations": [], "facts": []})
            for fld in tgt:
                for v in pl.get(fld, []):
                    if v not in tgt[fld]:
                        tgt[fld].append(v)

    n_llm_ok = sum(1 for r in main if r.get("llm"))
    M = []
    M.append(f"# 三省 · {today}")
    M.append("")
    M.append("## 📌 今日速览")
    M.append("")
    M.append(f"- 录音 **{len(recs)}** 段 · {n_dur // 60}分{n_dur % 60}秒 · {n_cjk}字 ｜ 完整分析 {n_llm_ok} 段"
             + (f" · 统计版 {len(main) - n_llm_ok} 段" if len(main) - n_llm_ok else "")
             + (f" · 短录音 {len(triv)} 段" if triv else ""))
    M.append(f"- 承诺 **{len(promises)}** 条"
             + (f"（‼️重要 {sum(1 for p in promises if p.get('importance') == 'high')} 条）" if promises else "")
             + f" ｜ 要记住 {len(memorize)} 条 ｜ 对话者 {len(people)} 人"
             + ("" if people else "（待声纹认人后解锁画像）"))
    if promises:
        for p in promises[:3]:
            imp = "‼️" if p.get("importance") == "high" else ""
            M.append(f"- {imp}→ **{p.get('to', '?')}**：{p.get('quote', '')[:40]}…（{p.get('deadline_display', '无')}）")
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
    M.append("  \n".join(obs_set) if obs_set else "(今日无观察)")
    if pat_set:
        M.append("")
        M.append("  \n".join(pat_set))
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
    if people:
        M.append("")
        M.append("## 👥 对话者洞察")
        M.append("")
        for nm, pl in people.items():
            M.append(f"### {nm}")
            for fld, lab in (("profile", "画像"), ("viewpoint", "观点"),
                             ("attitude", "与我的关系/态度"), ("expectations", "对我的期许"),
                             ("facts", "关键事实")):
                if pl.get(fld):
                    M.append(f"- **{lab}**: {'；'.join(pl[fld][:3])}")
            M.append("")
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
    print(f"{today}: 日报md已生成")

    tail = []
    if os.path.exists(COMMIT):
        tail = [t for t in open(COMMIT, encoding="utf-8").read().splitlines()[-15:] if t.strip()]
    body = []
    body.append(f"<h1>三省 · {today}</h1>")
    overview = M[M.index("## 📌 今日速览"):M.index("## 📖 传不习乎 · 分析表达")]
    body.append(html_of_md_lines(overview))
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
        print(f"{today}: 备忘录写入失败: {r.stderr.strip()[:200]}")
    else:
        print(f"{today}: 备忘录已更新 三省 · {today}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for d in sys.argv[1:]:
            render(d)
    else:
        dates = sorted(os.path.basename(d) for d in glob.glob(os.path.join(ADIR_ROOT, "20*")))
        for d in dates[-2:]:
            render(d)
