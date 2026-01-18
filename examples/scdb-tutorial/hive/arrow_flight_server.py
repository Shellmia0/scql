#!/usr/bin/env python3
"""
Arrow Flight SQL 服务器
支持两种后端模式：
1. DuckDB 模式（默认）- 用于本地测试，使用内存数据库模拟 Hive
2. Hive 模式 - 连接真实的 HiveServer2

此服务器实现了 Arrow Flight SQL 协议的核心功能，包括:
- GetFlightInfo: 处理 SQL 查询请求 (解析 CommandStatementQuery protobuf)
- DoGet: 返回查询结果

使用方法:
    # DuckDB 模式（测试用）
    python3 arrow_flight_server.py --party alice --port 8815

    # Hive 模式（连接真实 Hive）
    python3 arrow_flight_server.py --port 8815 --backend hive \
        --hive-host hive.example.com --hive-port 10000 \
        --hive-user hive --hive-database default

依赖:
    pip install pyarrow duckdb
    # Hive 模式额外需要:
    pip install pyhive thrift thrift-sasl
"""

import argparse
import pyarrow as pa
import pyarrow.flight as flight


# =============================================================================
# 后端抽象层
# =============================================================================

class DatabaseBackend:
    """数据库后端抽象接口"""

    def execute(self, query: str) -> pa.Table:
        """执行 SQL 并返回 Arrow Table"""
        raise NotImplementedError

    def close(self):
        """关闭连接"""
        pass


class DuckDBBackend(DatabaseBackend):
    """DuckDB 后端 - 用于本地测试"""

    def __init__(self, party: str = None, init_data: bool = True):
        import duckdb
        self.conn = duckdb.connect(":memory:")
        self.party = party
        if init_data and party:
            self._init_test_data()

    def _init_test_data(self):
        """初始化测试数据"""
        self.conn.execute('CREATE SCHEMA IF NOT EXISTS "default"')

        if self.party == "alice":
            self.conn.execute('''
                CREATE TABLE "default".user_credit (
                    ID VARCHAR PRIMARY KEY,
                    credit_rank INTEGER,
                    income INTEGER,
                    age INTEGER
                )
            ''')
            self.conn.execute('''
                INSERT INTO "default".user_credit VALUES
                    ('id0001', 6, 100000, 20),
                    ('id0002', 5, 90000, 19),
                    ('id0003', 6, 89700, 32),
                    ('id0005', 6, 607000, 30),
                    ('id0006', 5, 30070, 25),
                    ('id0007', 6, 12070, 28),
                    ('id0008', 6, 200800, 50),
                    ('id0009', 6, 607000, 30),
                    ('id0010', 5, 30070, 25),
                    ('id0011', 5, 12070, 28),
                    ('id0012', 6, 200800, 50),
                    ('id0013', 5, 30070, 25),
                    ('id0014', 5, 12070, 28),
                    ('id0015', 6, 200800, 18),
                    ('id0016', 5, 30070, 26),
                    ('id0017', 5, 12070, 27),
                    ('id0018', 6, 200800, 16),
                    ('id0019', 6, 30070, 25),
                    ('id0020', 5, 12070, 28)
            ''')
            print(f"[DuckDB] 初始化 Alice user_credit 表 (19 行)")

        elif self.party == "bob":
            self.conn.execute('''
                CREATE TABLE "default".user_stats (
                    ID VARCHAR PRIMARY KEY,
                    order_amount INTEGER,
                    is_active INTEGER
                )
            ''')
            self.conn.execute('''
                INSERT INTO "default".user_stats VALUES
                    ('id0001', 5000, 1),
                    ('id0002', 3000, 1),
                    ('id0003', 8000, 0),
                    ('id0005', 12000, 1),
                    ('id0006', 1500, 1),
                    ('id0007', 2500, 0),
                    ('id0008', 9500, 1),
                    ('id0009', 7000, 1),
                    ('id0010', 500, 0),
                    ('id0011', 3500, 1),
                    ('id0012', 15000, 1),
                    ('id0013', 2000, 0),
                    ('id0014', 4500, 1),
                    ('id0015', 6500, 1),
                    ('id0016', 1000, 0),
                    ('id0017', 8500, 1),
                    ('id0018', 11000, 1),
                    ('id0019', 3200, 1),
                    ('id0020', 7500, 0)
            ''')
            print(f"[DuckDB] 初始化 Bob user_stats 表 (19 行)")

    def execute(self, query: str) -> pa.Table:
        return self.conn.execute(query).fetch_arrow_table()

    def close(self):
        self.conn.close()


