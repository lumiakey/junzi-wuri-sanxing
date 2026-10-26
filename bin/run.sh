# 三省流水线主脚本: 发现新录音 -> 归档 -> 转写 -> 分析 -> 报告
# 必须由 ~/sanxing/bin/sanxing-bash 执行(它持有完全磁盘访问权限, 才能读语音备忘录容器)
set -u
ROOT="$HOME/sanxing"
INBOX="$ROOT/data/inbox"
ARCHIVE="$ROOT/data/archive/audio"
TRANS="$ROOT/data/transcripts"
STATE="$ROOT/data/state/processed.txt"
LOGDIR="$ROOT/logs"
MODEL="$ROOT/models/ggml-large-v3-turbo.bin"
WHISPER="/opt/homebrew/bin/whisper-cli"
FFMPEG="/opt/homebrew/bin/ffmpeg"
FFPROBE="/opt/homebrew/bin/ffprobe"

mkdir -p "$INBOX" "$ARCHIVE" "$TRANS" "$LOGDIR" "$ROOT/data/reports" "$ROOT/data/commitments" "$ROOT/data/state"
touch "$STATE"
LOG="$LOGDIR/run-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1
echo "=== 三省流水线开始 $(date '+%Y-%m-%d %H:%M:%S') ==="

if [ ! -f "$MODEL" ]; then
  echo "错误: 模型未就绪 $MODEL"
  exit 1
fi

# 收集候选: inbox手动投放(不限时间) + 语音备忘录容器(仅近MAX_AGE_DAYS天)
# 注意: iCloud同步会把文件mtime重置为同步时刻, 故按文件名开头的YYYYMMDD判断真实录音日期
MAX_AGE_DAYS=2
CUTOFF=$(date -v-${MAX_AGE_DAYS}d +%F)
TMP_LIST="$ROOT/data/state/.candidates"
: > "$TMP_LIST"
find "$INBOX" -maxdepth 1 -type f \( -iname '*.m4a' -o -iname '*.mp3' -o -iname '*.wav' -o -iname '*.aac' \) -print 2>/dev/null >> "$TMP_LIST"
VM_COUNT=0
find "$HOME/Library/Containers/com.apple.VoiceMemos" \
     "$HOME/Library/Group Containers/group.com.apple.VoiceMemos.shared" \
     -type f -iname '*.m4a' -print 2>/dev/null | while IFS= read -r f; do
  B="$(basename "$f")"
  D=$(echo "$B" | grep -oE '^[0-9]{8}' | head -1)
  if [ -n "$D" ]; then
    FD="${D:0:4}-${D:4:2}-${D:6:2}"
    if [[ "$FD" > "$CUTOFF" || "$FD" == "$CUTOFF" ]]; then echo "$f"; fi
  else
    MT=$(stat -f '%Sm' -t '%F' "$f" 2>/dev/null)
    if [[ "$MT" > "$CUTOFF" || "$MT" == "$CUTOFF" ]]; then echo "$f"; fi
  fi
done >> "$TMP_LIST"
VM_COUNT=$(grep -c "VoiceMemos" "$TMP_LIST" || true)
if [ "$VM_COUNT" -eq 0 ]; then
  echo "提示: 未读到语音备忘录录音(未授权完全磁盘访问时属正常), 本次仅处理inbox"
fi

NEW=0
# 消化联系人线索与声音认人回答(用户在备忘录里的答案)
python3 "$ROOT/bin/resolve_mentions.py" || echo "线索消化异常(不影响后续)"
python3 "$ROOT/bin/resolve_voices.py" || echo "声音认人消化异常(不影响后续)"

# 声纹注册: inbox里出现命名为"声纹注册"的音频则更新注册样本(30-60秒本人真声)
REG_SRC=$(ls "$INBOX" 2>/dev/null | grep -i "声纹注册" | head -1 || true)
if [ -n "$REG_SRC" ]; then
  if "$FFMPEG" -y -v error -i "$INBOX/$REG_SRC" -ar 16000 -ac 1 "$ROOT/data/state/声纹注册.wav"; then
    mv "$INBOX/$REG_SRC" "$ARCHIVE/" && echo "✅ 声纹注册已更新(来自 $REG_SRC)"
  fi
fi
while IFS= read -r f; do
  [ -z "$f" ] && continue
  BASE="$(basename "$f")"
  SIZE="$(stat -f%z "$f" 2>/dev/null || echo 0)"
  KEY="$BASE|$SIZE"
  grep -qF "$KEY" "$STATE" && continue

  echo "--- 处理: $f"
  MTIME="$(stat -f '%Sm' -t '%Y-%m-%d_%H%M%S' "$f" 2>/dev/null || date +%Y-%m-%d_%H%M%S)"
  SAFE="$(echo "$BASE" | tr ' /' '__' | tr -d '"')"
  STASH="$ARCHIVE/${MTIME}_${SAFE}"
  cp "$f" "$STASH" || { echo "复制失败, 跳过"; continue; }

  DUR="$("$FFPROBE" -v error -show_entries format=duration -of csv=p=0 "$STASH" 2>/dev/null | cut -d. -f1)"
  [ -z "$DUR" ] && DUR=0

  WAV="$ROOT/data/state/.tmp_$$.wav"
  "$FFMPEG" -y -v error -i "$STASH" -ar 16000 -ac 1 "$WAV" || { rm -f "$WAV"; echo "转码失败"; continue; }

  OUTBASE="$TRANS/${MTIME}_$(echo "$SAFE" | sed 's/\.[^.]*$//')"
  "$WHISPER" -m "$MODEL" -l zh -f "$WAV" -otxt -osrt -of "$OUTBASE" -t 8 --prompt "以下是普通话的句子。" || { rm -f "$WAV"; echo "转写失败"; continue; }

  # 说话人分离(本地声纹): 成功则生成 .spk.txt 带说话人标签的转写; 失败则无标签继续
  if [ -x "$ROOT/venv/bin/python3" ] && [ -f "$ROOT/models/sherpa-onnx-pyannote-segmentation-3.0/model.int8.onnx" ]; then
    "$ROOT/venv/bin/python3" "$ROOT/bin/diarize.py" "$WAV" "$OUTBASE.srt" "" 3 0.70 "$STASH" 2>&1 | tail -3 || echo "分离失败(继续无标签分析)"
  else
    echo "未配置声纹分离环境(venv/模型), 无标签分析"
  fi
  rm -f "$WAV"

  python3 "$ROOT/bin/analyze.py" "$OUTBASE.txt" "$OUTBASE.srt" "$DUR" "$STASH" || echo "分析步骤异常(转写结果不受影响)"

  echo "$KEY" >> "$STATE"
  NEW=$((NEW+1))
done < "$TMP_LIST"

echo "=== 完成: 本次新处理 $NEW 个录音 ==="

# 声音认人: 对新的陌生说话人生成可试听的认人笔记
python3 "$ROOT/bin/voice_id.py" || echo "声音认人生成异常(不影响其余)"

# 发布今日报告到备忘录(三类: 传不习乎/与朋友交/吾日三省)
python3 "$ROOT/bin/publish_note.py" || echo "备忘录发布失败(不影响其余结果)"
