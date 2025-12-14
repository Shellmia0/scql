#!/usr/bin/env python3
"""
自动生成 SCQL 本地运行配置文件
"""
import os
import shutil

# 项目根目录
PROJECT_ROOT = "/root/autodl-tmp/scql"
TUTORIAL_DIR = os.path.join(PROJECT_ROOT, "examples/scdb-tutorial")

# MySQL 密码（从 setup.sh 生成的配置中提取）
MYSQL_PASSWORD = "3rvUyH8QJaljB"

def generate_scdb_config():
    """生成 SCDB Server 配置"""
    config = f"""scdb_host: localhost:8080
port: 8080
protocol: http
query_result_callback_timeout: 3m
session_expire_time: 3m
session_expire_check_time: 1m
log_level: debug
storage:
  type: mysql
  conn_str: "root:{MYSQL_PASSWORD}@tcp(localhost:3306)/scdb?charset=utf8mb4&parseTime=True&loc=Local&interpolateParams=true"
  max_idle_conns: 10
  max_open_conns: 100
  conn_max_idle_time: 2m
  conn_max_lifetime: 5m
engine:
  timeout: 120s
  protocol: http
  content_type: application/json
  spu: |
    {{
        "protocol": "SEMI2K",
        "field": "FM64"
    }}
party_auth:
  method: pubkey
  enable_timestamp_check: true
  validity_period: 1m
"""

    config_path = os.path.join(TUTORIAL_DIR, "scdb/conf/config_local.yml")
    with open(config_path, 'w') as f:
        f.write(config)
    print(f"✓ Generated SCDB config: {config_path}")
    return config_path

def generate_engine_config(party_name, port):
    """生成 Engine 配置"""
    config = f"""--listen_port={port}
--datasource_router=embed
--enable_driver_authorization=false
--server_enable_ssl=false
--driver_enable_ssl_as_client=false
--peer_engine_enable_ssl_as_client=false
--embed_router_conf={{"datasources":[{{"id":"ds001","name":"mysql db","kind":"MYSQL","connection_str":"db={party_name};user=root;password={MYSQL_PASSWORD};host=localhost;auto-reconnect=true"}}],"rules":[{{"db":"*","table":"*","datasource_id":"ds001"}}]}}
# party authentication flags
--enable_self_auth=true
--enable_peer_auth=true
--private_key_pem_path={TUTORIAL_DIR}/engine/{party_name}/conf/ed25519key.pem
--authorized_profile_path={TUTORIAL_DIR}/engine/{party_name}/conf/authorized_profile.json
"""

    config_path = os.path.join(TUTORIAL_DIR, f"engine/{party_name}/conf/gflags_local.conf")
    with open(config_path, 'w') as f:
        f.write(config)
    print(f"✓ Generated {party_name.upper()} Engine config: {config_path}")
    return config_path

def generate_start_script():
    """生成启动脚本"""
    script = f"""#!/bin/bash
# SCQL 本地启动脚本

PROJECT_ROOT="{PROJECT_ROOT}"
TUTORIAL_DIR="{TUTORIAL_DIR}"
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
nohup "$BIN_DIR/scqlengine" \\
    --flagfile="$TUTORIAL_DIR/engine/alice/conf/gflags_local.conf" \\
    > "$TUTORIAL_DIR/logs/alice_engine.log" 2>&1 &
ALICE_PID=$!
echo "Alice Engine PID: $ALICE_PID"

# 启动 Bob Engine
echo "启动 Bob Engine (端口 8004)..."
nohup "$BIN_DIR/scqlengine" \\
    --flagfile="$TUTORIAL_DIR/engine/bob/conf/gflags_local.conf" \\
    > "$TUTORIAL_DIR/logs/bob_engine.log" 2>&1 &
BOB_PID=$!
echo "Bob Engine PID: $BOB_PID"

# 等待 Engines 启动
sleep 2

# 启动 SCDB Server
echo "启动 SCDB Server (端口 8080)..."
nohup "$BIN_DIR/scdbserver" \\
    -config="$TUTORIAL_DIR/scdb/conf/config_local.yml" \\
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
"""

    script_path = os.path.join(TUTORIAL_DIR, "start_all.sh")
    with open(script_path, 'w') as f:
        f.write(script)
    os.chmod(script_path, 0o755)
    print(f"✓ Generated start script: {script_path}")
    return script_path

def generate_stop_script():
    """生成停止脚本"""
    script = f"""#!/bin/bash
# SCQL 停止脚本

echo "停止 SCQL 服务..."

# 查找并停止进程
pkill -f "scqlengine.*alice" && echo "✓ Stopped Alice Engine"
pkill -f "scqlengine.*bob" && echo "✓ Stopped Bob Engine"
pkill -f "scdbserver" && echo "✓ Stopped SCDB Server"

echo "所有服务已停止"
"""

    script_path = os.path.join(TUTORIAL_DIR, "stop_all.sh")
    with open(script_path, 'w') as f:
        f.write(script)
    os.chmod(script_path, 0o755)
    print(f"✓ Generated stop script: {script_path}")
    return script_path

def main():
    print("========================================")
    print("SCQL 本地环境配置生成器")
    print("========================================\n")

    # 生成配置文件
    generate_scdb_config()
    generate_engine_config("alice", 8003)
    generate_engine_config("bob", 8004)

    # 生成启动/停止脚本
    generate_start_script()
    generate_stop_script()

    print("\n========================================")
    print("配置生成完成！")
    print("========================================")
    print("\n下一步:")
    print(f"1. 启动服务: bash {TUTORIAL_DIR}/start_all.sh")
    print(f"2. 停止服务: bash {TUTORIAL_DIR}/stop_all.sh")
    print(f"3. 使用客户端: {PROJECT_ROOT}/bin/scdbclient --help")

if __name__ == "__main__":
    main()

