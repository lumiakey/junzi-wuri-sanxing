# 在"三省"清单创建待办。年月日时分全传0表示不设时间
on run argv
	set ttl to item 1 of argv
	set bdy to item 2 of argv
	set y to item 3 of argv as integer
	set mo to item 4 of argv as integer
	set dy to item 5 of argv as integer
	set hh to item 6 of argv as integer
	set mi to item 7 of argv as integer
	do shell script "open -g -a Reminders"
	delay 1
	tell application "Reminders"
		if not (exists list "三省") then
			make new list with properties {name:"三省"}
		end if
		tell list "三省"
			if y is 0 then
				make new reminder with properties {name:ttl, body:bdy}
			else
				set d to current date
				set {year of d, month of d, day of d} to {y, mo, dy}
				set time of d to hh * hours + mi * minutes
				make new reminder with properties {name:ttl, body:bdy, remind me date:d, due date:d}
			end if
		end tell
	end tell
	return "ok"
end run
