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
			else
				set body of item 1 of hits to bdy
				if (count of hits) > 1 then
					delete (items 2 thru -1 of hits)
				end if
			end if
		end tell
	end tell
	return "ok"
end run
