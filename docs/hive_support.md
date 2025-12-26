# SCQL Hive 支持实现文档

本文档描述了 SCQL 项目中 Hive 数据源支持的实现细节，包括代码修改、配置方法和使用示例。

## 1. 概述

SCQL (Secure Collaborative Query Language) 现已支持 Hive 作为数据源。该实现通过 Arrow Flight SQL 协议与 Hive 进行通信，提供高性能的列式数据传输能力。

### 1.1 架构图

```
┌─────────────────┐      ┌─────────────────┐
│   SCDB Server   │      │   SCDB Server   │
│  (Query Router) │      │  (Query Router) │
└────────┬────────┘      └────────┬────────┘
         │                        │
         ▼                        ▼
┌─────────────────┐      ┌─────────────────┐
│  Alice Engine   │◄────►│   Bob Engine    │
│   (Port 8003)   │ PSI  │   (Port 8004)   │
└────────┬────────┘      └────────┬────────┘
         │ Arrow Flight           │ Arrow Flight
         │ SQL Protocol           │ SQL Protocol
         ▼                        ▼
┌─────────────────┐      ┌─────────────────┐
│  Hive/Arrow     │      │  Hive/Arrow     │
│  Flight Server  │      │  Flight Server  │
│  (Alice Data)   │      │   (Bob Data)    │
└─────────────────┘      └─────────────────┘
```

## 2. 代码修改

### 2.1 Go 代码修改

#### 2.1.1 数据库类型定义
**文件**: `pkg/planner/core/database_dialect.go`

新增 Hive 数据库类型和方言支持：

```go
// 添加 DBType 常量
const (
    DBTypeUnknown DBType = iota
    DBTypeMySQL
    DBTypeSQLite
    DBTypePostgres
    DBTypeCSVDB
    DBTypeODPS
    DBTypeHive  // 新增
)

// 添加到 dbTypeMap
var dbTypeMap = map[string]DBType{
    // ... 其他类型
    "hive": DBTypeHive,
}

// 添加到 dbTypeNameMap
var dbTypeNameMap = map[DBType]string{
    // ... 其他类型
    DBTypeHive: "hive",
}

// 添加到 DBDialectMap
var DBDialectMap = map[DBType]Dialect{
    // ... 其他类型
    DBTypeHive: NewHiveDialect(),
}

// HiveDialect 实现
type HiveDialect struct {
    MySQLDialect
}

func NewHiveDialect() *HiveDialect {
    return &HiveDialect{
        MySQLDialect{
            flags:         format.RestoreStringSingleQuotes | format.RestoreKeyWordLowercase,
            formatDialect: format.NewHiveDialect(),
        },
    }
}

func (d *HiveDialect) SupportAnyValue() bool {
    return false  // Hive 不支持 ANY_VALUE 函数
}
```

#### 2.1.2 SQL 格式化方言
**文件**: `pkg/parser/format/format_dialect.go`

新增 Hive SQL 方言处理：

```go
// HiveDialect Hive SQL 方言
type HiveDialect struct {
    MySQLDialect
    funcNameMap map[string]string
}

func NewHiveDialect() Dialect {
    return &HiveDialect{
        funcNameMap: map[string]string{
            "ifnull":   "nvl",       // Hive 使用 nvl 而非 ifnull
            "truncate": "trunc",     // Hive 使用 trunc
            "now":      "current_timestamp",
            "curdate":  "current_date",
        },
    }
}

func (d *HiveDialect) SkipSchemaInColName() bool {
    return true
}

func (d *HiveDialect) GetSpecialFuncName(originName string) string {
    if res, ok := d.funcNameMap[originName]; ok {
        return res
    }
    return originName
}

func (d *HiveDialect) ConvertCastTypeToString(asType byte, flen int, decimal int, flag uint) (keyword string, plainWord string, err error) {
    switch asType {
    case mysql.TypeVarString, mysql.TypeVarchar:
        keyword = "STRING"
    case mysql.TypeNewDecimal:
        keyword = "DECIMAL"
        if flen > 0 && decimal > 0 {
            plainWord = fmt.Sprintf("(%d, %d)", flen, decimal)
        }
    case mysql.TypeLonglong:
        keyword = "BIGINT"
    case mysql.TypeDouble, mysql.TypeFloat:
        keyword = "DOUBLE"
    case mysql.TypeDate:
        keyword = "DATE"
    case mysql.TypeDatetime:
        keyword = "TIMESTAMP"
    default:
        return d.MySQLDialect.ConvertCastTypeToString(asType, flen, decimal, flag)
    }
    return
}

func (d *HiveDialect) NeedParenthesesForCmpOperand() bool {
    return true
}
```

