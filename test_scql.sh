#!/bin/bash
cd /root/autodl-tmp/scql

echo "========================================="
echo "SCQL 功能测试"
echo "========================================="

echo -e "\n1. 显示数据库:"
echo "SHOW DATABASES;" | bin/scdbclient source \
  --sourceFile=/dev/stdin \
  --host=http://localhost:8080 \
  --userName=root \
  --passwd=root \
  --sync 2>&1 | grep -A 5 "Database"

echo -e "\n2. 显示表:"
echo "SHOW TABLES FROM demo;" | bin/scdbclient source \
  --sourceFile=/dev/stdin \
  --host=http://localhost:8080 \
  --userName=root \
  --passwd=root \
  --sync 2>&1 | grep -A 5 "Tables_in_demo"

echo -e "\n3. Alice 的数据 (前3条):"
mysql -u root -p3rvUyH8QJaljB -e "SELECT * FROM alice.user_credit LIMIT 3;" 2>&1 | grep -v "Warning"

echo -e "\n4. Bob 的数据 (前3条):"
mysql -u root -p3rvUyH8QJaljB -e "SELECT * FROM bob.user_stats LIMIT 3;" 2>&1 | grep -v "Warning"

echo -e "\n========================================="
echo "测试完成！"
echo "========================================="
