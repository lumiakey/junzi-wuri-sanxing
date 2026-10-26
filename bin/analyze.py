#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单条录音分析: 统计 + GLM提取(承诺/记住的事/联系人事实) -> JSON落盘
副作用: 提醒事项/日历闹钟/承诺台账/通讯录补全。日报渲染由 publish_note.py 汇总完成。
用法: analyze.py <transcript.txt> <transcript.srt> <秒数> <原始音频路径>
API Key 读取顺序: 环境变量 -> config.env -> 备忘录中含 GLM_API_KEY= 的笔记
"""
import sys, os, re, json, time, subprocess, urllib.request, datetime
import contacts_lib as cl

TXT, SRT, DUR, AUDIO = sys.argv[1], sys.argv[2], int(sys.argv[3] or 0), sys.argv[4]
ROOT = os.path.expanduser("~/sanxing")
BIN = os.path.join(ROOT, "bin")
CFG = os.path.join(ROOT, "config.env")


def osascript(path, *args):
    r = subprocess.run(["osascript", os.path.join(BIN, path)] + [str(a) for a in args],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"AppleScript {path} 失败: {r.stderr.strip()[:200]}")
        return None
    return r.stdout.strip()


def read_key_from_notes():
    out = osascript("as_key_read.applescript")
    if not out:
        return ""
    m = re.search(r"GLM_API_KEY\s*=\s*([A-Za-z0-9._\-]+)", re.sub(r"<[^>]+>", "", out))
    return m.group(1) if m else ""


api_key = os.environ.get("GLM_API_KEY", "")
model = os.environ.get("GLM_MODEL", "glm-5.3-flash")
if os.path.exists(CFG):
    for line in open(CFG, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if k == "GLM_API_KEY" and not api_key:
                api_key = v.strip()
            if k == "GLM_MODEL" and v.strip():
                model = v.strip()
if not api_key:
    api_key = read_key_from_notes()

text = open(TXT, encoding="utf-8").read()
srt_text = open(SRT, encoding="utf-8").read()

# 说话人分离结果: 存在 .spk.txt 则用带标签转写, 统计只算"我"的发言
SPK = SRT[: SRT.rfind(".")] + ".spk.txt"
has_spk = os.path.exists(SPK)
spk_lines = open(SPK, encoding="utf-8").read().splitlines() if has_spk else []
me_lines = [re.sub(r"^\[[^\]]*\]\s*", "", l.split(":", 1)[1]) for l in spk_lines if "] 我:" in l]
has_me = len(me_lines) > 0
stat_text = "".join(me_lines) if has_me else text
cjk = len(re.findall(r"[\u4e00-\u9fff]", stat_text))
dur_min = max(DUR / 60.0, 0.01)

# 日期按录音文件名归属(避免23:30任务跑过零点后错记到次日)
_m = re.search(r"(\d{4})(\d{2})(\d{2})_\d{6}-", os.path.basename(AUDIO))
today = f"{_m.group(1)}-{_m.group(2)}-{_m.group(3)}" if _m else datetime.date.today().isoformat()

FILLERS = ["然后", "就是", "那个", "这个", "其实", "怎么说", "嗯", "额", "呃",
           "对吧", "对不对", "你知道吗", "基本上", "反正", "就是说", "然后呢",
           "老实说", "事实上", "的话", "一下"]
fillers = {w: stat_text.count(w) for w in FILLERS if stat_text.count(w) > 0}


def srt_segments(s):
    out, ts, buf = [], None, []
    for ln in s.splitlines():
        if "-->" in ln:
            ts = ln.split("-->")[0].strip()[:5]
            continue
        if ln.strip() == "":
            if buf and ts:
                out.append((ts, "".join(buf)))
            buf = []
            continue
        if re.match(r"^\d+$", ln.strip()):
            continue
        buf.append(ln.strip())
    if buf and ts:
        out.append((ts, "".join(buf)))
    return out


def chunk_segments(segs, limit=12000):
    chunks, cur, size = [], [], 0
    for t, x in segs:
        ln = len(x) + 8
        if cur and size + ln > limit:
            chunks.append(cur)
            cur, size = [], 0
        cur.append((t, x))
        size += ln
    if cur:
        chunks.append(cur)
    return chunks


# 模型链: 优先config指定的模型, 额度不足(429/1113)时自动降级, 保证日报不中断
MODELS = [model]
if model != "glm-4-flash":
    MODELS.append("glm-4-flash")
ACTIVE = 0


def call_glm(seg_md, idx, total, date_iso=None):
    global ACTIVE
    today = datetime.date.fromisoformat(date_iso) if date_iso else datetime.date.today()
    weekday = "一二三四五六日"[today.weekday()]
    sys_prompt = (
        "你是用户的自省助手。输入是用户当天说话录音的转写(带时间戳,用户视角录音,"
        "他人话语可能不清晰)。"
        + ("**本次输入带说话人标签: '我:'是用户本人, 其余标签(如'说话人X:'或人名如'老X:')是他人。"
           "承诺/口头禅/表达习惯/三省只从'我:'的发言提取; 他人发言仅作上下文"
           "(用于确认对象与期限, 如对方说'你明天发我'且我回应'好'即为我的承诺)。"
           "若本段没有'我:'的发言, 相应字段给空值。**" if has_spk else "")
        + "只输出一个JSON对象,不要任何其他文字:\n"
        '{"promises":[{"time":"mm:ss","quote":"原话","to":"说给谁(推断,未知填?)",'
        '"deadline_display":"期限的人话描述或无",'
        '"deadline_iso":"YYYY-MM-DDTHH:MM,无明确期限填null,只有日期默认当天09:00",'
        '"importance":"high或normal,high=有明确期限且后果重要"}],'
        '"memorize":[{"text":"要记住的事","why":"为什么值得记","deadline_iso":"相关时间或null"}],'
        '"mentions":[{"name":"录音中对某人的称呼,如老X/王总","fact":"生日|电话|职位|公司|爱好|其它",'
        '"value":"具体值,生日用YYYY-MM-DD或MM-DD","evidence":"原话依据"}],'
        '"filler_obs":"对填充词和表达习惯的2-3句具体观察",'
        '"patterns":"表达模式2-3句(句长/语气/重复/口头禅组合)",'
        '"sanxing":{"为人谋":"今天答应别人/替别人做的事与诚意,1-2句",'
        '"与朋友交":"沟通中的诚信与温度,1-2句",'
        '"传习":"今天口头暴露的坏习惯或值得保持的优点,1-2句"},'
        '"quote_highlights":["当天最有自省价值的原话1-3条"],'
        '"people":[{"name":"带真名标签的他人(仅人名,匿名说话人X不分析)",'
        '"viewpoint":"此人表达的核心观点,1-2句",'
        '"profile":"人物画像:身份角色/关注点/说话风格,中性客观",'
        '"attitude":"与我(用户)的关系和态度,中性描述不评判,无信息填无",'
        '"expectations":"对我的要求/期盼/诉求,无则填无",'
        '"facts":"提到的关键事实(数字/日期/事件),无则填无"}]}\n'
        "承诺判定: 说话人向他人许下的我会/我明天/下周/某日前+动作均算, 模糊客套deadline_iso填null; "
        "memorize收录应记住的事项; mentions只收录音中明确说出的某人的具体事实(如某人生日几号), "
        "没有就给空数组,不要臆测; people只收录带真名标签的他人, 全部匿名则给空数组。"
        "无论内容多么重复或嘈杂, 都必须输出结构完整的非空JSON对象"
        "(数组字段可为[]), 严禁只输出{}。"
    )
    head = f"今天是{today.isoformat()}星期{weekday}。\n"
    if total > 1:
        head += f"(这是当天录音的第{idx + 1}/{total}段转写,请独立分析本段)\n"
    for attempt in range(5):
        m = MODELS[min(ACTIVE, len(MODELS) - 1)]
        body = json.dumps({"model": m,
                           "messages": [
                               {"role": "system", "content": sys_prompt},
                               {"role": "user", "content": head + seg_md}],
                           "temperature": 0.3,
                           "max_tokens": 4096}).encode()
        req = urllib.request.Request(
            "https://open.bigmodel.cn/api/paas/v4/chat/completions", data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.load(r)
            raw = data["choices"][0]["message"]["content"].strip()
            raw = re.sub(r"^```(json)?|```$", "", raw, flags=re.M).strip()
            obj = json.loads(raw)
            if not isinstance(obj, dict) or not obj:
                fr = data["choices"][0].get("finish_reason", "?")
                raise json.JSONDecodeError(f"空JSON(finish={fr},raw={raw[:60]!r})", raw[:100], 0)
            return obj
        except urllib.error.HTTPError as e:
            msg = ""
            try:
                msg = e.read().decode("utf-8", "ignore")[:200]
            except Exception:
                pass
            if e.code == 429 and "1113" in msg and ACTIVE < len(MODELS) - 1:
                ACTIVE += 1
                print(f"模型{m}无可用额度, 本次降级为{MODELS[ACTIVE]}")
                continue
            print(f"GLM分析失败(第{idx + 1}/{total}段) HTTP{e.code}: {msg[:80]}")
            return None
        except json.JSONDecodeError as e:
            if attempt < 4:
                wait = 8 * (attempt + 1)
                print(f"第{idx + 1}段JSON不完整({str(e)[:70]}), {wait}秒后重试")
                time.sleep(wait)
                continue
            print(f"GLM分析失败(第{idx + 1}/{total}段):", e)
            return None
        except Exception as e:
            if "timed out" in str(e).lower() and attempt < 2:
                print(f"第{idx + 1}段请求超时, {3 * (attempt + 1)}秒后重试")
                time.sleep(3 * (attempt + 1))
                continue
            print(f"GLM分析失败(第{idx + 1}/{total}段):", e)
            return None
    return None


def merge_results(rs):
    out = {"promises": [], "memorize": [], "mentions": [], "quote_highlights": [], "people": {},
           "filler_obs": "", "patterns": "", "sanxing": {}}
    seen = set()

    def key(s):
        return re.sub(r"\s", "", s or "")

    for r in rs:
        if not r:
            continue
        for p in r.get("promises", []):
            if key(p.get("quote")) and key(p["quote"]) not in seen:
                seen.add(key(p["quote"]))
                out["promises"].append(p)
        for m in r.get("memorize", []):
            if key(m.get("text")) and key(m["text"]) not in seen:
                seen.add(key(m["text"]))
                out["memorize"].append(m)
        for m in r.get("mentions", []):
            k = key(m.get("name")) + "|" + key(m.get("fact"))
            if k not in seen:
                seen.add(k)
                out["mentions"].append(m)
        for q in r.get("quote_highlights", []):
            if q and q not in out["quote_highlights"]:
                out["quote_highlights"].append(q)
        for pl in r.get("people", []):
            nm = (pl.get("name") or "").strip()
            if not nm or nm.startswith("说话人"):
                continue
            tgt = out["people"].setdefault(nm, {"viewpoint": [], "profile": [],
                                               "attitude": [], "expectations": [], "facts": []})
            for fld in tgt:
                v = (pl.get(fld) or "").strip()
                if v and v != "无" and v not in tgt[fld]:
                    tgt[fld].append(v)
        for field in ("filler_obs", "patterns"):
            v = (r.get(field) or "").strip()
            if v:
                out[field] = (out[field] + " " + v).strip()[:600]
        for k2, v in (r.get("sanxing") or {}).items():
            if v:
                out["sanxing"][k2] = (out["sanxing"].get(k2, "") + " " + v).strip()
    return out


llm = None
skip_reason = None
if api_key and cjk >= 10:
    if has_spk:
        # 折叠whisper复读循环(连续相同文本只留2次), 防止模型对重复垃圾输出空JSON
        dedup, last, cnt = [], "", 0
        for l in spk_lines:
            body_l = re.sub(r"^\[[^\]]*\]\s*[^:]*:\s*", "", l).strip()
            if body_l == last:
                cnt += 1
                if cnt > 2:
                    continue
            else:
                last, cnt = body_l, 0
            dedup.append(l)
        spk_lines = dedup
        # 带说话人标签: 按行分块
        chunks_txt, cur, size = [], [], 0
        for l in spk_lines:
            if cur and size + len(l) > 12000:
                chunks_txt.append("\n".join(cur))
                cur, size = [], 0
            cur.append(l)
            size += len(l) + 1
        if cur:
            chunks_txt.append("\n".join(cur))
        seg_texts = chunks_txt
    else:
        segs = srt_segments(srt_text)
        if segs:
            seg_texts = ["\n".join(f"[{t}] {x}" for t, x in ch) for ch in chunk_segments(segs)]
        else:
            raw = text.strip()
            seg_texts = [raw[i:i + 12000] for i in range(0, len(raw), 12000)]
    print(f"GLM分析: {'我的' if has_me else ''}语料{cjk}字, 分{len(seg_texts)}段调用" + (" (带说话人标签)" if has_spk else ""))
    results = []
    for i, seg_md in enumerate(seg_texts):
        if i:
            time.sleep(1)
        results.append(call_glm(seg_md, i, len(seg_texts), today))
    llm = merge_results(results) if any(results) else None
    if llm is None:
        print("GLM全部分析失败(本条降级为统计)")
elif not api_key:
    print("未找到GLM API Key(环境变量/config.env/备忘录笔记均无)")
elif cjk < 10:
    skip_reason = f"语料仅{cjk}字(不足10字门槛)"


def parse_iso(s):
    if not s or s == "null":
        return None
    try:
        return datetime.datetime.fromisoformat(str(s)[:16])
    except ValueError:
        return None


contact_actions = []

# ---- 联动苹果三件套 ----
if llm:
    ps = llm.get("promises", [])
    mem = llm.get("memorize", [])
    # 承诺 -> 提醒事项(重要承诺再加日历闹钟)
    for p in ps:
        dt = parse_iso(p.get("deadline_iso"))
        quote = p.get("quote", "")
        title = f"承诺→{p.get('to', '?')}: {quote[:40]}"
        body_ = f"期限:{p.get('deadline_display', '无')} | 原话:“{quote}” | 录于[{p.get('time', '?')}]"
        if dt:
            osascript("as_reminder.applescript", title, body_,
                      dt.year, dt.month, dt.day, dt.hour, dt.minute)
        else:
            osascript("as_reminder.applescript", title, body_, 0, 0, 0, 0, 0)
        if p.get("importance") == "high" and dt:
            osascript("as_calendar.applescript", f"⏰{title[:45]}", body_,
                      dt.year, dt.month, dt.day, dt.hour, dt.minute)
    # 记住的事 -> 提醒事项
    for m in mem:
        dt = parse_iso(m.get("deadline_iso"))
        t = f"记住: {m.get('text', '')[:50]}"
        b = m.get("why", "")
        if dt:
            osascript("as_reminder.applescript", t, b,
                      dt.year, dt.month, dt.day, dt.hour, dt.minute)
        else:
            osascript("as_reminder.applescript", t, b, 0, 0, 0, 0, 0)
    # 承诺台账
    if ps:
        with open(os.path.join(ROOT, "data", "commitments", "台账.md"), "a", encoding="utf-8") as f:
            for p in ps:
                dt = parse_iso(p.get("deadline_iso"))
                mark = "‼️" if p.get("importance") == "high" else ""
                f.write(f"- [ ] {today} {mark}→{p.get('to', '?')}: “{p.get('quote', '')}” "
                        f"期限:{dt.strftime('%m-%d %H:%M') if dt else p.get('deadline_display', '无')}\n")
    # 提到的人的事实 -> 关联通讯录(别名优先; 姓氏唯一匹配; 否则备忘录"联系人确认"选择题)
    PREFIX = re.compile(r"^[老小阿大]")
    SUFFIX = re.compile(r"[哥姐弟妹叔阿姨总工师长]$")
    JUNK = {"朋友", "同事", "家人", "亲戚", "同学"}
    amap = cl.load_alias_map()
    for m0 in llm.get("mentions", []):
        nick = (m0.get("name") or "").strip()
        fact = (m0.get("fact") or "").strip()
        value = (m0.get("value") or "").strip()
        if not nick or not fact or not value:
            continue
        if value in JUNK or fact == value:
            fact, value = None, None  # 无效事实(如"朋友:朋友"), 仅作身份确认
        if nick in amap:
            hit = cl.find_exact(amap[nick])
            if hit:
                if fact:
                    contact_actions.append(cl.apply_fact(hit, nick, fact, value, today))
                continue
            contact_actions.append(f"映射「{nick}→{amap[nick]}」失效(联系人改名?), 转入确认笔记")
        sur = SUFFIX.sub("", PREFIX.sub("", nick))
        sur = (sur or nick)[0]
        out = osascript("as_contacts.applescript", "search", sur) or ""
        cands = [l.split("|") for l in out.splitlines() if l.strip()]
        if len(cands) == 1:
            pid, cname = cands[0][0], cands[0][1]
            bd = cands[0][2] if len(cands[0]) > 2 else ""
            if fact:
                contact_actions.append(cl.apply_fact((pid, cname, bd), nick, fact, value, today))
            else:
                cl.learn_alias(nick, cname)
                contact_actions.append(f"姓氏唯一匹配, 已记住: {nick} = {cname}")
        else:
            cl.add_pending(nick, fact, value, [c[1] for c in cands[:6]])
            if cands:
                contact_actions.append(f"「{nick}」有{len(cands)}位{sur}姓候选, 已写入确认笔记待你选择")
            else:
                contact_actions.append(f"「{nick}」通讯录无此人, 已写入确认笔记提醒新建")
    cl.render_confirm_note()

# ---- 结构化结果落盘(供日报渲染器汇总) ----
ADIR = os.path.join(ROOT, "data", "analysis", today)
os.makedirs(ADIR, exist_ok=True)
base = os.path.splitext(os.path.basename(AUDIO))[0]
with open(os.path.join(ADIR, base + ".json"), "w", encoding="utf-8") as f:
    json.dump({"file": os.path.basename(AUDIO), "duration": DUR, "chars": cjk,
               "fillers": fillers, "trivial": cjk < 10, "skip_reason": skip_reason,
               "llm": llm, "contact_actions": contact_actions,
               "generated": datetime.datetime.now().isoformat(timespec="seconds")},
              f, ensure_ascii=False, indent=1)
print("分析JSON已落盘:", base)