class HiveBackend(DatabaseBackend):
    """Hive 后端 - 连接真实 HiveServer2"""

    def __init__(self, host: str, port: int = 10000, username: str = None,
                 password: str = None, database: str = "default",
                 auth: str = "NONE"):
        """
        初始化 Hive 连接

        Args:
            host: HiveServer2 主机地址
            port: HiveServer2 端口（默认 10000）
            username: 用户名
            password: 密码（用于 LDAP 认证）
            database: 默认数据库
            auth: 认证方式 (NONE, LDAP, KERBEROS)
        """
        try:
            from pyhive import hive
        except ImportError:
            raise ImportError(
                "Hive 后端需要安装 pyhive: pip install pyhive thrift thrift-sasl"
            )

        self.host = host
        self.port = port
        self.database = database

        # 连接参数
        conn_kwargs = {
            "host": host,
            "port": port,
            "database": database,
        }

        if username:
            conn_kwargs["username"] = username
        if auth and auth != "NONE":
            conn_kwargs["auth"] = auth
        if password and auth == "LDAP":
            conn_kwargs["password"] = password

        print(f"[Hive] 连接到 {host}:{port}/{database} (auth={auth})")
        self.conn = hive.connect(**conn_kwargs)
        self.cursor = self.conn.cursor()
        print(f"[Hive] 连接成功")

    def execute(self, query: str) -> pa.Table:
        """执行 Hive SQL 并返回 Arrow Table"""
        print(f"[Hive] 执行: {query[:100]}...")

        self.cursor.execute(query)

        # 获取列信息
        columns = [desc[0] for desc in self.cursor.description]
        col_types = [desc[1] for desc in self.cursor.description]

        # 获取所有数据
        rows = self.cursor.fetchall()

        # 转换为 Arrow Table
        if not rows:
            # 空结果，创建空 schema
            fields = [pa.field(name, self._hive_type_to_arrow(t))
                      for name, t in zip(columns, col_types)]
            schema = pa.schema(fields)
            return pa.table({name: [] for name in columns}, schema=schema)

        # 按列组织数据
        col_data = {name: [] for name in columns}
        for row in rows:
            for i, value in enumerate(row):
                col_data[columns[i]].append(value)

        # 创建 Arrow Table
        arrays = {}
        for name, data in col_data.items():
            arrays[name] = pa.array(data)

        return pa.table(arrays)

    def _hive_type_to_arrow(self, hive_type: str) -> pa.DataType:
        """将 Hive 类型映射到 Arrow 类型"""
        hive_type = hive_type.upper()
        type_map = {
            "STRING": pa.string(),
            "VARCHAR": pa.string(),
            "CHAR": pa.string(),
            "INT": pa.int32(),
            "INTEGER": pa.int32(),
            "BIGINT": pa.int64(),
            "SMALLINT": pa.int16(),
            "TINYINT": pa.int8(),
            "FLOAT": pa.float32(),
            "DOUBLE": pa.float64(),
            "DECIMAL": pa.float64(),
            "BOOLEAN": pa.bool_(),
            "BINARY": pa.binary(),
            "TIMESTAMP": pa.timestamp("us"),
            "DATE": pa.date32(),
        }
        return type_map.get(hive_type, pa.string())

    def close(self):
        self.cursor.close()
        self.conn.close()
        print("[Hive] 连接已关闭")


def create_backend(args) -> DatabaseBackend:
    """根据参数创建数据库后端"""
    if args.backend == "hive":
        if not args.hive_host:
            raise ValueError("Hive 模式需要指定 --hive-host")
        return HiveBackend(
            host=args.hive_host,
            port=args.hive_port,
            username=args.hive_user,
            password=args.hive_password,
            database=args.hive_database,
            auth=args.hive_auth,
        )
    else:
        return DuckDBBackend(party=args.party, init_data=True)


# =============================================================================
# Protobuf 解析工具
# =============================================================================

def _read_varint(data: bytes, start: int) -> tuple:
    """读取 protobuf varint，返回 (value, bytes_consumed)"""
    result = 0
    shift = 0
    idx = start
    while idx < len(data):
        byte = data[idx]
        result |= (byte & 0x7f) << shift
        idx += 1
        if (byte & 0x80) == 0:
            break
        shift += 7
    return result, idx - start


