#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""联系人关联共享库
被 analyze.py(录音实时匹配/出题) 和 resolve_mentions.py(消化回答) 共用:
- 别名映射: 本地学习表(data/state/alias_map.json) + 备忘录手工笔记(联系人映射), 手工优先
- 挂起问题: data/state/pending_mentions.json, 渲染成备忘录"三省 · 联系人确认"选择题
"""
import os, re, json, time, subprocess, datetime

BIN = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.expanduser("~/sanxing")
STATE = os.path.join(ROOT, "data", "state")
ALIAS = os.path.join(STATE, "alias_map.json")
PENDING = os.path.join(STATE, "pending_mentions.json")
CONFIRM_NOTE = "三省 · 联系人确认"


def osascript(path, *args):
    r = subprocess.run(["osascript", os.path.join(BIN, path)] + [str(a) for a in args],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return r.stdout.strip()


def html_to_lines(html):
    t = re.sub(r"<br\s*/?>|</div>|</p>|<hr\s*/?>", "\n", html or "")
    t = re.sub(r"<[^>]+>", "", t).replace("&nbsp;", " ").replace("&amp;", "&")
    return [l.strip() for l in t.splitlines()]


# ---------- 别名映射 ----------
def load_alias_map():
    """合并: 备忘录手工映射(含"联系人映射"的笔记) + 本地学习表, 手工优先"""
    mp = {}
    if os.path.exists(ALIAS):
        try:
            mp.update(json.load(open(ALIAS, encoding="utf-8")))
        except Exception:
            pass
    r = subprocess.run(["osascript", "-e",
        'tell application "Notes"\n'
        'set hits to body of every note whose body contains "联系人映射"\n'
        'set out to ""\nrepeat with b in hits\nset out to out & b & linefeed\nend repeat\n'
        'return out\nend tell'], capture_output=True, text=True)
    if r.returncode == 0:
        for ln in html_to_lines(r.stdout):
            m = re.match(r"^([^=＝<>]{1,15})\s*[=＝]\s*(\S{1,40})$", ln)
            if m and m.group(1).strip() != "联系人映射":
                mp[m.group(1).strip()] = m.group(2).strip()
    return mp


def learn_alias(nick, fullname):
    cur = {}
    if os.path.exists(ALIAS):
        try:
            cur = json.load(open(ALIAS, encoding="utf-8"))
        except Exception:
            cur = {}
    cur[nick] = fullname
    os.makedirs(STATE, exist_ok=True)
    json.dump(cur, open(ALIAS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def find_exact(fullname):
    out = osascript("as_contacts.applescript", "search", fullname[:1]) or ""
    for l in out.splitlines():
        if not l.strip():
            continue
        parts = l.split("|")
        if len(parts) >= 2 and parts[1].strip() == fullname.strip():
            return parts[0].strip(), parts[1].strip(), (parts[2].strip() if len(parts) > 2 else "")
    return None


def apply_fact(hit, nick, fact, value, today):
    pid, cname, bd = hit
    if fact == "生日":
        ymd = re.search(r"(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})", value or "")
        if ymd and not bd:
            osascript("as_contacts.applescript", "setbirth", pid,
                      int(ymd.group(1)), int(ymd.group(2)), int(ymd.group(3)))
            return f"已为「{cname}」设置生日 {value} (来自“{nick}”)"
        osascript("as_contacts.applescript", "appendnote", pid,
                  f"{today} 录音提及({nick}) 生日:{value}")
        why = "已有生日" if bd else "未提供年份"
        return f"生日线索{value}已记入「{cname}」备注({why})"
    osascript("as_contacts.applescript", "appendnote", pid,
              f"{today} 录音提及({nick}) {fact}:{value}")
    return f"{fact}线索已记入「{cname}」备注: {value}"


# ---------- 挂起问题(选择题) ----------
def load_pending():
    if os.path.exists(PENDING):
        try:
            return json.load(open(PENDING, encoding="utf-8"))
        except Exception:
            return []
    return []


def save_pending(lst):
    os.makedirs(STATE, exist_ok=True)
    json.dump(lst, open(PENDING, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def add_pending(nick, fact=None, value=None, options=None):
    """新增/合并一条待确认; 同名已存在则补事实与候选"""
    lst = load_pending()
    for e in lst:
        if e["nick"] == nick:
            if fact and not e.get("fact"):
                e["fact"], e["value"] = fact, value
            if options:
                e["options"] = options
            save_pending(lst)
            return
    lst.append({"nick": nick, "fact": fact, "value": value, "options": options or []})
    save_pending(lst)


def render_confirm_note():
    body = ['<h1>联系人确认</h1>',
            '<p>回答方式：把选中那一行开头的 <b>▢ 改成 ✅</b>；'
            '或直接在填空行写 <b>称呼=名字</b>。改完双击「立即处理」即生效。</p><hr>']
    lst = load_pending()
    if not lst:
        body.append('<p>（当前没有待确认的联系人 🎉）</p>')
    for e in lst:
        body.append(f"<div>❓{e['nick']}</div>")
        if e.get("fact"):
            body.append(f"<div>录音提到：{e['fact']} = {e.get('value', '')}</div>")
        if e.get("options"):
            for o in e["options"]:
                body.append(f"<div>▢ {o}</div>")
            body.append("<div>都不是？先去「通讯录」App新建，再把下面这行等号后补上名字：</div>")
            body.append(f"<div>{e['nick']}=</div>")
        else:
            body.append("<div>通讯录里暂无此人。请先在「通讯录」App新建联系人，"
                        "再把下面这行等号后补上名字：</div>")
            body.append(f"<div>{e['nick']}=</div>")
        body.append("<hr>")
    osascript("as_note_upsert.applescript", CONFIRM_NOTE, "".join(body))


def read_confirm_note():
    # Notes新建笔记后短暂时间内按名查不到(索引延迟), 重试兜底
    for _ in range(3):
        out = osascript("as_note_read.applescript", CONFIRM_NOTE)
        if out and out.strip():
            return html_to_lines(out)
        time.sleep(2)
    return []


def parse_answers(lines, pending):
    """从确认笔记解析用户回答 -> [(nick, 选择的名字)], 未答/无效跳过"""
    answers = []
    cur = None
    for ln in lines:
        m = re.match(r"^❓\s*(.+)$", ln)
        if m:
            cur = m.group(1).strip()
            continue
        if cur is None:
            continue
        m = re.match(r"^[✅☑✓]\s*(.+)$", ln)
        if m:
            name = re.sub(r"^\d+[.、]\s*", "", m.group(1).strip())
            if name:
                answers.append((cur, name))
                cur = None
            continue
        m = re.match(r"^(.+?)\s*[=＝]\s*(.+)$", ln)
        if m and m.group(1).strip() == cur:
            v = m.group(2).strip()
            if v and "新名字" not in v and "新建的名字" not in v and not set(v) <= {"_", "＿", " "}:
                answers.append((cur, v))
                cur = None
    return [(n, v) for n, v in answers if n in {e["nick"] for e in pending}]
