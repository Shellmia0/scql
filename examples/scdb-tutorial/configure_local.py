import os
import sys
import glob

# Configuration
WORK_DIR = os.getcwd()
if not WORK_DIR.endswith("examples/scdb-tutorial"):
    print("Error: Please run this script from 'examples/scdb-tutorial' directory")
    sys.exit(1)

# User input for MySQL password
mysql_password = input("Please enter your local MySQL root password: ").strip()
if not mysql_password:
    print("Error: Password cannot be empty")
    sys.exit(1)

# Paths to config files
alice_conf = "engine/alice/conf/gflags.conf"
bob_conf = "engine/bob/conf/gflags.conf"
scdb_conf = "scdb/conf/config.yml"
scdb_host = "scdb/conf/config.yml"

def update_file(filepath, replacements):
    with open(filepath, 'r') as f:
        content = f.read()

    for old, new in replacements.items():
        content = content.replace(old, new)

    with open(filepath, 'w') as f:
        f.write(content)
    print(f"Updated {filepath}")

# 1. Update Alice Config
# We need to read from current file which might have random password from setup.sh
# But it's easier to read the file and replace the whole connection string regex,
# or just simpler: re-read .template if available?
# Let's try to be robust and read the template if exists, else read the file.
# However, setup.sh modifies files in place if they don't end in .template (it generates them from .template)
# So we can re-generate from .template

def process_template(template_path, output_path, replacements):
    if not os.path.exists(template_path):
        print(f"Warning: Template {template_path} not found, skipping.")
        return
    with open(template_path, 'r') as f:
        content = f.read()

    for old, new in replacements.items():
        content = content.replace(old, new)

    with open(output_path, 'w') as f:
        f.write(content)
    print(f"Generated {output_path} from template")

# Replacements for Alice
alice_replacements = {
    "__MYSQL_ROOT_PASSWD__": mysql_password,
    "/home/admin/engine/conf": f"{WORK_DIR}/engine/alice/conf",
    "host=mysql": "host=127.0.0.1",
    # Fix setup.sh's randomness if we are running on top of it
    # But since we use template, we don't care about previous random password
}
process_template("engine/alice/conf/gflags.conf.template", alice_conf, alice_replacements)

# Replacements for Bob
bob_replacements = {
    "__MYSQL_ROOT_PASSWD__": mysql_password,
    "/home/admin/engine/conf": f"{WORK_DIR}/engine/bob/conf",
    "host=mysql": "host=127.0.0.1",
    "--listen_port=8003": "--listen_port=8004", # Change Port!
}
process_template("engine/bob/conf/gflags.conf.template", bob_conf, bob_replacements)

# Replacements for SCDB
scdb_replacements = {
    "__MYSQL_ROOT_PASSWD__": mysql_password,
    "mysql:3306": "127.0.0.1:3306",
}
process_template("scdb/conf/config.yml.template", scdb_conf, scdb_replacements)

print("\nConfiguration files updated successfully!")
print(f"Alice DB Port: 8003 (default)")
print(f"Bob DB Port: 8004 (modified)")
print(f"SCDB Port: 8080 (default)")

