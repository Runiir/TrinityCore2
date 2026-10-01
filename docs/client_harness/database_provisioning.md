# Isolated client lab database

The client lab now has its own running MariaDB instance at **127.0.0.1:13306**. It uses container `trinity-client442-db`, volume `trinity-client442-db-data`, and dedicated bridge network `trinity-client442-net`. The container is limited to one CPU and 512 MiB RAM and restarts unless explicitly stopped. The existing boss-bot database was not connected to, and its container identity, startup time, storage and network remained unchanged during the recorded verification.

The four databases are seeded from this checkout's versioned **4.3.4 build 15595 base schemas**, preserving the requested backend baseline. Their `client442_` names identify the future client compatibility lab; they do not mean a 4.4.2-compatible server has been implemented.

| Database | Imported tables |
| --- | ---: |
| `client442_auth` | 21 |
| `client442_world` | 194 |
| `client442_characters` | 106 |
| `client442_hotfixes` | 9 |

The runtime account has privileges on exactly these four schemas and no global privileges beyond USAGE. TCP identity, schema counts and a temporary-table read/write probe passed. Reads against `mysql.user`, `auth.account`, `world.creature` and `characters.characters` were denied. Those negative probes ran on the new instance, never on the boss-bot database. The schema count checks matched every source CREATE TABLE count.

Generated credentials live outside Git under `/home/runiir/.local/share/trinity-client442-lab/secrets/`, with mode 0600 in private directories. The ready connection fragment is `/home/runiir/.local/share/trinity-client442-lab/database.connections.conf`, also mode 0600. It contains the four database connection keys, all targeting the owned loopback port. No passwords are included in the receipt, DVC archive or repository.

The initial provisioning attempt imported all schemas but failed because its seed realm name exceeded the legacy name-column limit. Its internal Docker network also prevented publishing the requested host port. The realm name was shortened to `Client442 Lab`, and only the owned lab network was replaced with a dedicated bridge. The existing schema imports were retained, then all final checks passed. The isolated seed realm advertises loopback world port 18085 and native build 15595.

World gameplay content and post-base schema updates are **not loaded**. No authserver, worldserver or client was launched. The connection fragment is not a complete server config. Before worldserver startup, the lab still needs the selected client compatibility implementation, clean world content, the backend's required updates, client assets and complete isolated runtime configs.

The [isolation plan](../../experiments/configs/client_harness/442_isolation_plan_v1.json) records the current state and keeps server launch disabled. The [DVC evidence pointer](../../artifacts/client_harness/442_database_provision_20261001.tar.gz.dvc) retains the sanitized receipt, exact source hashes, container/image identity, grant checks and DVCLive metrics.

Use the pinned image and [provisioning tool](../../tools/client_compatibility/provision_database.py) for a fresh lab. It refuses existing identities by default; its explicit completion mode verifies owned storage and credentials and does not reimport schemas. Never run the existing root docker-compose stack or default host-server targets for this lab.
