#!/bin/bash
# SCQL 隐私保护联合计算完整测试脚本

set -e

SCQL_DIR="/root/autodl-tmp/scql"
cd "$SCQL_DIR"

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# 执行 SQL 函数
exec_sql() {
    local user="$1"
    local password="$2"
    local sql="$3"
    local description="$4"

    if [ -n "$description" ]; then
        log_info "$description"
    fi

    # 创建临时 users.json
    cat > /tmp/scql_users_$$.json <<EOF
{
  "test_user": {
    "UserName": "$user",
    "Password": "$password"
  }
}
EOF

    # 执行 SQL
    result=$(echo "$sql" | bin/scdbclient source --sourceFile=/dev/stdin \
        --host=http://localhost:8080 \
        --usersConfFileName=/tmp/scql_users_$$.json \
        --userName=test_user \
        --sync 2>&1)

    # 清理临时文件
    rm -f /tmp/scql_users_$$.json

    # 返回结果
    echo "$result"
}

# 测试函数
run_test() {
    local test_name="$1"
    local user="$2"
    local password="$3"
    local sql="$4"
    local should_succeed="$5"

    echo ""
    echo "=========================================="
    log_info "测试: $test_name"
    echo "=========================================="

    result=$(exec_sql "$user" "$password" "$sql" "")

    if echo "$result" | grep -q "err:"; then
        if [ "$should_succeed" = "no" ]; then
            log_success "✅ 通过 - 查询被正确拒绝（符合预期）"
            echo "原因: $(echo "$result" | grep "err:" | head -1)"
            return 0
        else
            log_error "❌ 失败 - 查询应该成功但被拒绝"
            echo "$result" | grep "err:"
            return 1
        fi
    else
        if [ "$should_succeed" = "yes" ]; then
            log_success "✅ 通过 - 查询成功执行（符合预期）"
            echo "$result" | head -30
            return 0
        else
            log_error "❌ 失败 - 查询应该被拒绝但成功了"
            echo "$result"
            return 1
        fi
    fi
}

# ==========================================
# 主程序开始
# ==========================================

echo "=========================================="
echo "  SCQL 隐私保护联合计算完整测试"
echo "=========================================="
echo ""

# ==========================================
# 1. 前置检查
# ==========================================
log_info "步骤 1: 检查服务状态"
echo ""

if ! ps aux | grep -v grep | grep -q "scdbserver"; then
    log_error "SCDB Server 未运行"
    echo "请运行: bash examples/scdb-tutorial/start_all.sh"
    exit 1
fi

engine_count=$(ps aux | grep -v grep | grep -c "scqlengine" || true)
if [ "$engine_count" -lt 2 ]; then
    log_error "SCQLEngine 未完全启动（需要 2 个，当前 $engine_count 个）"
    echo "请运行: bash examples/scdb-tutorial/start_all.sh"
    exit 1
fi

if ! ps aux | grep -v grep | grep -q "mysqld"; then
    log_error "MySQL 未运行"
    exit 1
fi

log_success "所有服务运行正常"
echo "  - SCDB Server: 运行中"
echo "  - SCQLEngine: $engine_count 个运行中"
echo "  - MySQL: 运行中"

# ==========================================
# 2. 清理环境
# ==========================================
echo ""
log_info "步骤 2: 清理旧环境"
echo ""

exec_sql "root" "root" "DROP DATABASE IF EXISTS demo;" "删除旧数据库" > /dev/null 2>&1 || true
exec_sql "root" "root" "DROP USER IF EXISTS alice;" "删除旧用户 alice" > /dev/null 2>&1 || true
exec_sql "root" "root" "DROP USER IF EXISTS bob;" "删除旧用户 bob" > /dev/null 2>&1 || true

log_success "环境清理完成"

# ==========================================
# 3. 创建数据库
# ==========================================
echo ""
log_info "步骤 3: 创建数据库"
echo ""

exec_sql "root" "root" "CREATE DATABASE demo;" "创建数据库 demo"
log_success "数据库创建成功"

# ==========================================
# 4. 创建用户
# ==========================================
echo ""
log_info "步骤 4: 创建用户"
echo ""

log_info "生成 Alice 的 CREATE USER 语句..."
ALICE_CREATE=$(bin/scqltool genCreateUserStmt \
    --user alice --passwd some_password --party alice \
    --pem examples/scdb-tutorial/engine/alice/conf/ed25519key.pem 2>/dev/null | grep "CREATE USER")

log_info "生成 Bob 的 CREATE USER 语句..."
BOB_CREATE=$(bin/scqltool genCreateUserStmt \
    --user bob --passwd another_password --party bob \
    --pem examples/scdb-tutorial/engine/bob/conf/ed25519key.pem 2>/dev/null | grep "CREATE USER")