def parse_flight_sql_command(data: bytes) -> str:
    """
    解析 Arrow Flight SQL 的 CommandStatementQuery protobuf 消息

    CommandStatementQuery 的 protobuf 定义:
    message CommandStatementQuery {
      string query = 1;
      string transaction_id = 2;
    }
    """
    if not data:
        return ""

    try:
        # 检查是否是 google.protobuf.Any 包装
        if b"type.googleapis.com" in data:
            idx = 0
            while idx < len(data):
                if data[idx] == 0x12:  # field 2, wire type 2
                    idx += 1
                    length, varint_size = _read_varint(data, idx)
                    idx += varint_size
                    inner_data = data[idx:idx+length]
                    return parse_flight_sql_command(inner_data)
                idx += 1

        # 直接解析 CommandStatementQuery
        idx = 0
        while idx < len(data):
            tag = data[idx]
            idx += 1

            if tag == 0x0a:  # field 1 (query)
                length, varint_size = _read_varint(data, idx)
                idx += varint_size
                return data[idx:idx+length].decode("utf-8")
            elif (tag & 0x07) == 2:
                length, varint_size = _read_varint(data, idx)
                idx += varint_size + length
            elif (tag & 0x07) == 0:
                _, varint_size = _read_varint(data, idx)
                idx += varint_size
            else:
                break

        return data.decode("utf-8", errors="replace")

    except Exception as e:
        print(f"[警告] 解析 protobuf 失败: {e}")
        return data.decode("utf-8", errors="replace")


# =============================================================================
# Arrow Flight SQL 服务器
# =============================================================================

class FlightSqlServer(flight.FlightServerBase):
    """
    Arrow Flight SQL 服务器实现
    支持 DuckDB（测试）和 Hive（生产）两种后端
    """

    def __init__(self, backend: DatabaseBackend, host="0.0.0.0", port=8815,
                 party="unknown"):
        location = f"grpc://0.0.0.0:{port}"
        super().__init__(location)
        self.backend = backend
        self.party = party
        self._port = port
        self._host = host
        self._queries = {}  # ticket_id -> query
        self._ticket_counter = 0
        print(f"[{party}] Arrow Flight SQL 服务器启动在端口 {port}")

    def _preprocess_query(self, query: str) -> str:
        """
        预处理 SQL 查询

        对于 DuckDB 后端：将 default.table 转换为 "default".table
        对于 Hive 后端：保持原样（Hive 使用 database.table 格式）
        """
        import re

        if isinstance(self.backend, DuckDBBackend):
            # DuckDB 需要引号包裹 schema 名
            query = re.sub(r'\bdefault\.(\w+)', r'"default".\1', query, flags=re.IGNORECASE)

        return query

    def _generate_ticket(self, query: str) -> bytes:
        """生成唯一的 ticket ID"""
        self._ticket_counter += 1
        ticket_id = f"{self.party}_{self._ticket_counter}"
        self._queries[ticket_id] = query
        return ticket_id.encode("utf-8")

    def get_flight_info(self, context, descriptor):
        """
        处理 GetFlightInfo 请求
        Arrow Flight SQL 客户端通过此方法发送 SQL 查询
        """
        if descriptor.descriptor_type == flight.DescriptorType.CMD:
            query = parse_flight_sql_command(descriptor.command)
        elif descriptor.descriptor_type == flight.DescriptorType.PATH:
            table_name = "/".join(
                p.decode() if isinstance(p, bytes) else p
                for p in descriptor.path
            )
            query = f"SELECT * FROM {table_name}"
        else:
            raise flight.FlightUnavailableError("Unsupported descriptor type")

        query = self._preprocess_query(query)
        print(f"[{self.party}] GetFlightInfo - Query: {query[:100]}...")

        try:
            result = self.backend.execute(query)
            schema = result.schema
            num_rows = result.num_rows

            ticket_bytes = self._generate_ticket(query)
            ticket = flight.Ticket(ticket_bytes)

            location = flight.Location.for_grpc_tcp("localhost", self._port)
            endpoint = flight.FlightEndpoint(ticket, [location])

            info = flight.FlightInfo(
                schema,
                descriptor,
                [endpoint],
                num_rows,
                -1
            )

            print(f"[{self.party}] FlightInfo - rows: {num_rows}, columns: {len(schema)}")
            return info

        except Exception as e:
            print(f"[{self.party}] 查询错误: {e}")
            raise flight.FlightServerError(f"Query execution failed: {e}")

    def do_get(self, context, ticket):
        """处理 DoGet 请求，返回查询结果"""
        ticket_data = ticket.ticket.decode("utf-8")

        if ticket_data in self._queries:
            query = self._queries.pop(ticket_data)
        else:
            query = ticket_data

        query = self._preprocess_query(query)
        print(f"[{self.party}] DoGet - Query: {query[:100]}...")

        try:
            result = self.backend.execute(query)
            print(f"[{self.party}] 返回 {result.num_rows} 行, {result.num_columns} 列")
            return flight.RecordBatchStream(result)
        except Exception as e:
            print(f"[{self.party}] 查询错误: {e}")
            raise flight.FlightServerError(f"Query execution failed: {e}")

    def do_action(self, context, action):
        """处理 Action 请求"""
        action_type = action.type
        print(f"[{self.party}] Action: {action_type}")

        if action_type == "healthcheck":
            yield flight.Result(b"ok")
        else:
            yield flight.Result(b"")

    def list_actions(self, context):
        """列出支持的 actions"""
        return [("healthcheck", "Health check")]

    def shutdown(self):
        """关闭服务器和后端连接"""
        self.backend.close()
        super().shutdown()


