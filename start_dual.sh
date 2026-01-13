#!/bin/bash
# 双端口启动脚本：HTTPS(8000) + HTTP(8080)

cd "$(dirname "$0")"
source venv/bin/activate

echo "======================================"
echo "  发票识别系统 - 双端口启动"
echo "======================================"
echo ""
echo "🔒 HTTPS 端口 (8000) - 支持摄像头扫码"
echo "📱 HTTP 端口 (8080) - 使用相册上传"
echo ""
echo "访问地址："
echo "  PC端:  https://$(hostname -I | awk '{print $1}'):8000"
echo "  手机:  http://$(hostname -I | awk '{print $1}'):8080/mobile"
echo ""
echo "======================================"

# 启动 HTTPS 服务 (端口 8000)
python -m backend.main &
HTTPS_PID=$!

# 启动 HTTP 服务 (端口 8080)
python -c "
import uvicorn
import os
os.chdir('$(pwd)')
from backend.main import app
uvicorn.run(app, host='0.0.0.0', port=8080)
" &
HTTP_PID=$!

echo ""
echo "✅ 服务已启动"
echo "   HTTPS PID: $HTTPS_PID"
echo "   HTTP PID:  $HTTP_PID"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

# 等待信号
trap "kill $HTTPS_PID $HTTP_PID 2>/dev/null; exit" SIGINT SIGTERM

wait