### 2.2 C++ 引擎修改

#### 2.2.1 数据源类型定义
**文件**: `engine/datasource/datasource.proto`

新增 HIVE 数据源类型：

```protobuf
enum DataSourceKind {
  UNKNOWN = 0;
  MYSQL = 1;
  SQLITE = 2;
  POSTGRESQL = 3;
  CSVDB = 4;
  ARROWSQL = 5;
  GRPC = 6;
  DATAPROXY = 7;
  HIVE = 8;  // 新增
}
```

#### 2.2.2 数据源适配器注册
**文件**: `engine/datasource/datasource_adaptor_mgr.cc`

将 Hive 注册到 Arrow Flight SQL 适配器：

```cpp
void DatasourceAdaptorMgr::RegisterBuiltinAdaptorFactories() {
  // ... 其他适配器

  auto arrow_sql_adaptor_factory = std::make_shared<ArrowSqlAdaptorFactory>();
  factory_maps_.insert({DataSourceKind::ARROWSQL, arrow_sql_adaptor_factory});

  // Hive 使用 Arrow Flight SQL 协议
  factory_maps_.insert({DataSourceKind::HIVE, arrow_sql_adaptor_factory});
}
```

## 3. 配置说明

### 3.1 引擎配置

**文件示例**: `examples/scdb-tutorial/engine/alice/conf/gflags_hive.conf`

```ini
--listen_port=8003
--datasource_router=embed
--enable_driver_authorization=false
--server_enable_ssl=false
--driver_enable_ssl_as_client=false
--peer_engine_enable_ssl_as_client=false

# Hive 配置 - 使用 Arrow Flight SQL 协议
--embed_router_conf={"datasources":[{"id":"ds001","name":"hive db","kind":"HIVE","connection_str":"grpc://localhost:8815"}],"rules":[{"db":"*","table":"*","datasource_id":"ds001"}]}

# Arrow Flight SQL TLS 配置 (可选)
--arrow_client_disable_server_verification=true

# Party 认证 (测试时可禁用)
--enable_self_auth=false
--enable_peer_auth=false
```

### 3.2 连接字符串格式

Arrow Flight SQL 连接字符串支持以下格式：

```
# 无认证
grpc://host:port

# 基本认证
grpc://host:port@username:password

# TLS
grpc+tls://host:port
```

### 3.3 SCDB 配置

**文件**: `examples/scdb-tutorial/scdb/conf/config_hive.yml`

```yaml
scdb_host: localhost:8080
port: 8080
protocol: http
storage:
  type: sqlite
  conn_str: "/path/to/scdb.db"
engine:
  timeout: 120s
  protocol: http
party_auth:
  method: none  # 测试时禁用认证
```

## 4. 使用方法

### 4.1 创建用户和数据库

```sql
-- 以 root 用户执行
CREATE USER alice PARTY_CODE "alice" IDENTIFIED BY 'password';
CREATE USER bob PARTY_CODE "bob" IDENTIFIED BY 'password';
CREATE DATABASE IF NOT EXISTS mydb;

-- 授权
GRANT ALL ON mydb.* TO alice;
GRANT ALL ON mydb.* TO bob;
```

### 4.2 创建表

```sql
-- Alice 创建表 (以 alice 用户执行)
CREATE TABLE mydb.user_credit (
    ID STRING,
    credit_rank INT,
    income INT,
    age INT
) REF_TABLE=default.user_credit DB_TYPE='hive';

-- Bob 创建表 (以 bob 用户执行)
CREATE TABLE mydb.user_stats (
    ID STRING,
    order_amount INT,
    is_active INT
) REF_TABLE=default.user_stats DB_TYPE='hive';
```

**注意**: `REF_TABLE` 需要使用 `schema.table` 格式（如 `default.user_credit`）。

### 4.3 设置引擎端点

```sql
-- 各用户设置自己的引擎端点
ALTER USER alice WITH ENDPOINT 'localhost:8003';
ALTER USER bob WITH ENDPOINT 'localhost:8004';
```

