#!/usr/bin/env python3
"""
Arrow Flight SQL 测试服务器
用于模拟 Hive 后端，支持 SCQL 联合查询测试

此服务器实现了 Arrow Flight SQL 协议的核心功能，包括:
- GetFlightInfo: 处理 SQL 查询请求 (解析 CommandStatementQuery protobuf)
- DoGet: 返回查询结果

使用方法:
    # 启动 Alice 服务器 (端口 8815)
    python3 arrow_flight_server.py --party alice --port 8815

    # 启动 Bob 服务器 (端口 8816)
    python3 arrow_flight_server.py --party bob --port 8816
"""

import argparse
import pyarrow as pa
import pyarrow.flight as flight
import duckdb


# =============================================================================
# Protobuf parsing (using google.protobuf library)
# =============================================================================

def parse_flight_sql_command(data: bytes) -> str:
    """
    Parse Arrow Flight SQL CommandStatementQuery protobuf message.

    Uses google.protobuf to unwrap Any wrapper if present,
    then extracts the query string from field 1.

    Requires: pip install protobuf
    """
    if not data:
        return ""

    try:
        from google.protobuf import descriptor_pb2
        from google.protobuf.any_pb2 import Any as AnyProto
        from google.protobuf.descriptor_pool import DescriptorPool
        from google.protobuf.message_factory import GetMessageClass

        # Try to unwrap google.protobuf.Any
        if b"type.googleapis.com" in data:
            any_msg = AnyProto()
            any_msg.ParseFromString(data)
            data = any_msg.value

        # Build a minimal CommandStatementQuery descriptor dynamically
        file_desc_proto = descriptor_pb2.FileDescriptorProto(
            name="flight_sql.proto",
            package="arrow.flight.protocol.sql",
            message_type=[descriptor_pb2.DescriptorProto(
                name="CommandStatementQuery",
                field=[
                    descriptor_pb2.FieldDescriptorProto(
                        name="query", number=1, type=9,  # TYPE_STRING
                        label=1,  # LABEL_OPTIONAL
                    ),
                    descriptor_pb2.FieldDescriptorProto(
                        name="transaction_id", number=2, type=9,
                        label=1,
                    ),
                ],
            )],
        )
        pool = DescriptorPool()
        pool.Add(file_desc_proto)
        desc = pool.FindMessageTypeByName(
            "arrow.flight.protocol.sql.CommandStatementQuery"
        )
        CmdClass = GetMessageClass(desc)
        msg = CmdClass()
        msg.ParseFromString(data)
        return msg.query

    except Exception as e:
        print(f"[warning] protobuf parse failed, falling back to raw decode: {e}")
        return data.decode("utf-8", errors="replace")


