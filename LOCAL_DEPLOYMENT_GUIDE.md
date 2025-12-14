# SCQL 本地部署指南 (AutoDL 环境)

## 概述

本指南记录了在 AutoDL Docker 容器环境中，不使用 Docker Compose 的情况下手动部署 SCQL 系统的完整过程。

## 架构说明

```
                    metadata
         ┌─────────────────────────────┐
         │                             │
         │   ┌──────┐      ┌────┐     │
         │   │ SCDB │◄─────┤ DB │     │
         │   └───┬──┘      └────┘     │
         │       │                     │
         └───────┼─────────────────────┘
                 │
        ┌────────┴────────┐
        │                 │
   ┌────▼────┐       ┌────▼────┐
   │  Alice  │◄─────►│   Bob   │
   │         │  MPC  │         │
   │ Engine  │       │ Engine  │
   │    +    │       │    +    │
   │   DB    │       │   DB    │
   └─────────┘       └─────────┘
```

- **SCDB Server**: 协调服务，监听 `localhost:8080`
- **Alice Engine**: Alice 的计算引擎，监听 `localhost:8003`
- **Bob Engine**: Bob 的计算引擎，监听 `localhost:8004`
- **MySQL**: 共享数据库服务器，使用不同数据库名区分（`scdb`, `alice`, `bob`）

## 编译过程中遇到的问题及解决方案

### 1. 缺少 NASM 汇编编译器

**报错**:
```
CMake Error: No CMAKE_ASM_NASM_COMPILER could be found.
```

**原因**: Intel IPP Cryptography 库需要 NASM 进行汇编优化。

**解决**:
```bash
sudo apt-get install -y nasm
export ASM_NASM=$(which nasm)
```

### 2. CMake 误报不支持 C++14

**报错**:
```
CMake Error: Compiler does not support C++14.
-- Checking for C++14 compiler - unavailable
```

**原因**: `.bazelrc` 中强制静态链接标准库 (`-static-libstdc++`)，导致 CMake 特性检测时链接失败。

**解决**: 修改 `.bazelrc`，注释掉静态链接配置:
```bash
# build:linux --action_env=BAZEL_LINKOPTS=-static-libstdc++:-static-libgcc
# build:linux --action_env=BAZEL_LINKLIBS=-l%:libstdc++.a:-l%:libgcc.a
```

同时在 `engine/bazel/poco.BUILD` 中添加:
```cmake
"CMAKE_CXX_STANDARD": "17",
"CMAKE_CXX_STANDARD_REQUIRED": "ON",
```

### 3. Poco 库链接顺序错误

**报错**:
```
undefined reference to 'Poco::AbstractTimerCallback::AbstractTimerCallback()'
undefined reference to 'Poco::Event::~Event()'
...
```

**原因**: `libPocoFoundation.a` 被依赖，但在链接列表中排在前面。

**解决**: 调整 `engine/bazel/poco.BUILD` 中的 `out_static_libs` 顺序:
```python
out_static_libs = [
    "libPocoDataMySQL.a",
    "libPocoDataSQLite.a",
    "libPocoDataPostgreSQL.a",
    "libPocoData.a",
    "libPocoFoundation.a",  # 基础库放最后
],
```

## 部署步骤

### 1. 编译二进制文件

```bash
cd /root/autodl-tmp/scql
export ASM_NASM=$(which nasm)
make binary

# 复制 scqlengine 到 bin 目录
cp bazel-bin/engine/exe/scqlengine bin/
```

### 2. 生成密钥和配置

```bash
bash examples/scdb-tutorial/setup.sh
```

这会生成:
- Alice 和 Bob 的 Ed25519 私钥
- 授权配置文件 (authorized_profile.json)
- MySQL 密码 (随机生成)

### 3. 安装并配置 MySQL

```bash
# 安装 MySQL
sudo apt-get update && sudo apt-get install -y mysql-server

# 启动 MySQL (safe mode)
mkdir -p /var/run/mysqld && chown mysql:mysql /var/run/mysqld
mysqld_safe --skip-grant-tables &

# 设置密码 (从 config.yml 中提取的密码)
sleep 3
mysql -u root -e "FLUSH PRIVILEGES; \
  ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '3rvUyH8QJaljB'; \
  CREATE USER IF NOT EXISTS 'root'@'127.0.0.1' IDENTIFIED WITH mysql_native_password BY '3rvUyH8QJaljB'; \
  GRANT ALL PRIVILEGES ON *.* TO 'root'@'127.0.0.1' WITH GRANT OPTION; \
  FLUSH PRIVILEGES;"

# 重启 MySQL (正常模式)
pkill mysqld && sleep 2
mysqld_safe --bind-address=0.0.0.0 --port=3306 &
```

