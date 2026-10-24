#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""消化"联系人确认"笔记里的回答:
读取备忘录选择题 -> 解析✅选择/=填空 -> 精确匹配联系人 -> 写事实+学习别名
-> 从待确认移除并重渲染笔记 -> 台账留痕。未回答的保留, 等用户下次编辑。"""
import os, datetime
import contacts_lib as cl

TAIZHANG = os.path.expanduser("~/sanxing/data/commitments/台账.md")
today = datetime.date.today().isoformat()

pending = cl.load_pending()
if not pending:
    cl.render_confirm_note()
    raise SystemExit(0)

lines = cl.read_confirm_note()
if not lines:
    print("确认笔记为空/不存在, 已重新渲染")
    cl.render_confirm_note()
    raise SystemExit(0)

answers = cl.parse_answers(lines, pending)
if not answers:
    print(f"{len(pending)}个待确认, 笔记中暂无回答(等待用户在备忘录选✅或填空)")
    raise SystemExit(0)

by_nick = {e["nick"]: e for e in pending}
actions, resolved = [], []
for nick, name in answers:
    hit = cl.find_exact(name)
    if not hit:
        print(f"· 「{nick}」回答的「{name}」在通讯录未精确找到, 保留待确认(请核对名字)")
        continue
    e = by_nick[nick]
    act = f"已记住: {nick} = {name}"
    if e.get("fact"):
        act = cl.apply_fact(hit, nick, e["fact"], e.get("value") or "", today) + f"; 已记住 {nick}={name}"
    cl.learn_alias(nick, name)
    actions.append(f"- {today} {act}")
    print("✅", act)
    resolved.append(nick)

if resolved:
    cl.save_pending([e for e in pending if e["nick"] not in resolved])
    cl.render_confirm_note()
    with open(TAIZHANG, "a", encoding="utf-8") as f:
        f.write("\n## 联系人动态\n")
        for a in actions:
            f.write(a + "\n")
    print(f"已消化{len(resolved)}条回答: {','.join(resolved)}")
