#!/bin/bash
# SCQL 本地启动脚本

PROJECT_ROOT="/root/autodl-tmp/scql"
TUTORIAL_DIR="/root/autodl-tmp/scql/examples/scdb-tutorial"
BIN_DIR="$PROJECT_ROOT/bin"

echo "========================================="
echo "启动 SCQL 服务"
echo "========================================="

# 检查二进制文件
if [ ! -f "$BIN_DIR/scqlengine" ] || [ ! -f "$BIN_DIR/scdbserver" ]; then
    echo "错误: 找不到编译好的二进制文件"
    echo "请先运行: make binary"
    exit 1
fi

# 创建日志目录
mkdir -p "$TUTORIAL_DIR/logs"

# 启动 Alice Engine
echo "启动 Alice Engine (端口 8003)..."
nohup "$BIN_DIR/scqlengine" \
    --flagfile="$TUTORIAL_DIR/engine/alice/conf/gflags_local.conf" \
    > "$TUTORIAL_DIR/logs/alice_engine.log" 2>&1 &
ALICE_PID=$!
echo "Alice Engine PID: $ALICE_PID"

# 启动 Bob Engine
echo "启动 Bob Engine (端口 8004)..."
nohup "$BIN_DIR/scqlengine" \
    --flagfile="$TUTORIAL_DIR/engine/bob/conf/gflags_local.conf" \
    > "$TUTORIAL_DIR/logs/bob_engine.log" 2>&1 &
BOB_PID=$!
echo "Bob Engine PID: $BOB_PID"

# 等待 Engines 启动
sleep 2

# 启动 SCDB Server
echo "启动 SCDB Server (端口 8080)..."
nohup "$BIN_DIR/scdbserver" \
    -config="$TUTORIAL_DIR/scdb/conf/config_local.yml" \
    > "$TUTORIAL_DIR/logs/scdb_server.log" 2>&1 &
SCDB_PID=$!
echo "SCDB Server PID: $SCDB_PID"

echo ""
echo "========================================="
echo "所有服务已启动！"
echo "========================================="
echo "Alice Engine:  http://localhost:8003 (PID: $ALICE_PID)"
echo "Bob Engine:    http://localhost:8004 (PID: $BOB_PID)"
echo "SCDB Server:   http://localhost:8080 (PID: $SCDB_PID)"
echo ""
echo "日志文件位置: $TUTORIAL_DIR/logs/"
echo ""
echo "停止服务: kill $ALICE_PID $BOB_PID $SCDB_PID"
echo "或运行: bash $TUTORIAL_DIR/stop_all.sh"
echo ""
echo "查看日志:"
echo "  tail -f $TUTORIAL_DIR/logs/alice_engine.log"
echo "  tail -f $TUTORIAL_DIR/logs/bob_engine.log"
echo "  tail -f $TUTORIAL_DIR/logs/scdb_server.log"
