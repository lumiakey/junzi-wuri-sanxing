#!/bin/bash
# 触发三省流水线(以launchd身份运行, 与每晚自动任务共用同一权限身份, 授权一次即可)
echo "三省流水线 · 手动触发"
echo "======================"
launchctl kickstart -k "gui/$(id -u)/com.sanxing.nightly"
echo "已触发(后台运行中)。首次运行若弹出权限确认, 请全部点允许。"
sleep 6
LATEST=$(ls -t "$HOME/sanxing/logs"/run-*.log 2>/dev/null | head -1)
[ -n "$LATEST" ] && tail -8 "$LATEST"
echo ""
read -p "按回车键关闭窗口..."
