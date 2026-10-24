# 从备忘录中读取含 GLM_API_KEY= 的笔记正文(可能有多条, 全部返回拼接)
do shell script "open -g -a Notes"
delay 1
tell application "Notes"
	set hits to body of every note whose body contains "GLM_API_KEY="
	set out to ""
	repeat with b in hits
		set out to out & b & linefeed
	end repeat
	return out
end tell
