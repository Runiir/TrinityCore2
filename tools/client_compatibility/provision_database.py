"""Provision a new owned database instance; never connect to the boss-bot database."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import time

import pymysql


SOURCES = {
    "auth": "sql/base/auth_database.sql",
    "world": "sql/base/dev/world_database.sql",
    "characters": "sql/base/characters_database.sql",
    "hotfixes": "sql/base/dev/hotfixes_database.sql",
}
IMAGE = "mariadb@sha256:8a99982dced50264560fd8ada91aa34c276636bc02713f01f252c540930f9915"
OWNER = "trinity-client442-lab"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--complete-existing", action="store_true",
                        help="Finish verification of this tool's owned fresh instance without reimporting schemas")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    repository = Path(__file__).resolve().parents[2]
    db = plan["database"]
    root = Path(plan["runtime"]["owned_root"])
    name, volume, network = db["instance_name"], db["data_volume"], "trinity-client442-net"
    schemas = db["database_names"]
    expected = {role: "client442_" + role for role in SOURCES}
    if (name != "trinity-client442-db" or volume != "trinity-client442-db-data"
            or schemas != expected or db["host"] != "127.0.0.1"
            or db["proposed_host_port"] != 13306
            or root != Path.home() / ".local/share/trinity-client442-lab"
            or db["reuse_existing_volume"] or db["import_live_boss_database"]):
        raise SystemExit("plan does not match the dedicated lab identity")
    if args.output.exists() or (root.exists() and not args.complete_existing):
        raise SystemExit("output/lab root already exists; refusing to overwrite or reprovision")
    passwords = []

    def run(command: list[str], data: bytes | None = None) -> str:
        result = subprocess.run(command, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode:
            detail = result.stderr.decode(errors="replace")
            for password in passwords:
                detail = detail.replace(password, "<redacted>")
            raise RuntimeError(f"{command[0]} operation failed: {detail}")
        return result.stdout.decode()

    for command, item in [("container", name), ("volume", volume), ("network", network)]:
        found = subprocess.run(["docker", command, "inspect", item], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL).returncode == 0
        if found != args.complete_existing:
            raise SystemExit(f"{command} {item} already exists; no automatic reuse")
    if not args.complete_existing:
        with socket.socket() as listener:
            listener.bind((db["host"], db["proposed_host_port"]))
    image = json.loads(run(["docker", "image", "inspect", IMAGE]))[0]

    if args.complete_existing:
        owned = json.loads(run(["docker", "inspect", name]))[0]
        if owned["Config"]["Labels"].get("com.trinity.client-harness.owner") != OWNER:
            raise SystemExit("existing instance is not owned by this lab")
        mounts = {item["Destination"]: item for item in owned["Mounts"]}
        if mounts["/var/lib/mysql"].get("Name") != volume or mounts["/run/secrets"]["Source"] != str(root / "secrets"):
            raise SystemExit("existing instance has different storage or credentials")

    def boss_identity() -> dict | None:
        result = subprocess.run(["docker", "inspect", "trinity-cata-db"], capture_output=True)
        if result.returncode:
            return None
        value = json.loads(result.stdout)[0]
        return {"id": value["Id"], "started_at": value["State"]["StartedAt"],
                "running": value["State"]["Running"],
                "storage": [m["Source"] for m in value["Mounts"] if m["Destination"] == "/var/lib/mysql"],
                "networks": sorted(value["NetworkSettings"]["Networks"])}

    before = boss_identity()
    if not args.complete_existing:
        root.mkdir(parents=True, mode=0o700)
        os.chmod(root, 0o700)
    private = root / "secrets"
    if args.complete_existing:
        admin = (private / "root_password").read_text().strip()
        credentials = json.loads((private / "runtime.json").read_text())
        if credentials["host"] != "127.0.0.1" or credentials["port"] != 13306 or credentials["user"] != db["runtime_user"] or credentials["databases"] != schemas:
            raise SystemExit("stored credentials belong to a different target")
        runtime = credentials["password"]
    else:
        private.mkdir(mode=0o700)
        admin, runtime = secrets.token_hex(32), secrets.token_hex(32)
    passwords.extend([admin, runtime])
    for filename, content in {
        "root_password": admin + "\n",
        "admin.cnf": f"[client]\nuser=root\npassword={admin}\n",
        "runtime.json": json.dumps({"host": db["host"], "port": 13306,
                                    "user": db["runtime_user"], "password": runtime,
                                    "databases": schemas}, indent=2) + "\n",
    }.items():
        if args.complete_existing:
            continue
        path = private / filename
        with path.open("x") as handle:
            os.chmod(path, 0o600)
            handle.write(content)
    label = f"com.trinity.client-harness.owner={OWNER}"
    if not args.complete_existing:
        run(["docker", "volume", "create", "--label", label, volume])
        run(["docker", "network", "create", "--label", label, network])
        run(["docker", "run", "--detach", "--name", name, "--hostname", name,
         "--label", label, "--network", network, "--restart", "unless-stopped",
         "--publish", "127.0.0.1:13306:3306", "--memory", "512m", "--memory-swap", "512m",
         "--cpus", "1", "--pids-limit", "256",
         "--mount", f"type=volume,source={volume},target=/var/lib/mysql",
         "--mount", f"type=bind,source={private},target=/run/secrets,readonly",
         "--env", "MARIADB_ROOT_PASSWORD_FILE=/run/secrets/root_password",
         IMAGE, "--max-connections=32", "--innodb-buffer-pool-size=128M"])

    sql_command = ["docker", "exec", "--interactive", name, "mariadb",
                   "--defaults-extra-file=/run/secrets/admin.cnf", "--batch", "--skip-column-names"]
    for attempt in range(60):
        try:
            if run(sql_command, b"SELECT 1;\n").strip() == "1":
                break
        except RuntimeError:
            if attempt == 59:
                raise
        time.sleep(1)
    creation = [f"CREATE DATABASE `{schema}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
                for schema in schemas.values()]
    creation.append(f"CREATE USER '{db['runtime_user']}'@'%' IDENTIFIED BY '{runtime}';")
    creation.extend(f"GRANT ALL PRIVILEGES ON `{schema}`.* TO '{db['runtime_user']}'@'%';"
                    for schema in schemas.values())
    if not args.complete_existing:
        run(sql_command, ("\n".join(creation) + "\n").encode())
    source_receipts = {}
    for role, source in SOURCES.items():
        data = (repository / source).read_bytes()
        if b"CREATE DATABASE " in data or b"\nUSE " in data:
            raise RuntimeError(f"source {source} overrides database selection")
        if not args.complete_existing:
            run(sql_command + [schemas[role]], data)
        source_receipts[role] = {"path": source, "sha256": hashlib.sha256(data).hexdigest()}
    realm_sql = ("UPDATE realmlist SET name='Client442 Lab', "
                 "address='127.0.0.1',localAddress='127.0.0.1',port=18085,gamebuild=15595 WHERE id=1;")
    run(sql_command + [schemas["auth"]], realm_sql.encode())

    connection = pymysql.connect(host=db["host"], port=13306, user=db["runtime_user"],
                                 password=runtime, connect_timeout=5)
    denied, table_counts = {}, {}
    with connection.cursor() as cursor:
        cursor.execute("SELECT @@hostname,@@port,@@version,CURRENT_USER()")
        hostname, inner_port, version, current_user = cursor.fetchone()
        if hostname != name or inner_port != 3306:
            raise RuntimeError("runtime TCP connection reached the wrong database identity")
        for schema in schemas.values():
            cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s", (schema,))
            table_counts[schema] = cursor.fetchone()[0]
            if not table_counts[schema]:
                raise RuntimeError(f"schema import is empty: {schema}")
        for role, path in SOURCES.items():
            expected_tables = len(re.findall(r"^CREATE TABLE ", (repository / path).read_text(), re.M))
            if table_counts[schemas[role]] != expected_tables:
                raise RuntimeError(f"schema import table count differs from source: {role}")
        cursor.execute("SELECT PRIVILEGE_TYPE FROM information_schema.USER_PRIVILEGES")
        global_privileges = sorted(row[0] for row in cursor.fetchall())
        if any(value != "USAGE" for value in global_privileges):
            raise RuntimeError("runtime account has global privileges")
        cursor.execute("SELECT DISTINCT TABLE_SCHEMA FROM information_schema.SCHEMA_PRIVILEGES")
        allowed = sorted(row[0] for row in cursor.fetchall())
        if allowed != sorted(schemas.values()):
            raise RuntimeError("runtime schema grants do not match the lab allowlist")
        for schema, table in [("mysql", "user"), ("auth", "account"), ("world", "creature"), ("characters", "characters")]:
            try:
                cursor.execute(f"SELECT * FROM `{schema}`.`{table}` LIMIT 0")
            except pymysql.MySQLError as error:
                if error.args[0] not in (1044, 1142):
                    raise
                denied[schema] = error.args[0]
            else:
                raise RuntimeError(f"runtime unexpectedly accessed non-lab schema {schema}")
        cursor.execute(f"USE `{schemas['characters']}`")
        cursor.execute("CREATE TEMPORARY TABLE harness_provision_probe (value INT)")
        cursor.execute("INSERT INTO harness_provision_probe VALUES (1)")
        cursor.execute("SELECT value FROM harness_provision_probe")
        assert cursor.fetchone() == (1,)
    connection.close()
    after = boss_identity()
    if before != after:
        raise RuntimeError("boss database container identity/start/storage/network changed during provisioning")
    owned = json.loads(run(["docker", "inspect", name]))[0]
    bindings = owned["HostConfig"]["PortBindings"]
    if bindings != {"3306/tcp": [{"HostIp": "127.0.0.1", "HostPort": "13306"}]}:
        raise RuntimeError("database listener is not restricted to the planned loopback endpoint")
    if sorted(owned["NetworkSettings"]["Networks"]) != [network]:
        raise RuntimeError("database container is attached to an unexpected network")
    config = root / "database.connections.conf"
    with config.open("x") as handle:
        os.chmod(config, 0o600)
        for role, key in [("auth", "Login"), ("world", "World"), ("characters", "Character"), ("hotfixes", "Hotfix")]:
            handle.write(f'{key}DatabaseInfo = "127.0.0.1;13306;{db["runtime_user"]};{runtime};{schemas[role]}"\n')
    receipt = {
        "schema": "client_harness_database_provision_receipt_v1",
        "container": name, "container_id": owned["Id"], "network": network, "volume": volume,
        "image": IMAGE, "image_id": image["Id"], "endpoint": "127.0.0.1:13306",
        "server_version": version, "runtime_user": current_user, "database_names": schemas,
        "table_counts": table_counts, "schema_grants": allowed, "global_privileges": global_privileges,
        "denied_non_lab_schema_reads": denied, "read_write_probe_passed": True,
        "boss_container_metadata_unchanged_during_verification": before == after,
        "boss_database_connected": False, "source_commit": run(["git", "-C", str(repository), "rev-parse", "HEAD"]).strip(),
        "source_schemas": source_receipts, "native_schema_baseline": "4.3.4 build 15595",
        "world_content_loaded": False, "schema_updates_applied": False, "server_launch_allowed": False,
        "credentials_directory": str(private), "connection_config": str(config),
        "resource_limits": {"memory_bytes": owned["HostConfig"]["Memory"], "nano_cpus": owned["HostConfig"]["NanoCpus"]},
        "schema_imports_repeated": False if args.complete_existing else None,
        "provisioning_fixes": ["shortened_seed_realm_name_to_fit_legacy_column", "dedicated_bridge_for_loopback_port_publication"] if args.complete_existing else [],
    }
    args.output.mkdir(parents=True)
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"endpoint": receipt["endpoint"], "databases": table_counts,
                      "isolation_verified": True, "receipt": str(args.output / "receipt.json")}, indent=2))


if __name__ == "__main__":
    main()