### 4. 初始化数据库

```bash
cd examples/scdb-tutorial/mysql/initdb
mysql -u root -p3rvUyH8QJaljB < scdb_init.sql
mysql -u root -p3rvUyH8QJaljB < alice_init.sql
mysql -u root -p3rvUyH8QJaljB < bob_init.sql
```

### 5. 生成本地配置文件

```bash
cd /root/autodl-tmp/scql
python3 setup_local_env.py
```

这会生成:
- `scdb/conf/config_local.yml` - SCDB Server 配置
- `engine/alice/conf/gflags_local.conf` - Alice Engine 配置
- `engine/bob/conf/gflags_local.conf` - Bob Engine 配置 (端口 8004)
- `start_all.sh` - 启动脚本
- `stop_all.sh` - 停止脚本

### 6. 启动服务

```bash
cd examples/scdb-tutorial
bash start_all.sh
```

### 7. 验证服务

```bash
# 检查进程
ps aux | grep -E "(scqlengine|scdbserver)" | grep -v grep

# 测试客户端连接
cd /root/autodl-tmp/scql
echo "SHOW DATABASES;" > test.sql
bin/scdbclient source --sourceFile=test.sql \
  --host=http://localhost:8080 \
  --userName=root \
  --passwd=root \
  --sync
```

## 服务管理

### 启动服务
```bash
bash examples/scdb-tutorial/start_all.sh
```

### 停止服务
```bash
bash examples/scdb-tutorial/stop_all.sh
```

### 查看日志
```bash
tail -f examples/scdb-tutorial/logs/alice_engine.log
tail -f examples/scdb-tutorial/logs/bob_engine.log
tail -f examples/scdb-tutorial/logs/scdb_server.log
```

## 关键配置说明

### MySQL 密码
从 `examples/scdb-tutorial/scdb/conf/config.yml` 中提取:
```yaml
conn_str: "root:3rvUyH8QJaljB@tcp(localhost:3306)/scdb?..."
```

### 端口分配
- SCDB Server: `8080`
- Alice Engine: `8003`
- Bob Engine: `8004` (避免与 Alice 冲突)
- MySQL: `3306`

### 密钥路径
使用绝对路径:
```
/root/autodl-tmp/scql/examples/scdb-tutorial/engine/alice/conf/ed25519key.pem
/root/autodl-tmp/scql/examples/scdb-tutorial/engine/bob/conf/ed25519key.pem
```

## 常见问题

### Q: SCDB Server 无法连接 MySQL
**A**: 确保 MySQL 启动时开启了网络监听 (`--bind-address=0.0.0.0`)，而不是 `--skip-networking`。

### Q: 客户端交互模式报错 "no such device or address"
**A**: 在非 TTY 环境（如 Docker 容器）中，使用 `source` 命令执行 SQL 文件，而不是 `prompt` 交互模式。

### Q: 编译时链接错误
**A**: 检查 Poco 库的链接顺序，确保 `libPocoFoundation.a` 在最后。

## 下一步

现在你可以:
1. 按照 [SCQL 教程](https://www.secretflow.org.cn/docs/scql/latest/zh-Hans/intro/tutorial) 继续操作
2. 创建数据库和表
3. 配置用户和权限
4. 执行联合查询

## 文件清单

### 修改的文件
- `.bazelrc` - 注释掉静态链接配置
- `engine/bazel/poco.BUILD` - 调整库链接顺序，添加 C++ 标准

### 生成的文件
- `setup_local_env.py` - 配置生成脚本
- `examples/scdb-tutorial/scdb/conf/config_local.yml`
- `examples/scdb-tutorial/engine/alice/conf/gflags_local.conf`
- `examples/scdb-tutorial/engine/bob/conf/gflags_local.conf`
- `examples/scdb-tutorial/start_all.sh`
- `examples/scdb-tutorial/stop_all.sh`
- `examples/scdb-tutorial/client/users_local.json`

## 总结

通过以上步骤，我们成功在 AutoDL 容器环境中部署了 SCQL 系统，解决了编译、配置和运行过程中的各种问题。关键点在于:
1. 正确配置编译依赖 (NASM)
2. 调整链接策略 (动态链接)
3. 修复库链接顺序
4. 适配本地环境配置 (路径、端口、数据库)

