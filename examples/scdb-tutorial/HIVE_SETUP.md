# SCQL Hive 后端快速入门指南

本指南介绍如何配置和测试 SCQL 的 Hive 后端支持。

## 前置条件

- Python 3.8+
- Go 1.19+
- 已编译的 SCQL 二进制文件 (`scqlengine`, `scdbserver`, `scdbclient`)

## 快速开始

### 1. 安装 Python 依赖

```bash
pip3 install duckdb pyarrow pandas
```

### 2. 启动 Arrow Flight SQL 测试服务器

```bash
cd examples/scdb-tutorial/hive

# 启动 Alice 的数据服务器 (端口 8815)
python3 arrow_flight_server.py --party alice --port 8815 &

# 启动 Bob 的数据服务器 (端口 8816)
python3 arrow_flight_server.py --party bob --port 8816 &
```

### 3. 启动 SCQL 服务

```bash
cd examples/scdb-tutorial
bash start_all_hive.sh
```

### 4. 配置用户和表

```bash
cd examples/scdb-tutorial/hive

# 创建用户
scdbclient source --host http://localhost:8080 \
    --usersConfFileName users_hive.json \
    --userName root --sync \
    --sourceFile setup_users.sql

# 授权
scdbclient source --host http://localhost:8080 \
    --usersConfFileName users_hive.json \
    --userName root --sync \
    --sourceFile grant_privileges.sql

# Alice 创建表
scdbclient source --host http://localhost:8080 \
    --usersConfFileName users_hive.json \
    --userName alice --sync \
    --sourceFile setup_alice.sql

# Bob 创建表
scdbclient source --host http://localhost:8080 \
    --usersConfFileName users_hive.json \
    --userName bob --sync \
    --sourceFile setup_bob.sql

# 设置引擎端点
scdbclient source --host http://localhost:8080 \
    --usersConfFileName users_hive.json \
    --userName alice --sync \
    --sourceFile setup_endpoints.sql

scdbclient source --host http://localhost:8080 \
    --usersConfFileName users_hive.json \
    --userName bob --sync \
    --sourceFile setup_endpoints_bob.sql

# 设置 CCL 权限
scdbclient source --host http://localhost:8080 \
    --usersConfFileName users_hive.json \
    --userName alice --sync \
    --sourceFile grant_ccl_alice.sql

scdbclient source --host http://localhost:8080 \
    --usersConfFileName users_hive.json \
    --userName bob --sync \
    --sourceFile grant_ccl_bob.sql
```

### 5. 运行联合查询

```bash
scdbclient source --host http://localhost:8080 \
    --usersConfFileName users_hive.json \
    --userName alice --sync \
    --sourceFile federated_query.sql
```

预期输出：
```
+--------+-------------+--------+--------------+-----------+
|   ID   | credit_rank | income | order_amount | is_active |
+--------+-------------+--------+--------------+-----------+
| id0011 |           5 |  12070 |         3500 |         1 |
| id0019 |           6 |  30070 |         3200 |         1 |
| id0006 |           5 |  30070 |         1500 |         1 |
| ...    |         ... |    ... |          ... |       ... |
+--------+-------------+--------+--------------+-----------+
```

## 连接真实 Hive 环境

要连接真实的 Hive 环境，需要：

1. **Hive 服务器要求**：Hive 需要支持 Arrow Flight SQL 协议。可选方案：
   - Apache Hive 4.0+ (原生支持 Arrow Flight SQL)
   - Apache Spark with Thrift Server + Arrow 集成
   - Dremio, Trino 等支持 Arrow Flight SQL 的查询引擎

2. **修改引擎配置**：

编辑 `engine/alice/conf/gflags_hive.conf` 和 `engine/bob/conf/gflags_hive.conf`：

```ini
--embed_router_conf={"datasources":[{"id":"ds001","name":"hive db","kind":"HIVE","connection_str":"grpc://your-hive-server:port"}],"rules":[{"db":"*","table":"*","datasource_id":"ds001"}]}
```

3. **如需认证**：

```ini
# 连接字符串格式: grpc://host:port@username:password
--embed_router_conf={"datasources":[{"id":"ds001","name":"hive db","kind":"HIVE","connection_str":"grpc://hive-server:8815@hive_user:hive_pass"}],...}
```

4. **如需 TLS**：

```ini
--arrow_client_disable_server_verification=false
--arrow_cert_pem_path=/path/to/ca.pem
# 如需双向 TLS
--arrow_client_key_pem_path=/path/to/client-key.pem
--arrow_client_cert_pem_path=/path/to/client-cert.pem
```

## 文件说明

```
examples/scdb-tutorial/hive/
├── arrow_flight_server.py    # Arrow Flight SQL 测试服务器
├── users_hive.json           # 用户配置
├── setup_users.sql           # 创建用户脚本
├── setup_alice.sql           # Alice 表创建脚本
├── setup_bob.sql             # Bob 表创建脚本
├── grant_privileges.sql      # 权限授予脚本
├── grant_ccl_alice.sql       # Alice CCL 配置
├── grant_ccl_bob.sql         # Bob CCL 配置
├── setup_endpoints.sql       # Alice 端点设置
├── setup_endpoints_bob.sql   # Bob 端点设置
└── federated_query.sql       # 联合查询测试
```

## 停止服务

```bash
# 停止 SCQL 服务
bash examples/scdb-tutorial/stop_all.sh

# 停止 Arrow Flight SQL 测试服务器
pkill -f arrow_flight_server.py
```

## 故障排除

### 1. 连接被拒绝

检查 Arrow Flight SQL 服务器是否正在运行：
```bash
ps aux | grep arrow_flight_server
```

### 2. 代理干扰

如果使用代理，Arrow Flight 连接可能失败。启动引擎时清除代理：
```bash
env http_proxy="" https_proxy="" all_proxy="" ./bin/scqlengine --flagfile=...
```

### 3. 表不存在错误

确保 `REF_TABLE` 使用正确的格式：`schema.table`（如 `default.user_credit`）

### 4. CCL 检查失败

确保双方都正确设置了 CCL 权限，包括允许自己和对方查看列。

## 参考文档

- [SCQL Hive 支持实现文档](../../docs/hive_support.md) - 详细的实现说明
- [SCQL 官方文档](https://www.secretflow.org.cn/docs/scql/) - 完整的 SCQL 使用指南