### 4.4 设置列控制策略 (CCL)

```sql
-- Alice 授权
GRANT SELECT PLAINTEXT(ID, credit_rank, income, age) ON mydb.user_credit TO alice;
GRANT SELECT PLAINTEXT(ID, credit_rank, income, age) ON mydb.user_credit TO bob;

-- Bob 授权
GRANT SELECT PLAINTEXT(ID, order_amount, is_active) ON mydb.user_stats TO bob;
GRANT SELECT PLAINTEXT(ID, order_amount, is_active) ON mydb.user_stats TO alice;
```

### 4.5 执行联合查询

```sql
SELECT
    a.ID,
    a.credit_rank,
    a.income,
    b.order_amount,
    b.is_active
FROM mydb.user_credit a
JOIN mydb.user_stats b ON a.ID = b.ID
WHERE a.age >= 20 AND b.is_active = 1;
```

## 5. 测试环境

### 5.1 Arrow Flight SQL 测试服务器

项目包含一个基于 DuckDB 的 Arrow Flight SQL 测试服务器：

**文件**: `examples/scdb-tutorial/hive/arrow_flight_server.py`

启动命令：
```bash
# Alice 服务器
python3 arrow_flight_server.py --party alice --port 8815

# Bob 服务器
python3 arrow_flight_server.py --party bob --port 8816
```

### 5.2 完整测试流程

```bash
# 1. 启动 Arrow Flight SQL 测试服务器
cd examples/scdb-tutorial/hive
python3 arrow_flight_server.py --party alice --port 8815 &
python3 arrow_flight_server.py --party bob --port 8816 &

# 2. 启动 SCQL 服务
bash examples/scdb-tutorial/start_all_hive.sh

# 3. 运行测试脚本
scdbclient source --host http://localhost:8080 \
    --usersConfFileName users_hive.json \
    --userName alice --sync \
    --sourceFile federated_query.sql
```

## 6. SQL 方言转换示例

| MySQL/标准 SQL | Hive SQL |
|----------------|----------|
| `IFNULL(a, b)` | `nvl(a, b)` |
| `TRUNCATE(n, d)` | `trunc(n, d)` |
| `NOW()` | `current_timestamp` |
| `CURDATE()` | `current_date` |
| `CAST(x AS VARCHAR(100))` | `CAST(x AS STRING)` |
| `CAST(x AS DATETIME)` | `CAST(x AS TIMESTAMP)` |

## 7. 注意事项

1. **Arrow Flight SQL 服务器要求**: Hive 需要配置 Arrow Flight SQL 服务端点，可以使用：
   - Apache Hive 4.0+ (原生支持)
   - Spark Thrift Server with Arrow
   - 其他兼容的 Arrow Flight SQL 服务器

2. **表引用格式**: `REF_TABLE` 必须使用 `schema.table` 格式

3. **ANY_VALUE 函数**: Hive 不支持 `ANY_VALUE`，SCQL 会自动处理

4. **代理设置**: 确保引擎运行环境无代理干扰 Arrow Flight 连接

## 8. 编译说明

修改代码后需要重新编译：

```bash
# 编译 Go 组件
go build -o bin/scdbserver ./cmd/scdbserver

# 编译 C++ 引擎
bazel build //engine/exe:scqlengine
cp bazel-bin/engine/exe/scqlengine bin/
```

## 9. 相关文件列表

### Go 代码
- `pkg/planner/core/database_dialect.go` - 数据库方言定义
- `pkg/parser/format/format_dialect.go` - SQL 格式化方言

### C++ 代码
- `engine/datasource/datasource.proto` - 数据源类型定义
- `engine/datasource/datasource_adaptor_mgr.cc` - 适配器注册
- `engine/datasource/arrow_sql_adaptor.cc` - Arrow Flight SQL 适配器实现

### 配置文件
- `examples/scdb-tutorial/engine/*/conf/gflags_hive.conf` - 引擎配置
- `examples/scdb-tutorial/scdb/conf/config_hive.yml` - SCDB 配置

### 测试文件
- `examples/scdb-tutorial/hive/arrow_flight_server.py` - 测试服务器
- `examples/scdb-tutorial/hive/*.sql` - 测试 SQL 脚本