class FlightSqlServer(flight.FlightServerBase):
    """
    Arrow Flight SQL 服务器实现

    支持 SCQL 引擎通过 FlightSqlClient 发送的请求
    """

    def __init__(self, host="0.0.0.0", port=8815, party="alice"):
        location = f"grpc://0.0.0.0:{port}"
        super().__init__(location)
        self.party = party
        self._port = port
        self._host = host
        self.conn = duckdb.connect(":memory:")
        self._queries = {}  # ticket_id -> query
        self._ticket_counter = 0
        self._init_data()
        print(f"[{party}] Arrow Flight SQL 服务器启动在端口 {port}")

    def _init_data(self):
        """初始化测试数据"""
        # 创建 default schema 以兼容 SCQL 的 db.table 格式
        self.conn.execute("CREATE SCHEMA IF NOT EXISTS \"default\"")
        self.conn.execute('SET search_path TO "default"')

        if self.party == "alice":
            # Alice 的用户信用数据
            self.conn.execute("""
                CREATE TABLE "default".user_credit (
                    ID VARCHAR PRIMARY KEY,
                    credit_rank INTEGER,
                    income INTEGER,
                    age INTEGER
                )
            """)
            self.conn.execute("""
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
            """)
            print(f"[{self.party}] 初始化 user_credit 表 (19 行)")

        elif self.party == "bob":
            # Bob 的用户统计数据
            self.conn.execute("""
                CREATE TABLE "default".user_stats (
                    ID VARCHAR PRIMARY KEY,
                    order_amount INTEGER,
                    is_active INTEGER
                )
            """)
            self.conn.execute("""
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
            """)
            print(f"[{self.party}] 初始化 user_stats 表 (19 行)")

    def _preprocess_query(self, query: str) -> str:
        """Preprocess SQL query: strip database prefix for DuckDB backend."""
        import re
        # SCQL engine sends SQL with party name prefix (e.g. alice.user_credit, bob.user_stats)
        # Strip any db.table prefix since DuckDB tables are in the default schema via search_path
        query = re.sub(r'\b\w+\.(\w+)', r'\1', query, flags=re.IGNORECASE)
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

        Arrow Flight SQL 客户端通过此方法发送 SQL 查询。
        命令被编码在 descriptor.command 中，格式为 CommandStatementQuery protobuf。
        """
        # 从 descriptor 中提取 SQL 查询
        if descriptor.descriptor_type == flight.DescriptorType.CMD:
            query = parse_flight_sql_command(descriptor.command)
        elif descriptor.descriptor_type == flight.DescriptorType.PATH:
            # 表名查询
            table_name = "/".join(p.decode() if isinstance(p, bytes) else p for p in descriptor.path)
            query = f"SELECT * FROM {table_name}"
        else:
            raise flight.FlightUnavailableError("Unsupported descriptor type")

        # 预处理查询：将 default.table_name 转换为 "default".table_name
        query = self._preprocess_query(query)

        print(f"[{self.party}] GetFlightInfo - Query: {query[:100]}...")

        # 执行查询获取 schema
        try:
            result = self.conn.execute(query).fetch_arrow_table()
            schema = result.schema
            num_rows = result.num_rows

            # 保存查询以供 DoGet 使用
            ticket_bytes = self._generate_ticket(query)
            ticket = flight.Ticket(ticket_bytes)

            # 创建 endpoint
            location = flight.Location.for_grpc_tcp("localhost", self._port)
            endpoint = flight.FlightEndpoint(ticket, [location])

            info = flight.FlightInfo(
                schema,
                descriptor,
                [endpoint],
                num_rows,
                -1  # 未知的字节数
            )

            print(f"[{self.party}] FlightInfo created - rows: {num_rows}, columns: {len(schema)}")
            return info

        except Exception as e:
            print(f"[{self.party}] 查询错误: {e}")
            raise flight.FlightServerError(f"Query execution failed: {e}")

    def do_get(self, context, ticket):
        """
        处理 DoGet 请求，返回查询结果

        ticket 包含查询 ID 或直接是 SQL 查询
        """
        ticket_data = ticket.ticket.decode("utf-8")

        # 检查是否是保存的 ticket ID
        if ticket_data in self._queries:
            query = self._queries[ticket_data]
            # 清理已使用的 ticket
            del self._queries[ticket_data]
        else:
            # 直接使用 ticket 作为查询
            query = ticket_data

        # 预处理查询
        query = self._preprocess_query(query)

        print(f"[{self.party}] DoGet - Query: {query[:100]}...")

        try:
            result = self.conn.execute(query).fetch_arrow_table()
            print(f"[{self.party}] 返回 {result.num_rows} 行, {result.num_columns} 列")
            return flight.RecordBatchStream(result)
        except Exception as e:
            print(f"[{self.party}] 查询错误: {e}")
            raise flight.FlightServerError(f"Query execution failed: {e}")

    def list_flights(self, context, criteria):
        """列出可用的表"""
        tables = self.conn.execute("SHOW TABLES").fetchall()
        for table in tables:
            table_name = table[0]
            descriptor = flight.FlightDescriptor.for_path(table_name)
            schema = self.conn.execute(f"SELECT * FROM {table_name} LIMIT 0").fetch_arrow_table().schema
            yield flight.FlightInfo(
                schema,
                descriptor,
                [],
                -1,
                -1
            )

    def do_action(self, context, action):
        """处理 Action 请求"""
        action_type = action.type
        print(f"[{self.party}] Action: {action_type}")

        if action_type == "healthcheck":
            yield flight.Result(b"ok")
        else:
            # Flight SQL 使用各种 action，这里返回空结果
            yield flight.Result(b"")

    def list_actions(self, context):
        """列出支持的 actions"""
        return [
            ("healthcheck", "Health check"),
        ]


def main():
    parser = argparse.ArgumentParser(description="Arrow Flight SQL 测试服务器")
    parser.add_argument("--party", type=str, default="alice", choices=["alice", "bob"],
                        help="参与方名称 (alice 或 bob)")
    parser.add_argument("--port", type=int, default=8815,
                        help="服务端口")
    parser.add_argument("--host", type=str, default="0.0.0.0",
                        help="监听地址")
    args = parser.parse_args()

    server = FlightSqlServer(host=args.host, port=args.port, party=args.party)
    print(f"Arrow Flight SQL 服务器 [{args.party}] 正在运行...")
    print(f"连接地址: grpc://localhost:{args.port}")
    print("按 Ctrl+C 停止服务器")

    try:
        server.serve()
    except KeyboardInterrupt:
        print(f"\n[{args.party}] 服务器已停止")


if __name__ == "__main__":
    main()
