#!/bin/bash
# SCQL 本地启动脚本 - 连接真实本地 Hive
#
# 使用方法:
#   1. 先启动 Hive: bash start_local_hive.sh
#   2. 初始化数据: bash init_hive_test_data.sh
#   3. 启动 SCQL: bash start_scql_with_real_hive.sh

set -e

PROJECT_ROOT="/root/autodl-tmp/scql"
TUTORIAL_DIR="$PROJECT_ROOT/examples/scdb-tutorial"
HIVE_DIR="$TUTORIAL_DIR/hive"
BIN_DIR="$PROJECT_ROOT/bin"
LOG_DIR="$TUTORIAL_DIR/logs"

# ========================================
# Hive 连接配置
# ========================================
HIVE_HOST="localhost"
HIVE_PORT=10000
HIVE_USER="$(whoami)"
HIVE_AUTH="NONE"
# Alice 和 Bob 使用不同的数据库
ALICE_HIVE_DATABASE="alice"
BOB_HIVE_DATABASE="bob"
# ========================================

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

echo "=========================================="
echo "  启动 SCQL (连接本地 Hive)"
echo "=========================================="
echo ""

# 检查 SCQL 二进制文件
if [ ! -f "$BIN_DIR/scqlengine" ] || [ ! -f "$BIN_DIR/scdbserver" ]; then
    log_error "找不到 SCQL 二进制文件"
    echo "请先运行: cd $PROJECT_ROOT && make binary"
    exit 1
fi

# 检查 HiveServer2 是否运行
log_info "检查 HiveServer2..."
if ! nc -z $HIVE_HOST $HIVE_PORT 2>/dev/null; then
    log_error "HiveServer2 未运行 ($HIVE_HOST:$HIVE_PORT)"
    echo "请先运行: bash $HIVE_DIR/start_local_hive.sh"
    exit 1
fi
log_success "HiveServer2 运行正常"

# 检查 Python 依赖
log_info "检查 Python 依赖..."
if ! python3 -c "import pyarrow.flight, pyhive" 2>/dev/null; then
    log_warning "缺少 Python 依赖，请安装:"
    echo "  pip install pyarrow duckdb pyhive thrift thrift-sasl"
    echo ""
fi

# 创建日志目录
mkdir -p "$LOG_DIR"

# 停止可能已运行的服务
log_info "清理旧服务..."
pkill -f "arrow_flight_server.py" 2>/dev/null || true
pkill -f "scqlengine" 2>/dev/null || true
pkill -f "scdbserver" 2>/dev/null || true
sleep 2

# 禁用代理
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY

# ==========================================
# 启动 Arrow Flight SQL 服务器（连接真实 Hive）
# ==========================================
echo ""
log_info "启动 Arrow Flight SQL 服务器（连接本地 Hive）..."

# Alice Arrow Flight (端口 8815) - 连接 alice 数据库
log_info "  启动 Alice Arrow Flight (端口 8815, 数据库: $ALICE_HIVE_DATABASE)..."
nohup python3 "$HIVE_DIR/arrow_flight_server.py" \
    --party alice \
    --port 8815 \
    --backend hive \
    --hive-host "$HIVE_HOST" \
    --hive-port "$HIVE_PORT" \
    --hive-user "$HIVE_USER" \
    --hive-database "$ALICE_HIVE_DATABASE" \
    --hive-auth "$HIVE_AUTH" \
    > "$LOG_DIR/alice_flight.log" 2>&1 &
ALICE_FLIGHT_PID=$!
echo "    PID: $ALICE_FLIGHT_PID"

# Bob Arrow Flight (端口 8816) - 连接 bob 数据库
log_info "  启动 Bob Arrow Flight (端口 8816, 数据库: $BOB_HIVE_DATABASE)..."
nohup python3 "$HIVE_DIR/arrow_flight_server.py" \
    --party bob \
    --port 8816 \
    --backend hive \
    --hive-host "$HIVE_HOST" \
    --hive-port "$HIVE_PORT" \
    --hive-user "$HIVE_USER" \
    --hive-database "$BOB_HIVE_DATABASE" \
    --hive-auth "$HIVE_AUTH" \
    > "$LOG_DIR/bob_flight.log" 2>&1 &
BOB_FLIGHT_PID=$!
echo "    PID: $BOB_FLIGHT_PID"

# 等待 Arrow Flight 服务器启动
sleep 5