exec_sql "root" "root" "$ALICE_CREATE" "创建用户 alice" > /dev/null
exec_sql "root" "root" "$BOB_CREATE" "创建用户 bob" > /dev/null

log_success "用户创建成功"

# ==========================================
# 5. 授予权限
# ==========================================
echo ""
log_info "步骤 5: 授予数据库权限"
echo ""

exec_sql "root" "root" "GRANT CREATE, GRANT OPTION, DROP ON demo.* TO alice;" "授予 alice 权限" > /dev/null
exec_sql "root" "root" "GRANT CREATE, GRANT OPTION, DROP ON demo.* TO bob;" "授予 bob 权限" > /dev/null

log_success "权限授予成功"

# ==========================================
# 6. 创建表
# ==========================================
echo ""
log_info "步骤 6: 创建表"
echo ""

ALICE_TABLE="CREATE TABLE demo.user_credit (id string, credit_rank int, income int, age int) REF_TABLE=alice.user_credit DB_TYPE='mysql';"
BOB_TABLE="CREATE TABLE demo.user_stats (id string, order_amount double, is_active int) REF_TABLE=bob.user_stats DB_TYPE='mysql';"

exec_sql "alice" "some_password" "$ALICE_TABLE" "Alice 创建表 user_credit" > /dev/null
exec_sql "bob" "another_password" "$BOB_TABLE" "Bob 创建表 user_stats" > /dev/null

log_success "表创建成功"

# ==========================================
# 7. 注册 Engine 端点
# ==========================================
echo ""
log_info "步骤 7: 注册 Engine 端点"
echo ""

exec_sql "alice" "some_password" "ALTER USER alice WITH ENDPOINT 'localhost:8003';" "注册 Alice Engine" > /dev/null
exec_sql "bob" "another_password" "ALTER USER bob WITH ENDPOINT 'localhost:8004';" "注册 Bob Engine" > /dev/null

log_success "Engine 端点注册成功"
echo "  - Alice Engine: localhost:8003"
echo "  - Bob Engine: localhost:8004"

# ==========================================
# 8. 设置 CCL 权限
# ==========================================
echo ""
log_info "步骤 8: 设置 CCL 权限"
echo ""

log_info "Alice 设置 CCL..."
exec_sql "alice" "some_password" "GRANT SELECT PLAINTEXT(id, credit_rank, income, age) ON demo.user_credit TO alice;" "" > /dev/null
exec_sql "alice" "some_password" "GRANT SELECT PLAINTEXT_AFTER_JOIN(id) ON demo.user_credit TO bob;" "" > /dev/null
exec_sql "alice" "some_password" "GRANT SELECT PLAINTEXT_AFTER_GROUP_BY(credit_rank) ON demo.user_credit TO bob;" "" > /dev/null
exec_sql "alice" "some_password" "GRANT SELECT PLAINTEXT_AFTER_AGGREGATE(income) ON demo.user_credit TO bob;" "" > /dev/null
exec_sql "alice" "some_password" "GRANT SELECT PLAINTEXT_AFTER_COMPARE(age) ON demo.user_credit TO bob;" "" > /dev/null

log_info "Bob 设置 CCL..."
exec_sql "bob" "another_password" "GRANT SELECT PLAINTEXT(id, order_amount, is_active) ON demo.user_stats TO bob;" "" > /dev/null
exec_sql "bob" "another_password" "GRANT SELECT PLAINTEXT_AFTER_JOIN(id) ON demo.user_stats TO alice;" "" > /dev/null
exec_sql "bob" "another_password" "GRANT SELECT PLAINTEXT_AFTER_AGGREGATE(order_amount) ON demo.user_stats TO alice;" "" > /dev/null
exec_sql "bob" "another_password" "GRANT SELECT PLAINTEXT_AFTER_COMPARE(is_active) ON demo.user_stats TO alice;" "" > /dev/null

log_success "CCL 权限设置成功"

# ==========================================
# 9. 查看权限
# ==========================================
echo ""
log_info "步骤 9: 查看权限设置"
echo ""

log_info "Alice 的权限:"
exec_sql "root" "root" "SHOW GRANTS ON demo FOR alice;" ""

echo ""
log_info "Bob 的权限:"
exec_sql "root" "root" "SHOW GRANTS ON demo FOR bob;" ""

# ==========================================
# 10. 执行测试
# ==========================================
echo ""
echo "=========================================="
log_info "步骤 10: 执行测试用例"
echo "=========================================="

TOTAL=0
PASSED=0
FAILED=0

