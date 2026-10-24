# 读取"三省"文件夹中指定名称笔记的正文(不存在返回空)
on run argv
	set nm to item 1 of argv
	do shell script "open -g -a Notes"
	delay 1
	tell application "Notes"
		if not (exists folder "三省") then return ""
		tell folder "三省"
			set hits to every note whose name is nm
			if (count of hits) is 0 then return ""
			return body of item 1 of hits
		end tell
	end tell
end run