# 验证 Arrow Flight 服务器
if ! nc -z localhost 8815 2>/dev/null; then
    log_error "Alice Arrow Flight 启动失败"
    echo "检查日志: cat $LOG_DIR/alice_flight.log"
    cat "$LOG_DIR/alice_flight.log"
    exit 1
fi

if ! nc -z localhost 8816 2>/dev/null; then
    log_error "Bob Arrow Flight 启动失败"
    echo "检查日志: cat $LOG_DIR/bob_flight.log"
    exit 1
fi

log_success "Arrow Flight 服务器启动成功"

# ==========================================
# 启动 SCQL Engine
# ==========================================
echo ""
log_info "启动 SCQL Engine..."

# Alice Engine
log_info "  启动 Alice Engine (端口 8003)..."
nohup "$BIN_DIR/scqlengine" \
    --flagfile="$TUTORIAL_DIR/engine/alice/conf/gflags_hive.conf" \
    > "$LOG_DIR/alice_engine.log" 2>&1 &
ALICE_ENGINE_PID=$!
echo "    PID: $ALICE_ENGINE_PID"

# Bob Engine
log_info "  启动 Bob Engine (端口 8004)..."
nohup "$BIN_DIR/scqlengine" \
    --flagfile="$TUTORIAL_DIR/engine/bob/conf/gflags_hive.conf" \
    > "$LOG_DIR/bob_engine.log" 2>&1 &
BOB_ENGINE_PID=$!
echo "    PID: $BOB_ENGINE_PID"

sleep 3

# ==========================================
# 启动 SCDB Server
# ==========================================
echo ""
log_info "启动 SCDB Server (端口 8080)..."

# 删除旧的 SQLite 数据库
rm -f "$TUTORIAL_DIR/scdb/scdb_hive.db"

export SCQL_ROOT_PASSWORD="root"
nohup "$BIN_DIR/scdbserver" \
    -config="$TUTORIAL_DIR/scdb/conf/config_hive.yml" \
    > "$LOG_DIR/scdb_server.log" 2>&1 &
SCDB_PID=$!
echo "    PID: $SCDB_PID"

sleep 3

# ==========================================
# 验证所有服务
# ==========================================
echo ""
log_info "验证服务状态..."

all_ok=true

if nc -z localhost 8815 2>/dev/null; then
    log_success "✓ Alice Arrow Flight (8815) -> Hive:$ALICE_HIVE_DATABASE"
else
    log_error "✗ Alice Arrow Flight (8815)"
    all_ok=false
fi

if nc -z localhost 8816 2>/dev/null; then
    log_success "✓ Bob Arrow Flight (8816) -> Hive:$BOB_HIVE_DATABASE"
else
    log_error "✗ Bob Arrow Flight (8816)"
    all_ok=false
fi

if nc -z localhost 8003 2>/dev/null; then
    log_success "✓ Alice Engine (8003)"
else
    log_error "✗ Alice Engine (8003)"
    all_ok=false
fi

if nc -z localhost 8004 2>/dev/null; then
    log_success "✓ Bob Engine (8004)"
else
    log_error "✗ Bob Engine (8004)"
    all_ok=false
fi

if nc -z localhost 8080 2>/dev/null; then
    log_success "✓ SCDB Server (8080)"
else
    log_error "✗ SCDB Server (8080)"
    all_ok=false
fi

echo ""
echo "=========================================="
if [ "$all_ok" = true ]; then
    echo -e "  ${GREEN}所有服务启动成功！${NC}"
else
    echo -e "  ${RED}部分服务启动失败${NC}"
fi
echo "=========================================="
echo ""
echo "Hive 数据库:"
echo "  Alice: $HIVE_HOST:$HIVE_PORT/$ALICE_HIVE_DATABASE (表: user_credit)"
echo "  Bob:   $HIVE_HOST:$HIVE_PORT/$BOB_HIVE_DATABASE (表: user_stats)"
echo ""
echo "SCQL 服务:"
echo "  Alice Arrow Flight: grpc://localhost:8815"
echo "  Bob Arrow Flight:   grpc://localhost:8816"
echo "  Alice Engine:       http://localhost:8003"
echo "  Bob Engine:         http://localhost:8004"
echo "  SCDB Server:        http://localhost:8080"
echo ""
echo "日志目录: $LOG_DIR"
echo ""
echo "运行测试:"
echo "  bash $PROJECT_ROOT/test_privacy_hive.sh"
echo ""
echo "停止服务:"
echo "  bash $TUTORIAL_DIR/stop_all_hive.sh"