# 测试 1: 隐私保护的联合查询
TOTAL=$((TOTAL + 1))
if run_test \
    "隐私保护的联合查询" \
    "alice" "some_password" \
    "SELECT ta.credit_rank, COUNT(*) as cnt, AVG(ta.income) as avg_income, AVG(tb.order_amount) as avg_amount FROM demo.user_credit AS ta INNER JOIN demo.user_stats AS tb ON ta.id = tb.id WHERE ta.age >= 20 AND ta.age <= 30 AND tb.is_active = 1 GROUP BY ta.credit_rank;" \
    "yes"; then
    PASSED=$((PASSED + 1))
else
    FAILED=$((FAILED + 1))
fi

# 测试 2: Alice 尝试直接查看 Bob 的原始数据
TOTAL=$((TOTAL + 1))
if run_test \
    "Alice 尝试直接查看 Bob 的原始数据（应该被拒绝）" \
    "alice" "some_password" \
    "SELECT tb.order_amount FROM demo.user_stats AS tb LIMIT 10;" \
    "no"; then
    PASSED=$((PASSED + 1))
else
    FAILED=$((FAILED + 1))
fi

# 测试 3: Alice 尝试通过 JOIN 查看 Bob 的原始数据
TOTAL=$((TOTAL + 1))
if run_test \
    "Alice 尝试通过 JOIN 查看 Bob 的原始数据（应该被拒绝）" \
    "alice" "some_password" \
    "SELECT ta.id, tb.order_amount FROM demo.user_credit AS ta INNER JOIN demo.user_stats AS tb ON ta.id = tb.id LIMIT 10;" \
    "no"; then
    PASSED=$((PASSED + 1))
else
    FAILED=$((FAILED + 1))
fi

# 测试 4: Alice 查看 Bob 数据的聚合结果
TOTAL=$((TOTAL + 1))
if run_test \
    "Alice 查看 Bob 数据的聚合结果（应该成功）" \
    "alice" "some_password" \
    "SELECT AVG(tb.order_amount) as avg_amount FROM demo.user_stats AS tb;" \
    "yes"; then
    PASSED=$((PASSED + 1))
else
    FAILED=$((FAILED + 1))
fi

# 测试 5: Alice 查看自己的数据
TOTAL=$((TOTAL + 1))
if run_test \
    "Alice 查看自己的数据（应该成功）" \
    "alice" "some_password" \
    "SELECT * FROM demo.user_credit LIMIT 5;" \
    "yes"; then
    PASSED=$((PASSED + 1))
else
    FAILED=$((FAILED + 1))
fi

# 测试 6: Bob 查看自己的数据
TOTAL=$((TOTAL + 1))
if run_test \
    "Bob 查看自己的数据（应该成功）" \
    "bob" "another_password" \
    "SELECT * FROM demo.user_stats LIMIT 5;" \
    "yes"; then
    PASSED=$((PASSED + 1))
else
    FAILED=$((FAILED + 1))
fi

# 测试 7: Bob 尝试查看 Alice 的原始数据
TOTAL=$((TOTAL + 1))
if run_test \
    "Bob 尝试查看 Alice 的原始数据（应该被拒绝）" \
    "bob" "another_password" \
    "SELECT ta.income FROM demo.user_credit AS ta LIMIT 10;" \
    "no"; then
    PASSED=$((PASSED + 1))
else
    FAILED=$((FAILED + 1))
fi

# ==========================================
# 11. 测试结果总结
# ==========================================
echo ""
echo "=========================================="
log_info "测试结果总结"
echo "=========================================="
echo ""
echo "总测试数: $TOTAL"
echo -e "${GREEN}通过: $PASSED${NC}"
echo -e "${RED}失败: $FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    log_success "🎉 所有测试通过！"
    echo ""
    echo "验证结论："
    echo "  ✅ Alice 和 Bob 可以进行隐私保护的联合查询"
    echo "  ✅ 双方看不到对方的原始数据"
    echo "  ✅ 只能看到符合 CCL 约束的聚合结果"
    echo "  ✅ 违反 CCL 的查询被正确拒绝"
    echo "  ✅ 数据所有者对自己的数据有完全访问权限"
    echo ""
    echo "🔐 SCQL 的隐私保护机制工作正常！"
    echo ""
    echo "查看详细文档: cat PRIVACY_TEST.md"
    exit 0
else
    log_error "有 $FAILED 个测试失败"
    echo ""
    echo "请检查日志:"
    echo "  tail -f examples/scdb-tutorial/logs/alice_engine.log"
    echo "  tail -f examples/scdb-tutorial/logs/bob_engine.log"
    echo "  tail -f examples/scdb-tutorial/logs/scdbserver.log"
    exit 1
fi

