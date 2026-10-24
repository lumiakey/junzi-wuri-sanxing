# AGENTS.md — 三省（junzi-wuri-sanxing）启动与操作手册

> 这份文件是给 **AI Agent / LLM** 读的。读完你应当能在 10 分钟内把这套装起来、跑通、并排障。
> 面向人类读者的项目介绍见 [README.md](README.md)。

---

## 0. 一句话说清这是什么

macOS 本机的一条**无人值守流水线**：iPhone/Apple Watch 全天候录音 → iCloud 同步到 Mac →
**本机** whisper 转写 → 云端 LLM 做结构化提取 → 写回**备忘录 / 提醒事项 / 日历 / 通讯录**。

- 安装根目录：`~/sanxing`
- 定时：每天 **23:30**（launchd，label `com.sanxing.nightly`）
- 每月费用：¥0（LLM 用有免费额度的 `glm-4-flash`）
- 出网的只有**文字稿**；音频永远留在本机

---

## 1. 前置条件（缺一项就装不成，先逐条核对）

| 项 | 要求 | 怎么验 |
|---|---|---|
| 系统 | macOS 13+（`codesign` / `launchctl bootstrap` 需要） | `sw_vers -productVersion` |
| Homebrew | 已安装 | `command -v brew` |
| 转写器 | `whisper-cpp`（提供 `whisper-cli`） | `command -v whisper-cli` |
| 音频工具 | `ffmpeg` + `ffprobe` | `command -v ffmpeg` |
| 磁盘 | ≥ 3 GB（模型 1.5 GB + 音频归档） | `df -h ~` |
| iCloud | iPhone 与 Mac **同一 Apple ID**，且「语音备忘录」同步已开 | 手动确认 |
| 常开 | Mac 夜间开机或至少 23:30 在线（休眠时 launchd 会在唤醒后补跑） | — |

**这一步你（Agent）可以自己跑：**

```bash
brew install whisper-cpp ffmpeg
mkdir -p ~/sanxing/models
curl -L -o ~/sanxing/models/ggml-large-v3-turbo.bin \
  https://hf-mirror.com/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin
```

模型文件约 1.5 GB，走 hf-mirror 国内镜像。**没有模型 `run.sh` 会直接退出**，不要跳过。

---

## 2. 安装（3 条命令）

```bash
git clone https://github.com/lumiakey/junzi-wuri-sanxing.git
cd junzi-wuri-sanxing
bash setup.sh
```

`setup.sh` 会做 5 件事，全部幂等：

1. 建目录 `~/sanxing/{bin,models,logs,data/...}`
2. 检查 `whisper-cli` / `ffmpeg`（缺就退出）
3. 生成**专用解释器** `~/sanxing/bin/sanxing-bash`（`/bin/bash` 的签名副本，用来承接「完全磁盘访问」权限；macOS 26 下 launchd 只认这个身份）
4. 写 `~/sanxing/config.env`（`GLM_API_KEY` / `GLM_MODEL` / `GLM_BASE`）
5. 装 LaunchAgent `com.sanxing.nightly`（23:30）+ 复制 `立即处理.command` 到 `~/sanxing/`

国内访问 GitHub 慢就把 clone 换成 `https://gitee.com/lumiakey/junzi-wuri-sanxing.git`，内容一致。

---

## 3. 必须由**人**完成的 3 步（Agent 做不了，别硬试）

TCC 权限和 API Key 都只能由用户在 GUI 里授予。装完直接把下面三行原样交给用户：

```
1. 系统设置 → 隐私与安全性 → 完全磁盘访问权限 → 点「+」→ Cmd+Shift+G 粘贴 ~/sanxing/bin/sanxing-bash → 打开
2. 备忘录新建一条笔记，正文只有一行：GLM_API_KEY=你的Key
   （Key 从 https://open.bigmodel.cn 拿；也可以直接写进 ~/sanxing/config.env）
3. 双击 ~/sanxing/立即处理.command → 首次会依次弹「控制备忘录/提醒事项/日历/通讯录」→ 全部点「允许」
```

为什么第 1 步非做不可：`run.sh` 要读
`~/Library/Containers/com.apple.VoiceMemos`，这是 TCC 保护目录，没有完全磁盘访问权限就读不到任何录音。

---

## 4. 验证（跑这一条就够）

```bash
~/sanxing/bin/sanxing-bash ~/sanxing/bin/selfcheck.sh
```

输出 5 项，全 ✅ 才算装好：

