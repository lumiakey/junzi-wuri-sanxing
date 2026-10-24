#!/bin/bash
# 停用并卸载三省流水线(保留 data/ 数据目录)
launchctl bootout "gui/$(id -u)/com.sanxing.nightly" 2>/dev/null
rm -f "$HOME/Library/LaunchAgents/com.sanxing.nightly.plist" "$HOME/Library/LaunchAgents/com.sanxing.selfcheck.plist"
echo "✓ 定时任务已停用"
echo "数据与脚本保留在 ~/sanxing (确认不再需要可手动删除)"
echo "别忘了在 系统设置→隐私与安全性 里撤销 sanxing-bash 的完全磁盘访问"
