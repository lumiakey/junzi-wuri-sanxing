#!/bin/bash
# 三省流水线一键安装: 目录/依赖检查/签名解释器/定时任务
set -e
ROOT="$HOME/sanxing"
echo "═══ 三省流水线安装 ═══"

# 1. 目录结构
mkdir -p "$ROOT"/{bin,models,logs} "$ROOT"/data/{inbox,transcripts,reports,commitments,state,analysis,archive/audio}
cp -n "$(dirname "$0")"/bin/* "$ROOT/bin/" 2>/dev/null || true
echo "✓ 脚本就位 $ROOT/bin"

# 2. 依赖检查
MISSING=0
command -v whisper-cli >/dev/null || { echo "✗ 缺少 whisper-cli: brew install whisper-cpp"; MISSING=1; }
command -v ffmpeg >/dev/null || { echo "✗ 缺少 ffmpeg: brew install ffmpeg"; MISSING=1; }
[ -f "$ROOT/models/ggml-large-v3-turbo.bin" ] || echo "△ 模型未下载(可选,稍后再下):
    curl -L -o $ROOT/models/ggml-large-v3-turbo.bin https://hf-mirror.com/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin"
[ $MISSING -eq 1 ] && { echo "请先安装上述依赖后重跑本脚本"; exit 1; }
echo "✓ 依赖检查通过"

# 2.5 声纹分离环境(可选但推荐): venv + sherpa-onnx + 模型
echo "── 配置说话人分离环境(约70MB模型) ──"
python3 -m venv "$ROOT/venv" 2>/dev/null
"$ROOT/venv/bin/pip" install -q sherpa-onnx numpy 2>&1 | grep -v WARNING || true
mkdir -p "$ROOT/models/sherpa-onnx-pyannote-segmentation-3.0"
SEG="$ROOT/models/sherpa-onnx-pyannote-segmentation-3.0/model.int8.onnx"
EMB="$ROOT/models/3dspeaker_speech_eres2netv2_sv_zh-cn_16k-common.onnx"
[ -f "$SEG" ] || curl -sL --fail --retry 3 -o "$SEG" \
  "https://hf-mirror.com/csukuangfj/sherpa-onnx-pyannote-segmentation-3-0/resolve/main/model.int8.onnx" \
  || echo "△ 分割模型下载失败(可稍后手动下载到 $SEG)"
[ -f "$EMB" ] || curl -sL --fail --retry 3 -o "$EMB" \
  "https://mirror.ghproxy.com/https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2netv2_sv_zh-cn_16k-common.onnx" \
  || curl -sL --fail --retry 3 -o "$EMB" \
  "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2netv2_sv_zh-cn_16k-common.onnx" \
  || echo "△ 声纹模型下载失败(可稍后手动下载到 $EMB)"
"$ROOT/venv/bin/python3" -c "import sherpa_onnx" 2>/dev/null && echo "✓ 声纹分离环境就绪" || echo "△ 声纹分离暂不可用(流水线将无标签分析,不影响其余功能)"

# 3. 专用解释器(承接完全磁盘访问权限; macOS 26 需重签名否则 launchd 拒启)
cp /bin/bash "$ROOT/bin/sanxing-bash"
chmod +x "$ROOT/bin/sanxing-bash"
codesign --force --sign - "$ROOT/bin/sanxing-bash" >/dev/null 2>&1
echo "✓ 专用解释器已签名"

# 4. 配置文件
if [ ! -f "$ROOT/config.env" ]; then
  printf '# 三省流水线配置\n# API Key 建议写在备忘录笔记里(一行 GLM_API_KEY=xxx), 此处可留空\nGLM_API_KEY=\n# 模型与端点可换成任意兼容服务\nGLM_MODEL=glm-4-flash\n# GLM_BASE=https://open.bigmodel.cn/api/paas/v4/chat/completions\n' > "$ROOT/config.env"
fi
echo "✓ 配置文件 $ROOT/config.env"

# 5. 定时任务(每晚 23:30)
SRC="$(cd "$(dirname "$0")" && pwd)"
for T in com.sanxing.nightly; do
  sed "s|__HOME__|$HOME|g" "$SRC/LaunchAgents/$T.plist.template" > "$HOME/Library/LaunchAgents/$T.plist"
  launchctl bootout "gui/$(id -u)/$T" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/$T.plist"
done
cp "$SRC/立即处理.command" "$ROOT/" && chmod +x "$ROOT/立即处理.command"
echo "✓ 定时任务已加载(23:30) + 手动入口 立即处理.command"

echo ""
echo "═══ 接下来请手动完成(共3步) ═══"
echo "1. 完全磁盘访问: 系统设置→隐私与安全性→完全磁盘访问权限→添加"
echo "   按 Cmd+Shift+G 输入: $ROOT/bin/sanxing-bash"
echo "2. 备忘录任意笔记写一行(行内无其他内容): GLM_API_KEY=你的Key"
echo "3. 双击 $ROOT/立即处理.command —— 首次会弹 控制备忘录/提醒事项/日历/通讯录 授权, 全部允许"
echo ""
echo "自检: $ROOT/bin/sanxing-bash $ROOT/bin/selfcheck.sh"
