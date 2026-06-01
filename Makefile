COMPOSE ?= docker compose
SERVICE_IMAGE ?= trinity-cata-server:local
BUILD_DIR ?= build
INSTALL_DIR ?= server
CLIENT_DIR ?=
DATA_DIR ?= $(CURDIR)/data
JOBS ?= $(shell nproc)

.PHONY: help build binaries runtime-image local-configure local-build local-install db up down logs shell auth world clean-db clean-images data-dir require-client extract-maps extract-vmaps assemble-vmaps extract-mmaps extract-assets

help:
	@printf '%s\n' \
		'Targets:' \
		'  make build        Build and install host-local binaries under ./server' \
		'  make binaries     Alias for build' \
		'  make runtime-image Build the small Docker runtime image only' \
		'  make local-build   Build host-local binaries under ./build' \
		'  make local-install Install host-local binaries under ./server' \
		'  make extract-assets CLIENT_DIR=/path/to/WoW  Extract maps/dbc/vmaps/mmaps into ./data' \
		'  make extract-maps CLIENT_DIR=/path/to/WoW    Extract maps, dbc, db2, cameras into ./data' \
		'  make extract-vmaps CLIENT_DIR=/path/to/WoW   Extract raw Buildings vmap data into ./data' \
		'  make assemble-vmaps                         Build ./data/vmaps from ./data/Buildings' \
		'  make extract-mmaps                          Build ./data/mmaps from ./data maps/vmaps/dbc' \
		'  make db           Start MariaDB and initialize schemas on first run' \
		'  make up           Start db, authserver, and worldserver' \
		'  make auth         Run authserver attached' \
		'  make world        Run worldserver attached with console stdin' \
		'  make logs         Follow all service logs' \
		'  make shell        Open a shell in the server image' \
		'  make down         Stop containers' \
		'  make clean-db     Stop containers and delete the MariaDB volume' \
		'  make clean-images Remove the local server image'

build: local-install

binaries: build

runtime-image:
	$(COMPOSE) build authserver

local-configure:
	cmake -S . -B $(BUILD_DIR) \
		-DCMAKE_INSTALL_PREFIX="$(CURDIR)/$(INSTALL_DIR)" \
		-DCMAKE_BUILD_TYPE=RelWithDebInfo \
		-DSERVERS=1 \
		-DTOOLS=1 \
		-DSCRIPTS=static \
		-DUNITY_BUILDS=1

local-build: local-configure
	cmake --build $(BUILD_DIR) -j"$(JOBS)"

local-install: local-build
	cmake --install $(BUILD_DIR)

data-dir:
	mkdir -p "$(DATA_DIR)"

require-client:
	@if [ -z "$(CLIENT_DIR)" ]; then \
		printf '%s\n' 'Set CLIENT_DIR to your Cataclysm client folder, for example:'; \
		printf '%s\n' '  make extract-assets CLIENT_DIR="/home/runiir/Games/WoW 4.3.4"'; \
		exit 2; \
	fi

extract-maps: build data-dir require-client
	"$(CURDIR)/$(INSTALL_DIR)/bin/mapextractor" -i "$(CLIENT_DIR)" -o "$(DATA_DIR)"

extract-vmaps: build data-dir require-client
	cd "$(DATA_DIR)" && "$(CURDIR)/$(INSTALL_DIR)/bin/vmap4extractor" -d "$(CLIENT_DIR)"

assemble-vmaps: build data-dir
	cd "$(DATA_DIR)" && "$(CURDIR)/$(INSTALL_DIR)/bin/vmap4assembler" Buildings vmaps

extract-mmaps: build data-dir
	cd "$(DATA_DIR)" && "$(CURDIR)/$(INSTALL_DIR)/bin/mmaps_generator"

extract-assets: extract-maps extract-vmaps assemble-vmaps extract-mmaps

db:
	$(COMPOSE) up -d db

up: build
	$(COMPOSE) up

auth: build
	$(COMPOSE) run --rm --service-ports authserver

world: build
	$(COMPOSE) run --rm --service-ports worldserver

logs:
	$(COMPOSE) logs -f

shell:
	$(COMPOSE) run --rm --entrypoint /bin/bash worldserver

down:
	$(COMPOSE) down

clean-db:
	$(COMPOSE) down -v

clean-images:
	docker image rm $(SERVICE_IMAGE)
