# Local Docker Server

This starts a local TrinityCore Cataclysm stack with:

- MariaDB 10.11
- host-built authserver mounted into Docker on port 3724
- host-built worldserver mounted into Docker on port 8085

## Build and Start

From the repository root:

Install host build dependencies first:

```bash
sudo apt update
sudo apt install -y \
  build-essential \
  cmake \
  git \
  default-libmysqlclient-dev \
  default-mysql-client \
  libboost-all-dev \
  libboost-filesystem-dev \
  libboost-locale-dev \
  libboost-program-options-dev \
  libboost-regex-dev \
  libboost-system-dev \
  libboost-thread-dev \
  libssl-dev \
  zlib1g-dev \
  libbz2-dev \
  libreadline-dev
```

```bash
make build
make db
make up
```

`make build` compiles locally and installs into `./server`. The Docker server
containers mount that directory at `/opt/trinity`; they do not compile the core
inside Docker.

Equivalent lower-level commands are:

```bash
cmake -S . -B build \
  -DCMAKE_INSTALL_PREFIX="$PWD/server" \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DSERVERS=1 \
  -DTOOLS=1 \
  -DSCRIPTS=static \
  -DUNITY_BUILDS=1
cmake --build build -j"$(nproc)"
cmake --install build

docker compose up -d db
docker compose up authserver worldserver
```

The first database startup imports:

- `sql/base/auth_database.sql`
- `sql/base/characters_database.sql`
- `sql/base/dev/world_database.sql`
- `sql/base/dev/hotfixes_database.sql`

The database user is `trinity` / `trinity`; the root password is `root`.
The database is only exposed inside the Docker network by default.

## Client Data

Extract client data into `./data` before starting `worldserver`:

```bash
make extract-assets CLIENT_DIR="/path/to/World of Warcraft 4.3.4"
```

This runs the locally-built extractor tools from `./server/bin` and writes
generated files to `./data`.

The container mounts it at `/opt/trinity/data`, and the entrypoint writes that
path into `worldserver.conf`.

Expected folders include the usual extracted data such as `dbc`, `maps`,
`vmaps`, and `mmaps`.

## Console Commands

Run worldserver attached when you need the interactive console:

```bash
make world
```

Then create a local account from the worldserver console:

```text
account create test test
account set gmlevel test 3 -1
```

## Reset Database

MariaDB only runs `/docker-entrypoint-initdb.d` scripts for a new data volume.
To re-import the base SQL from scratch:

```bash
make clean-db
make db
```

## Connecting

The auth realm address defaults to `127.0.0.1`, which is correct when the game
client runs on the same machine as Docker. Override it if needed:

```bash
TC_REALM_ADDRESS=192.168.1.50 docker compose up authserver worldserver
```