| 检查 | 期望 |
|---|---|
| [1/5] 完全磁盘访问 | `✅ 可读取, 当前发现 N 个录音文件`（N=0 说明手机还没录过，正常） |
| [2/5] 备忘录 API Key | `✅ 找到: sk-xxx...xxxx (长度NN)` |
| [3/5] API 连通性 | `✅ Key有效, API返回 200` |
| [4/5] 提醒事项写入 | `✅ 写入+删除成功` |
| [5/5] 日历闹钟写入 | `✅ 写入+删除成功` |

日志落在 `~/sanxing/logs/selfcheck.log`。

---

## 5. 跑一次 / 跑每天

```bash
# 手动触发（与定时任务同一权限身份，推荐）
launchctl kickstart -k "gui/$(id -u)/com.sanxing.nightly"

# 或前台直跑（调试用，日志直接打屏）
~/sanxing/bin/sanxing-bash ~/sanxing/bin/run.sh
```

定时由 `~/Library/LaunchAgents/com.sanxing.nightly.plist` 控制，默认 23:30。
改时间：编辑该 plist 的 `Hour` / `Minute`，然后

```bash
launchctl bootout "gui/$(id -u)/com.sanxing.nightly"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.sanxing.nightly.plist"
```

**必须用 `~/sanxing/bin/sanxing-bash` 执行，不能用 `bash`**——换解释器就丢了完全磁盘访问权限，读不到录音。

---

## 6. 配置

优先级：**环境变量 → `~/sanxing/config.env` → 备忘录里 `GLM_API_KEY=` 那一行**

```bash
# ~/sanxing/config.env
GLM_API_KEY=
GLM_MODEL=glm-4-flash
# GLM_BASE=https://open.bigmodel.cn/api/paas/v4/chat/completions
```

- 任意 OpenAI 兼容端点都能用：改 `GLM_BASE` + `GLM_MODEL` 即可（DeepSeek / 通义 / 本地 vLLM…）
- Key 写在备忘录里的好处：换 Key 不用碰 Mac，手机上改一行就行
- 模型额度不足（HTTP 429 且报文含 `1113`）会自动降级到 `glm-4-flash`，日报不会中断

---

## 7. 数据都在哪（排障必看）

```
~/sanxing/
├── bin/                    脚本（run.sh 主流水线、analyze.py、publish_note.py…）
├── models/ggml-large-v3-turbo.bin
├── config.env
├── 立即处理.command         双击手动触发
├── logs/
│   ├── run-YYYYMMDD-HHMMSS.log   每次运行日志（最新一条看这个）
│   ├── launchd.log                launchd 的 stdout/stderr
│   └── selfcheck.log
└── data/
    ├── inbox/              手动投放的音频（不限时间，放进去就会被处理）
    ├── archive/audio/      已处理音频归档（转写成功后才留）
    ├── transcripts/        转写产物 .txt + .srt
    ├── analysis/YYYY-MM-DD/*.json   每条录音的结构化结果（LLM 原始输出）
    ├── reports/YYYY-MM-DD.md        当天汇总日报（md）
    ├── commitments/台账.md           承诺台账（append-only）
    └── state/
        ├── processed.txt        已处理清单（`文件名|大小`，去重用）
        ├── alias_map.json       学到的称呼→联系人映射
        └── pending_mentions.json 待用户确认的联系人歧义
```

数据目录已 gitignore，随时可删可迁移。

---

## 8. 产出长什么样（判断"跑通了"的标准）

- **备忘录**：文件夹 `三省` 下的 `三省 · YYYY-MM-DD`，三节——📖 传不习乎（填充词表 + 表达观察）／🤝 与朋友交（承诺 + 要记住的事 + 联系人动态）／🪞 吾日三省（三问）
- **提醒事项**：清单 `三省`，每条标题形如 `承诺→老张: 今晚肯定改好`
- **日历**：日历 `三省`，只收 `importance=high` 且有明确期限的承诺，事件名以 `⏰` 开头，带双提醒（弹窗 + Hero 铃声）
- **通讯录**：命中的人追加备注（`2026-10-24 录音提及(老张) 生日:03-15`），生日字段能解析就直接写入
- **歧义处理**：拿不准「老X是谁」时，备忘录生成 `三省 · 联系人确认` 选择题；用户把 `▢` 改成 `✅`（或写 `老X=张三`），下次跑流水线自动消化并终身记住

---

## 9. 常见故障对照表

