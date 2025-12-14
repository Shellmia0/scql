#!/bin/bash
# SCQL 停止脚本

echo "停止 SCQL 服务..."

# 查找并停止进程
pkill -f "scqlengine.*alice" && echo "✓ Stopped Alice Engine"
pkill -f "scqlengine.*bob" && echo "✓ Stopped Bob Engine"
pkill -f "scdbserver" && echo "✓ Stopped SCDB Server"

echo "所有服务已停止"
