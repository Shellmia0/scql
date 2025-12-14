#!/bin/bash
set -e

# Ask for password
read -s -p "Enter MySQL root password (leave empty if none): " MYSQL_PASS

CMD="mysql -u root"
if [ ! -z "$MYSQL_PASS" ]; then
    CMD="mysql -u root -p$MYSQL_PASS"
fi

echo "Initializing Alice Database..."
$CMD < mysql/initdb/alice_init.sql

echo "Initializing Bob Database..."
$CMD < mysql/initdb/bob_init.sql

echo "Initializing SCDB Database..."
$CMD < mysql/initdb/scdb_init.sql

echo "Database initialization complete."

