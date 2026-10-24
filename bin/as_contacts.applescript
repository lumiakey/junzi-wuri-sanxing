# 通讯录操作: search <姓> | setbirth <联系人id> <年> <月> <日> | appendnote <联系人id> <文本>
on run argv
	set mode to item 1 of argv
	do shell script "open -g -a Contacts"
	delay 2
	tell application "Contacts"
		if mode is "search" then
			set sur to item 2 of argv
			set out to ""
			repeat with p in (every person whose name contains sur)
				set bd to ""
				try
					if birth date of p is not missing value then set bd to (birth date of p) as text
				end try
				set out to out & (id of p) & "|" & (name of p) & "|" & bd & linefeed
			end repeat
			return out
		else if mode is "setbirth" then
			set pid to item 2 of argv
			set y to item 3 of argv as integer
			set mo to item 4 of argv as integer
			set d to item 5 of argv as integer
			set theDate to current date
			set {year of theDate, month of theDate, day of theDate} to {y, mo, d}
			set birth date of (first person whose id is pid) to theDate
			save
			return "ok"
		else if mode is "appendnote" then
			set pid to item 2 of argv
			set addText to item 3 of argv
			set p to (first person whose id is pid)
			set oldNote to ""
			try
				set oldNote to note of p as text
			end try
			set note of p to (oldNote & linefeed & addText)
			save
			return "ok"
		end if
	end tell
	return "unknown-mode"
end run
