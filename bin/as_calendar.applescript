# 为重要事项创建"三省"日历事件+双提醒(iPhone同步后等效闹钟: 到点响铃弹窗)
# 注: 日历建在系统默认账户(通常为iCloud, iPhone可同步)
on run argv
	set ttl to item 1 of argv
	set bdy to item 2 of argv
	set y to item 3 of argv as integer
	set mo to item 4 of argv as integer
	set dy to item 5 of argv as integer
	set hh to item 6 of argv as integer
	set mi to item 7 of argv as integer
	set d to current date
	set {year of d, month of d, day of d} to {y, mo, dy}
	set time of d to hh * hours + mi * minutes
	set d2 to d + 15 * minutes
	do shell script "open -g -a Calendar"
	delay 1
	tell application "Calendar"
		set targetCal to missing value
		repeat with c in calendars
			if name of c is "三省" then set targetCal to contents of c
		end repeat
		if targetCal is missing value then
			set targetCal to make new calendar with properties {name:"三省"}
		end if
		tell targetCal
			set ev to make new event with properties {summary:ttl, description:bdy, start date:d, end date:d2}
			tell ev
				make new display alarm with properties {trigger interval:0}
				make new sound alarm with properties {trigger interval:0, sound name:"Hero"}
			end tell
		end tell
	end tell
	return "ok"
end run
