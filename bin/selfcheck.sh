#!/bin/bash
# 三省流水线自检: 四项能力逐一验证(以launchd身份运行)
ROOT="$HOME/sanxing"
LOG="$ROOT/logs/selfcheck.log"
exec > >(tee -a "$LOG") 2>&1
echo "=== 自检开始 $(date '+%F %T') ==="

echo "[1/4] 完全磁盘访问(读语音备忘录容器)..."
VM=$(find "$HOME/Library/Containers/com.apple.VoiceMemos" "$HOME/Library/Group Containers/group.com.apple.VoiceMemos.shared" -type f -iname '*.m4a' -print 2>/dev/null | wc -l | tr -d ' ')
if [ "$VM" -gt 0 ]; then echo "    ✅ 可读取, 当前发现 $VM 个录音文件"; else echo "    ❌ 读不到(FDA未授予)"; fi

echo "[2/5] 备忘录API Key(只显示头尾, 不显示全文)..."
KEY=$(osascript "$ROOT/bin/as_key_read.applescript" 2>/dev/null | python3 -c "
import sys, re
t = re.sub(r'<[^>]+>', '', sys.stdin.read())
m = re.search(r'GLM_API_KEY\s*=\s*([A-Za-z0-9._\-]+)', t)
print(m.group(1) if m else '')")
if [ -n "$KEY" ]; then
  echo "    ✅ 找到: ${KEY:0:6}...${KEY: -4} (长度${#KEY})"
  echo "[3/5] API连通性(实时验证Key)..."
  echo "$KEY" | python3 -c "
import sys, json, urllib.request
key = sys.stdin.read().strip()
body = json.dumps({'model': 'glm-4.6', 'messages': [{'role': 'user', 'content': 'hi'}], 'max_tokens': 1}).encode()
req = urllib.request.Request('https://open.bigmodel.cn/api/paas/v4/chat/completions', data=body,
    headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        print('    ✅ Key有效, API返回', r.status)
except urllib.error.HTTPError as e:
    print('    ❌ Key无效: HTTP', e.code, '(请到 open.bigmodel.cn 重新复制Key并更新备忘录)')
except Exception as e:
    print('    ❌ 网络异常:', str(e)[:80])"
else
  echo "    ❌ 未找到(检查备忘录笔记中 GLM_API_KEY= 一行)"
  echo "[3/5] API连通性: 跳过"
fi

echo "[4/5] 提醒事项写入(会弹授权, 请点允许)..."
R=$(osascript "$ROOT/bin/as_reminder.applescript" "【三省自检】测试待办" "自检临时项, 随后自动删除" $(date -v+1M +%Y) $(date -v+1M +%m) $(date -v+1M +%d) $(date -v+1M +%H) $(date -v+1M +%M) 2>&1)
if echo "$R" | grep -q ok; then
  sleep 1
  osascript -e 'tell application "Reminders"' -e 'tell list "三省" to delete (every reminder whose name is "【三省自检】测试待办")' -e 'end tell' >/dev/null 2>&1 && echo "    ✅ 写入+删除成功" || echo "    ✅ 写入成功(测试项请手动删)"
else
  echo "    ❌ 失败: $(echo "$R" | head -1)"
fi

echo "[5/5] 日历闹钟写入(如已授权则无弹窗)..."
C=$(osascript "$ROOT/bin/as_calendar.applescript" "【三省自检】测试闹钟" "自检临时项, 随后自动删除" $(date -v+2M +%Y) $(date -v+2M +%m) $(date -v+2M +%d) $(date -v+2M +%H) $(date -v+2M +%M) 2>&1)
if echo "$C" | grep -q ok; then
  sleep 2
  osascript -e 'tell application "Calendar"' -e 'repeat with c in calendars' -e 'if name of c is "三省" then tell c to delete (every event whose summary is "【三省自检】测试闹钟")' -e 'end repeat' -e 'end tell' >/dev/null 2>&1 && echo "    ✅ 写入+删除成功" || echo "    ✅ 写入成功(测试项请手动删)"
else
  echo "    ❌ 失败: $(echo "$C" | head -1)"
fi

echo "=== 自检结束 ==="