| 症状 | 原因 | 修法 |
|---|---|---|
| `未读到语音备忘录录音(未授权完全磁盘访问时属正常)` | `sanxing-bash` 没拿到 FDA，或用了普通 `bash` | 重做第 3 步第 1 条；确认执行者是 `~/sanxing/bin/sanxing-bash` |
| `错误: 模型未就绪` | 模型没下 / 路径不对 | 重下到 `~/sanxing/models/ggml-large-v3-turbo.bin` |
| 录音明明有，但没被处理 | `run.sh` 只扫近 **2 天**（`MAX_AGE_DAYS=2`，按文件名 `YYYYMMDD` 判日期，因为 iCloud 会把 mtime 重置成同步时刻） | 把文件 `cp` 到 `~/sanxing/data/inbox/`（inbox 不限时间）再跑 |
| 备忘录里没有日报 | 当天没有 `analysis/*.json`，`publish_note.py` 会 `跳过发布` | 先确认转写产物存在；再确认 `data/analysis/<今天>/` 非空 |
| 日报有，但没有承诺/提醒 | LLM 未返回（Key 无效 / 额度用尽 / 语料 < 10 字） | 看 `logs/run-*.log` 里 `GLM分析失败`；`<10 字` 的录音会被标记 `trivial` 直接跳过 |
| `osascript ... 失败: Not authorized` | 自动化权限没给 | 系统设置 → 隐私与安全性 → 自动化，勾上对应 App |
| 联系人选择题答案不生效 | 名字与通讯录不完全一致 | 答案必须是通讯录里的**完整姓名**；不确定就先在通讯录建好再填 `老X=张三` |
| 改了仓库代码但没生效 | `setup.sh` 用 `cp -n`（不覆盖） | `cp bin/* ~/sanxing/bin/ && chmod +x ~/sanxing/bin/*.sh` |
| `launchctl` 报 `Bootstrap failed: 5` | 旧 plist 还挂着 | `launchctl bootout "gui/$(id -u)/com.sanxing.nightly"` 后重新 bootstrap |

---

## 10. 卸载

```bash
bash uninstall.sh          # 停定时任务 + 删 LaunchAgent，保留 ~/sanxing 数据
rm -rf ~/sanxing           # 确认不要数据后再手动删
```

别忘了在 系统设置 → 隐私与安全性 → 完全磁盘访问权限 里移除 `sanxing-bash`。

---

## 11. Agent 操作纪律（重要）

**可以自己做的：**
- 装依赖、下模型、clone、跑 `setup.sh`、跑 `selfcheck.sh`、跑 `run.sh`
- 读 `logs/` 和 `data/analysis/` 定位问题、改 `config.env`、改 plist 时间
- 用 `data/inbox/` 投放测试音频验证链路

**必须交给人做的：**
- 授予完全磁盘访问权限、点自动化授权弹窗
- 提供并填写 `GLM_API_KEY`
- 在备忘录里做联系人选择题

**绝对不要：**
- 用 `bash` 代替 `~/sanxing/bin/sanxing-bash` 跑 `run.sh`（会静默读不到录音，看起来像"没坏但没数据"）
- 删除或重置 `data/state/processed.txt`（会导致全部历史录音重跑重扣额度）
- 清空 `data/commitments/台账.md`（这是用户唯一不可再生的资产）
- 把 `config.env`、`data/`、`models/*.bin`、`*.wav` 提交进 git（`.gitignore` 已覆盖，别手贱 `-f`）
- 未经用户同意就上传任何音频或转写文本到第三方

**判断"装好了"的唯一标准**：`selfcheck.sh` 5 项全 ✅，且手动触发后 `logs/run-*.log` 出现 `=== 完成: 本次新处理 N 个录音 ===`。
N=0 且没有报错，通常只是手机还没录过音——不是故障。

---

## 12. 最小可用路径（只想看效果，5 分钟）

```bash
brew install whisper-cpp ffmpeg
mkdir -p ~/sanxing/models && curl -L -o ~/sanxing/models/ggml-large-v3-turbo.bin \
  https://hf-mirror.com/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin
git clone https://github.com/lumiakey/junzi-wuri-sanxing.git && cd junzi-wuri-sanxing && bash setup.sh
# 人工：授予 FDA + 填 Key
cp 任意一段中文录音.m4a ~/sanxing/data/inbox/     # 或直接用手机录一条
launchctl kickstart -k "gui/$(id -u)/com.sanxing.nightly"
tail -30 "$(ls -t ~/sanxing/logs/run-*.log | head -1)"
open -a Notes      # 看「三省」文件夹里的当日日报
```

---

MIT License · 录音涉及他人请遵守当地法律法规
