#!/usr/bin/env python3
"""
SCQL 联合查询测试脚本
测试使用 Hive 后端的联合查询功能
"""

import requests
import json
import time

SCDB_URL = "http://localhost:8080"
ROOT_PASSWORD = "p6>14%h:u2&79k83"  # 从日志中获取

def execute_sql(sql, user="root", password=ROOT_PASSWORD):
    """执行 SCQL 查询"""
    url = f"{SCDB_URL}/public/submit_query"
    payload = {
        "user": {"user": {"account_system_type": "NATIVE_USER", "native_user": {"name": user, "password": password}}},
        "query": sql
    }
    try:
        response = requests.post(url, json=payload, timeout=60)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def fetch_result(session_id, user="root", password=ROOT_PASSWORD):
    """获取查询结果"""
    url = f"{SCDB_URL}/public/fetch_result"
    payload = {
        "user": {"user": {"account_system_type": "NATIVE_USER", "native_user": {"name": user, "password": password}}},
        "session_id": session_id
    }
    try:
        response = requests.post(url, json=payload, timeout=60)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def setup_parties():
    """设置参与方"""
    print("=== 设置参与方 ===")

    # 创建 Alice
    result = execute_sql("CREATE USER alice IDENTIFIED BY 'alice123'")
    print(f"创建 Alice 用户: {result}")

    # 创建 Bob
    result = execute_sql("CREATE USER bob IDENTIFIED BY 'bob123'")
    print(f"创建 Bob 用户: {result}")

    # 创建数据库
    result = execute_sql("CREATE DATABASE IF NOT EXISTS hive_test")
    print(f"创建数据库: {result}")

def setup_tables():
    """设置表元数据"""
    print("\n=== 设置表元数据 ===")

    # Alice 的表
    result = execute_sql("""
        CREATE TABLE hive_test.user_credit (
            ID STRING,
            credit_rank INT,
            income INT,
            age INT
        ) REF_TABLE=user_credit DB_TYPE='hive' OWNER='alice' PARTY='alice'
    """)
    print(f"创建 Alice 表: {result}")

    # Bob 的表
    result = execute_sql("""
        CREATE TABLE hive_test.user_stats (
            ID STRING,
            order_amount INT,
            is_active INT
        ) REF_TABLE=user_stats DB_TYPE='hive' OWNER='bob' PARTY='bob'
    """)
    print(f"创建 Bob 表: {result}")

def grant_permissions():
    """授权"""
    print("\n=== 授权 ===")

    # Alice 授权给 Bob
    result = execute_sql("GRANT SELECT ON hive_test.user_credit TO bob", user="alice", password="alice123")
    print(f"Alice 授权给 Bob: {result}")

    # Bob 授权给 Alice
    result = execute_sql("GRANT SELECT ON hive_test.user_stats TO alice", user="bob", password="bob123")
    print(f"Bob 授权给 Alice: {result}")

def run_federated_query():
    """运行联合查询"""
    print("\n=== 运行联合查询 ===")

    query = """
        SELECT
            a.ID,
            a.credit_rank,
            a.income,
            b.order_amount,
            b.is_active
        FROM hive_test.user_credit a
        JOIN hive_test.user_stats b ON a.ID = b.ID
        WHERE a.age >= 20 AND b.is_active = 1
        LIMIT 10
    """

    print(f"查询: {query}")
    result = execute_sql(query)
    print(f"提交查询结果: {json.dumps(result, indent=2)}")

    if "session_id" in result:
        print("\n等待查询结果...")
        time.sleep(5)

        fetch = fetch_result(result["session_id"])
        print(f"查询结果: {json.dumps(fetch, indent=2)}")

def test_basic_connectivity():
    """测试基本连接"""
    print("=== 测试 SCDB 连接 ===")
    try:
        response = requests.get(f"{SCDB_URL}/public/submit_query", timeout=5)
        print(f"SCDB 服务器状态: 运行中 (HTTP {response.status_code})")
        return True
    except Exception as e:
        print(f"SCDB 服务器连接失败: {e}")
        return False

def main():
    print("=" * 60)
    print("SCQL 联合查询测试 - Hive 后端")
    print("=" * 60)

    if not test_basic_connectivity():
        print("请先启动 SCDB 服务器")
        return

    # 简单测试 - 检查 SCDB API
    print("\n=== 测试 SCDB API ===")
    result = execute_sql("SHOW DATABASES")
    print(f"SHOW DATABASES: {json.dumps(result, indent=2)}")

if __name__ == "__main__":
    main()

