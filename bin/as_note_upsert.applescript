# 在"三省"文件夹创建或更新同名笔记(手动补跑不产生重复; 顺带清理同名重复笔记)
on run argv
	set nm to item 1 of argv
	set bdy to item 2 of argv
	do shell script "open -g -a Notes"
	delay 1
	tell application "Notes"
		if not (exists folder "三省") then
			make new folder with properties {name:"三省"}
		end if
		tell folder "三省"
			set hits to every note whose name is nm
			if (count of hits) is 0 then
				make new note with properties {name:nm, body:bdy}
				# 新建后索引延迟可能再查不到/或历史已存在多条, 二次核对去重
				delay 2
				set hits2 to every note whose name is nm
				repeat while (count of hits2) > 1
					delete item 2 of hits2
					set hits2 to every note whose name is nm
				end repeat
			else
				set body of item 1 of hits to bdy
				repeat while (count of hits) > 1
					delete item 2 of hits
					set hits to every note whose name is nm
				end repeat
			end if
		end tell
	end tell
	return "ok"
end run
