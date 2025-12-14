# SCQL 隐私保护联合计算测试

## 📋 测试目标

验证 SCQL 的核心功能：
- ✅ Alice 和 Bob 可以进行联合查询
- ✅ 双方看不到对方的原始数据
- ✅ 只能看到符合 CCL 的聚合结果
- ✅ 违反 CCL 的查询会被拒绝

## 🚀 快速开始

### 自动化测试（推荐）

```bash
cd /root/autodl-tmp/scql
bash test_privacy.sh
```

### 手动测试

参考下面的详细步骤。

## 📝 测试流程

### 1. 环境准备

**检查服务状态：**
```bash
# 检查 SCDB Server 和 SCQLEngine
ps aux | grep -E "(scdbserver|scqlengine)" | grep -v grep

# 如果未运行，启动服务
bash examples/scdb-tutorial/start_all.sh
```

### 2. 初始化数据库和用户

**创建数据库：**
```sql
CREATE DATABASE demo;
```

**创建用户：**
```bash
# 生成 Alice 的 CREATE USER 语句
bin/scqltool genCreateUserStmt \
  --user alice --passwd some_password --party alice \
  --pem examples/scdb-tutorial/engine/alice/conf/ed25519key.pem

# 生成 Bob 的 CREATE USER 语句
bin/scqltool genCreateUserStmt \
  --user bob --passwd another_password --party bob \
  --pem examples/scdb-tutorial/engine/bob/conf/ed25519key.pem
```

**授予权限：**
```sql
GRANT CREATE, GRANT OPTION, DROP ON demo.* TO alice;
GRANT CREATE, GRANT OPTION, DROP ON demo.* TO bob;
```

### 3. 创建表

**Alice 创建表：**
```sql
CREATE TABLE demo.user_credit (
  id string,
  credit_rank int,
  income int,
  age int
) REF_TABLE=alice.user_credit DB_TYPE='mysql';
```

**Bob 创建表：**
```sql
CREATE TABLE demo.user_stats (
  id string,
  order_amount double,
  is_active int
) REF_TABLE=bob.user_stats DB_TYPE='mysql';
```

### 4. 注册 Engine 端点

```sql
ALTER USER alice WITH ENDPOINT 'localhost:8003';
ALTER USER bob WITH ENDPOINT 'localhost:8004';
```

### 5. 设置 CCL 权限

**Alice 设置 CCL：**
```sql
-- Alice 自己可以看所有明文
GRANT SELECT PLAINTEXT(id, credit_rank, income, age) ON demo.user_credit TO alice;

-- Bob 只能在特定条件下使用
GRANT SELECT PLAINTEXT_AFTER_JOIN(id) ON demo.user_credit TO bob;
GRANT SELECT PLAINTEXT_AFTER_GROUP_BY(credit_rank) ON demo.user_credit TO bob;
GRANT SELECT PLAINTEXT_AFTER_AGGREGATE(income) ON demo.user_credit TO bob;
GRANT SELECT PLAINTEXT_AFTER_COMPARE(age) ON demo.user_credit TO bob;
```

**Bob 设置 CCL：**
```sql
-- Bob 自己可以看所有明文
GRANT SELECT PLAINTEXT(id, order_amount, is_active) ON demo.user_stats TO bob;

-- Alice 只能在特定条件下使用
GRANT SELECT PLAINTEXT_AFTER_JOIN(id) ON demo.user_stats TO alice;
GRANT SELECT PLAINTEXT_AFTER_AGGREGATE(order_amount) ON demo.user_stats TO alice;
GRANT SELECT PLAINTEXT_AFTER_COMPARE(is_active) ON demo.user_stats TO alice;
```

### 6. 执行测试查询

#### 测试 1: ✅ 隐私保护的联合查询（成功）

```sql
SELECT
  ta.credit_rank,
  COUNT(*) as cnt,
  AVG(ta.income) as avg_income,
  AVG(tb.order_amount) as avg_amount
FROM demo.user_credit AS ta
INNER JOIN demo.user_stats AS tb ON ta.id = tb.id
WHERE ta.age >= 20 AND ta.age <= 30 AND tb.is_active = 1
GROUP BY ta.credit_rank;
```

**预期结果：** 查询成功，返回聚合数据
```
+-------------+-----+------------+------------+
| credit_rank | cnt | avg_income | avg_amount |
+-------------+-----+------------+------------+
|           6 |   4 |  336016.22 |  5499.4043 |
|           5 |   6 |  18069.775 |  7743.3486 |
+-------------+-----+------------+------------+
```

#### 测试 2: ❌ 直接查看对方原始数据（失败）

```sql
-- Alice 尝试查看 Bob 的原始数据
SELECT tb.order_amount FROM demo.user_stats AS tb LIMIT 10;
```

**预期结果：** 查询被拒绝，CCL 检查失败

#### 测试 3: ❌ 通过 JOIN 查看原始数据（失败）

```sql
-- Alice 尝试通过 JOIN 查看 Bob 的原始数据
SELECT ta.id, tb.order_amount
FROM demo.user_credit AS ta
INNER JOIN demo.user_stats AS tb ON ta.id = tb.id
LIMIT 10;
```

**预期结果：** 查询被拒绝，CCL 检查失败

#### 测试 4: ✅ 查看聚合结果（成功）

```sql
-- Alice 查看 Bob 数据的聚合结果
SELECT AVG(tb.order_amount) as avg_amount
FROM demo.user_stats AS tb;
```

**预期结果：** 查询成功，返回聚合值

## 📊 测试结果验证

| 测试项 | 预期 | 验证点 |
|-------|------|--------|
| 联合查询 | ✅ 成功 | 返回聚合结果，不暴露原始数据 |
| 查看对方原始数据 | ❌ 失败 | CCL 检查拒绝 |
| JOIN 绕过 CCL | ❌ 失败 | CCL 检查拒绝 |
| 查看聚合结果 | ✅ 成功 | 符合 CCL 约束 |

## 🔍 查看日志

```bash
# Alice Engine 日志
tail -f examples/scdb-tutorial/logs/alice_engine.log

# Bob Engine 日志
tail -f examples/scdb-tutorial/logs/bob_engine.log

# SCDB Server 日志
tail -f examples/scdb-tutorial/logs/scdbserver.log
```

## 📚 相关文档

- `FINAL_ANSWER.txt` - 问题回答总结
- `LOCAL_DEPLOYMENT_GUIDE.md` - 部署指南