def main():
    parser = argparse.ArgumentParser(
        description="Arrow Flight SQL 服务器 - 支持 DuckDB（测试）和 Hive（生产）后端",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # DuckDB 模式（本地测试）
  python3 arrow_flight_server.py --party alice --port 8815

  # Hive 模式（连接真实 Hive）
  python3 arrow_flight_server.py --port 8815 --backend hive \\
      --hive-host hive.example.com --hive-port 10000 \\
      --hive-user hive --hive-database default
        """
    )

    # 基本参数
    parser.add_argument("--party", type=str, default="alice",
                        help="参与方名称 (用于日志标识)")
    parser.add_argument("--port", type=int, default=8815,
                        help="Arrow Flight 服务端口 (默认: 8815)")
    parser.add_argument("--host", type=str, default="0.0.0.0",
                        help="监听地址 (默认: 0.0.0.0)")

    # 后端选择
    parser.add_argument("--backend", type=str, default="duckdb",
                        choices=["duckdb", "hive"],
                        help="数据库后端 (默认: duckdb)")

    # Hive 连接参数
    hive_group = parser.add_argument_group("Hive 连接参数")
    hive_group.add_argument("--hive-host", type=str,
                            help="HiveServer2 主机地址")
    hive_group.add_argument("--hive-port", type=int, default=10000,
                            help="HiveServer2 端口 (默认: 10000)")
    hive_group.add_argument("--hive-user", type=str,
                            help="Hive 用户名")
    hive_group.add_argument("--hive-password", type=str,
                            help="Hive 密码 (LDAP 认证时使用)")
    hive_group.add_argument("--hive-database", type=str, default="default",
                            help="Hive 数据库 (默认: default)")
    hive_group.add_argument("--hive-auth", type=str, default="NONE",
                            choices=["NONE", "LDAP", "KERBEROS"],
                            help="Hive 认证方式 (默认: NONE)")

    args = parser.parse_args()

    # 创建后端
    print("=" * 60)
    print("Arrow Flight SQL 服务器")
    print("=" * 60)

    try:
        backend = create_backend(args)
    except Exception as e:
        print(f"[错误] 创建后端失败: {e}")
        return 1

    # 创建并启动服务器
    server = FlightSqlServer(
        backend=backend,
        host=args.host,
        port=args.port,
        party=args.party
    )

    print(f"后端: {args.backend.upper()}")
    if args.backend == "hive":
        print(f"Hive: {args.hive_host}:{args.hive_port}/{args.hive_database}")
    print(f"监听: grpc://{args.host}:{args.port}")
    print("-" * 60)
    print("按 Ctrl+C 停止服务器")
    print()

    try:
        server.serve()
    except KeyboardInterrupt:
        print(f"\n[{args.party}] 正在关闭服务器...")
        server.shutdown()
        print(f"[{args.party}] 服务器已停止")

    return 0


if __name__ == "__main__":
    exit(main())
