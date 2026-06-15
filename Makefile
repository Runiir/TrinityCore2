COMPOSE ?= docker compose
SERVICE_IMAGE ?= trinity-cata-server:local
BUILD_DIR ?= build
INSTALL_DIR ?= server
CLIENT_DIR ?=
DATA_DIR ?= $(CURDIR)/data
JOBS ?= $(shell nproc)
AUTH_TEST_CONF ?= trinity-authserver-test.conf
WORLD_TEST_CONF ?= trinity-worldserver-test.conf
BOTWORLD_AUTOSTART ?= 0
BOTWORLD_AUTOSTART_RECORDING ?= 0
BOTWORLD_RECORDING_WINDOW_MINUTES ?= 30
BOTPOLICYMODEL_ENABLE ?= 0
BOTPOLICYMODEL_MODE ?= shadow
BOTPOLICYMODEL_VERSION ?=
BOTPOLICYMODEL_SCORE_WEIGHT ?= 1.0

.PHONY: help build binaries runtime-image local-configure local-build local-install db up down logs shell auth world test-configs host-auth host-world clean-db clean-images data-dir require-client extract-maps extract-vmaps assemble-vmaps extract-mmaps extract-assets

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
		'  make test-configs Create local host-run test configs' \
		'  make host-auth    Run host-built authserver with trinity-authserver-test.conf' \
		'  make host-world   Run host-built worldserver with trinity-worldserver-test.conf' \
		'                    Use BOTWORLD_AUTOSTART=1 BOTWORLD_AUTOSTART_RECORDING=1 for always-on recording' \
		'                    Use BOTPOLICYMODEL_ENABLE=1 BOTPOLICYMODEL_MODE=shadow BOTPOLICYMODEL_VERSION=... to shadow a registered model' \
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

test-configs:
	cp src/server/authserver/authserver.conf.dist "$(AUTH_TEST_CONF)"
	cp src/server/worldserver/worldserver.conf.dist "$(WORLD_TEST_CONF)"
	perl -0pi -e 's|LoginDatabaseInfo\s*=\s*"127\.0\.0\.1;3306;trinity;trinity;auth"|LoginDatabaseInfo = "172.20.0.2;3306;trinity;trinity;auth"|g' "$(AUTH_TEST_CONF)"
	perl -0pi -e 's|DataDir\s*=\s*"."|DataDir = "$(DATA_DIR)"|g; s|LoginDatabaseInfo\s*=\s*"127\.0\.0\.1;3306;trinity;trinity;auth"|LoginDatabaseInfo = "172.20.0.2;3306;trinity;trinity;auth"|g; s|WorldDatabaseInfo\s*=\s*"127\.0\.0\.1;3306;trinity;trinity;world"|WorldDatabaseInfo = "172.20.0.2;3306;trinity;trinity;world"|g; s|CharacterDatabaseInfo\s*=\s*"127\.0\.0\.1;3306;trinity;trinity;characters"|CharacterDatabaseInfo = "172.20.0.2;3306;trinity;trinity;characters"|g; s|HotfixDatabaseInfo\s*=\s*"127\.0\.0\.1;3306;trinity;trinity;hotfixes"|HotfixDatabaseInfo = "172.20.0.2;3306;trinity;trinity;hotfixes"|g; s|PlayerBot\.Enable\s*=\s*0|PlayerBot.Enable = 1|g; s|Ra\.Enable\s*=\s*0|Ra.Enable = 1|g; s|SOAP\.Enabled\s*=\s*0|SOAP.Enabled = 1|g' "$(WORLD_TEST_CONF)"
	perl -0pi -e 's|BotWorld\.AutoStart\s*=\s*\d+|BotWorld.AutoStart = $(BOTWORLD_AUTOSTART)|g; s|BotWorld\.AutoStartRecording\s*=\s*\d+|BotWorld.AutoStartRecording = $(BOTWORLD_AUTOSTART_RECORDING)|g; s|BotWorld\.AutoRecordingWindowMinutes\s*=\s*\d+|BotWorld.AutoRecordingWindowMinutes = $(BOTWORLD_RECORDING_WINDOW_MINUTES)|g' "$(WORLD_TEST_CONF)"
	perl -0pi -e 's|BotPolicyModel\.Enable\s*=\s*\d+|BotPolicyModel.Enable = $(BOTPOLICYMODEL_ENABLE)|g; s|BotPolicyModel\.Mode\s*=\s*\w+|BotPolicyModel.Mode = $(BOTPOLICYMODEL_MODE)|g; s|BotPolicyModel\.Version\s*=\s*.*|BotPolicyModel.Version = $(BOTPOLICYMODEL_VERSION)|g; s|BotPolicyModel\.ScoreWeight\s*=\s*[0-9.]+|BotPolicyModel.ScoreWeight = $(BOTPOLICYMODEL_SCORE_WEIGHT)|g' "$(WORLD_TEST_CONF)"

host-auth: local-configure db test-configs
	cmake --build $(BUILD_DIR) --target authserver -j"$(JOBS)"
	ulimit -c unlimited && $(BUILD_DIR)/src/server/authserver/authserver --config "$(AUTH_TEST_CONF)"

host-world: local-configure db test-configs
	cmake --build $(BUILD_DIR) --target worldserver -j"$(JOBS)"
	ulimit -c unlimited && $(BUILD_DIR)/src/server/worldserver/worldserver --config "$(WORLD_TEST_CONF)"

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
