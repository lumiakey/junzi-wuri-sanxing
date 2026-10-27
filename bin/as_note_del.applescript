# 删除"三省"文件夹中所有名字包含给定关键词的笔记(供确认笔记重建前清理)
on run argv
	set kw to item 1 of argv
	do shell script "open -g -a Notes"
	delay 1
	tell application "Notes"
		if not (exists folder "三省") then return "ok"
		tell folder "三省"
			delete (every note whose name contains kw)
		end tell
	end tell
	return "ok"
end run
