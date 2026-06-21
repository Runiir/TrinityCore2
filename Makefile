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
BOTWORLD_AUTOSTART_RECORDING ?= 1
BOTWORLD_ENABLE ?= 1
BOTWORLD_RUNTIME_PROFILE ?=
BOTWORLD_RECORDING_WINDOW_MINUTES ?= 15
BOTWORLD_TARGET_POPULATION ?= 5
BOTWORLD_SPAWN_MODE ?= resume_or_race_start
BOTWORLD_ALLOW_CONFIGURED_CENTER_FALLBACK ?= 0
BOTWORLD_USE_SAVED_POSITION ?= 1
BOTWORLD_QUEST_FIRST ?= 0
BOTWORLD_ALLOW_GRINDING ?= 1
BOTWORLD_GRIND_ONLY_WHEN_NO_QUEST_AVAILABLE ?= 0
BOTPOLICYMODEL_ENABLE ?= 0
BOTPOLICYMODEL_MODE ?= shadow
MODEL_VERSION ?=
BOTPOLICYMODEL_VERSION ?= $(MODEL_VERSION)
BOTPOLICYMODEL_SCORE_WEIGHT ?= 1.0
BOTPOLICYMODEL_FAIL_CLOSED ?= 1
CHARACTER_DB_URL ?= mysql://trinity:trinity@127.0.0.1:3306/characters
LIVE_VALIDATION_DIR ?= dataset/live_validation
BOT_DATASET_DIR ?= dataset/bot_ml
BOT_MODEL_DIR ?= models/bot_policy
BOT_EVAL_DIR ?= evaluations/bot_policy
OUTCOME_WINDOW_SEC ?= 180
DEATH_WINDOW_SEC ?= 180
STUCK_WINDOW_SEC ?= 180
QUEST_WINDOW_SEC ?= 600
REWARD_WINDOW_SEC ?= 300

.PHONY: help build binaries runtime-image local-configure local-build local-install db up down logs shell auth world test-configs host-auth host-world host-world-stonecore-5n host-world-blackwing-descent-10n host-world-botexp host-world-botexp-real host-world-botexp-watch host-world-botexp-small host-world-botexp-shadow bot-live-validate bot-ml-export bot-ml-build-dataset bot-ml-train bot-ml-evaluate bot-ml-register bot-ml-full clean-db clean-images data-dir require-client extract-maps extract-vmaps assemble-vmaps extract-mmaps extract-assets

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
		'  make host-world   Run host-built worldserver with always-on BotWorld test config' \
		'  make host-world-stonecore-5n  Run Stonecore 5N validation runtime profile' \
		'  make host-world-blackwing-descent-10n  Run Blackwing Descent 10N validation runtime profile' \
		'  make host-world-botexp-small  Run 5 always-on bots with 15-minute recording windows' \
		'  make host-world-botexp        Run always-on bots with configured recording windows' \
		'  make host-world-botexp-real   Run real autonomy from saved/race start positions' \
		'  make host-world-botexp-watch  Run watch/debug mode spawning near the GM' \
		'  make host-world-botexp-shadow MODEL_VERSION=policy_xxx  Run shadow policy tracing' \
		'  make bot-live-validate        Pipe .botauto diagnose/trace into worldserver and write a report' \
		'  make bot-ml-full MODEL_VERSION=policy_xxx  Export, label, validate, train, evaluate, register' \
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
	perl -0pi -e 's|^DataDir\s*=.*$$|DataDir = "$(DATA_DIR)"|gm; s|^LoginDatabaseInfo\s*=\s*"127\.0\.0\.1;3306;trinity;trinity;auth"$$|LoginDatabaseInfo = "172.20.0.2;3306;trinity;trinity;auth"|gm; s|^WorldDatabaseInfo\s*=\s*"127\.0\.0\.1;3306;trinity;trinity;world"$$|WorldDatabaseInfo = "172.20.0.2;3306;trinity;trinity;world"|gm; s|^CharacterDatabaseInfo\s*=\s*"127\.0\.0\.1;3306;trinity;trinity;characters"$$|CharacterDatabaseInfo = "172.20.0.2;3306;trinity;trinity;characters"|gm; s|^HotfixDatabaseInfo\s*=\s*"127\.0\.0\.1;3306;trinity;trinity;hotfixes"$$|HotfixDatabaseInfo = "172.20.0.2;3306;trinity;trinity;hotfixes"|gm; s|^PlayerBot\.Enable\s*=.*$$|PlayerBot.Enable = 1|gm; s|^Ra\.Enable\s*=.*$$|Ra.Enable = 1|gm; s|^SOAP\.Enabled\s*=.*$$|SOAP.Enabled = 1|gm' "$(WORLD_TEST_CONF)"
	perl -0pi -e 's|^BotWorld\.AutoStart\s*=.*$$|BotWorld.AutoStart = $(BOTWORLD_AUTOSTART)|gm; s|^BotWorld\.RuntimeProfile\s*=.*$$|BotWorld.RuntimeProfile = "$(BOTWORLD_RUNTIME_PROFILE)"|gm; s|^BotWorld\.AutoStartRecording\s*=.*$$|BotWorld.AutoStartRecording = $(BOTWORLD_AUTOSTART_RECORDING)|gm; s|^BotWorld\.AutoRecordingWindowMinutes\s*=.*$$|BotWorld.AutoRecordingWindowMinutes = $(BOTWORLD_RECORDING_WINDOW_MINUTES)|gm' "$(WORLD_TEST_CONF)"
	perl -0pi -e 's|^BotWorld\.Enable\s*=.*$$|BotWorld.Enable = $(BOTWORLD_ENABLE)|gm; s|^BotWorld\.TargetPopulation\s*=.*$$|BotWorld.TargetPopulation = $(BOTWORLD_TARGET_POPULATION)|gm; s|^BotWorld\.SpawnMode\s*=.*$$|BotWorld.SpawnMode = "$(BOTWORLD_SPAWN_MODE)"|gm; s|^BotWorld\.AllowConfiguredCenterFallback\s*=.*$$|BotWorld.AllowConfiguredCenterFallback = $(BOTWORLD_ALLOW_CONFIGURED_CENTER_FALLBACK)|gm; s|^BotWorld\.UseSavedPosition\s*=.*$$|BotWorld.UseSavedPosition = $(BOTWORLD_USE_SAVED_POSITION)|gm; s|^BotWorld\.AllowGrinding\s*=.*$$|BotWorld.AllowGrinding = $(BOTWORLD_ALLOW_GRINDING)|gm; s|^BotWorld\.QuestFirst\s*=.*$$|BotWorld.QuestFirst = $(BOTWORLD_QUEST_FIRST)|gm; s|^BotWorld\.GrindOnlyWhenNoQuestAvailable\s*=.*$$|BotWorld.GrindOnlyWhenNoQuestAvailable = $(BOTWORLD_GRIND_ONLY_WHEN_NO_QUEST_AVAILABLE)|gm; s|^BotWorld\.DeathRecoveryMode\s*=.*$$|BotWorld.DeathRecoveryMode = "safe_local"\nBotWorld.RespawnMode = "safe_local"|gm; s|^BotProgression\.AllowQuesting\s*=.*$$|BotProgression.AllowQuesting = 1\nBotWorld.AllowQuesting = 1|gm; s|^BotProgression\.AllowDungeons\s*=.*$$|BotProgression.AllowDungeons = 0|gm; s|^BotProgression\.AllowRaids\s*=.*$$|BotProgression.AllowRaids = 0|gm; s|^BotLearning\.Enable\s*=.*$$|BotLearning.Enable = 1|gm' "$(WORLD_TEST_CONF)"
	perl -0pi -e 's|^BotPolicyModel\.Enable\s*=.*$$|BotPolicyModel.Enable = $(BOTPOLICYMODEL_ENABLE)|gm; s|^BotPolicyModel\.Mode\s*=.*$$|BotPolicyModel.Mode = "$(BOTPOLICYMODEL_MODE)"|gm; s|^BotPolicyModel\.Version\s*=.*$$|BotPolicyModel.Version = "$(BOTPOLICYMODEL_VERSION)"|gm; s|^BotPolicyModel\.ScoreWeight\s*=.*$$|BotPolicyModel.ScoreWeight = $(BOTPOLICYMODEL_SCORE_WEIGHT)|gm; s|^BotPolicyModel\.FailClosed\s*=.*$$|BotPolicyModel.FailClosed = $(BOTPOLICYMODEL_FAIL_CLOSED)|gm' "$(WORLD_TEST_CONF)"

host-auth: local-configure db test-configs
	cmake --build $(BUILD_DIR) --target authserver -j"$(JOBS)"
	ulimit -c unlimited && $(BUILD_DIR)/src/server/authserver/authserver --config "$(AUTH_TEST_CONF)"

host-world: local-configure db test-configs
	cmake --build $(BUILD_DIR) --target worldserver -j"$(JOBS)"
	ulimit -c unlimited && $(BUILD_DIR)/src/server/worldserver/worldserver --config "$(WORLD_TEST_CONF)"

host-world-stonecore-5n:
	$(MAKE) host-world BOTWORLD_ENABLE=1 BOTWORLD_AUTOSTART=1 BOTWORLD_RUNTIME_PROFILE=stonecore_5n BOTPOLICYMODEL_ENABLE=0

host-world-blackwing-descent-10n:
	$(MAKE) host-world BOTWORLD_ENABLE=1 BOTWORLD_AUTOSTART=1 BOTWORLD_RUNTIME_PROFILE=blackwing_descent_10n BOTPOLICYMODEL_ENABLE=0

host-world-botexp-small:
	$(MAKE) host-world BOTWORLD_ENABLE=1 BOTWORLD_AUTOSTART=1 BOTWORLD_AUTOSTART_RECORDING=1 BOTWORLD_RECORDING_WINDOW_MINUTES=15 BOTWORLD_TARGET_POPULATION=5 BOTWORLD_SPAWN_MODE=resume_or_race_start BOTWORLD_ALLOW_CONFIGURED_CENTER_FALLBACK=0 BOTWORLD_USE_SAVED_POSITION=1 BOTWORLD_QUEST_FIRST=1 BOTWORLD_ALLOW_GRINDING=0 BOTWORLD_GRIND_ONLY_WHEN_NO_QUEST_AVAILABLE=1 BOTPOLICYMODEL_ENABLE=0

host-world-botexp:
	$(MAKE) host-world BOTWORLD_ENABLE=1 BOTWORLD_AUTOSTART=1 BOTWORLD_AUTOSTART_RECORDING=1 BOTWORLD_RECORDING_WINDOW_MINUTES=$(BOTWORLD_RECORDING_WINDOW_MINUTES) BOTWORLD_TARGET_POPULATION=$(BOTWORLD_TARGET_POPULATION) BOTWORLD_SPAWN_MODE=resume_or_race_start BOTWORLD_ALLOW_CONFIGURED_CENTER_FALLBACK=0 BOTWORLD_USE_SAVED_POSITION=1 BOTPOLICYMODEL_ENABLE=0

host-world-botexp-real:
	$(MAKE) host-world BOTWORLD_ENABLE=1 BOTWORLD_AUTOSTART=1 BOTWORLD_AUTOSTART_RECORDING=1 BOTWORLD_RECORDING_WINDOW_MINUTES=$(BOTWORLD_RECORDING_WINDOW_MINUTES) BOTWORLD_TARGET_POPULATION=$(BOTWORLD_TARGET_POPULATION) BOTWORLD_SPAWN_MODE=resume_or_race_start BOTWORLD_ALLOW_CONFIGURED_CENTER_FALLBACK=0 BOTWORLD_USE_SAVED_POSITION=1 BOTPOLICYMODEL_ENABLE=0

host-world-botexp-watch:
	$(MAKE) host-world BOTWORLD_ENABLE=1 BOTWORLD_AUTOSTART=1 BOTWORLD_RUNTIME_PROFILE=watch_near_player BOTWORLD_AUTOSTART_RECORDING=1 BOTWORLD_RECORDING_WINDOW_MINUTES=$(BOTWORLD_RECORDING_WINDOW_MINUTES) BOTWORLD_TARGET_POPULATION=$(BOTWORLD_TARGET_POPULATION) BOTWORLD_SPAWN_MODE=near_player BOTWORLD_ALLOW_CONFIGURED_CENTER_FALLBACK=0 BOTWORLD_USE_SAVED_POSITION=0 BOTPOLICYMODEL_ENABLE=0

host-world-botexp-shadow:
	$(MAKE) host-world BOTWORLD_ENABLE=1 BOTWORLD_AUTOSTART=1 BOTWORLD_AUTOSTART_RECORDING=1 BOTWORLD_RECORDING_WINDOW_MINUTES=$(BOTWORLD_RECORDING_WINDOW_MINUTES) BOTWORLD_TARGET_POPULATION=$(BOTWORLD_TARGET_POPULATION) BOTWORLD_SPAWN_MODE=resume_or_race_start BOTWORLD_ALLOW_CONFIGURED_CENTER_FALLBACK=0 BOTWORLD_USE_SAVED_POSITION=1 BOTPOLICYMODEL_ENABLE=1 BOTPOLICYMODEL_MODE=shadow BOTPOLICYMODEL_VERSION=$(MODEL_VERSION) BOTPOLICYMODEL_FAIL_CLOSED=1

bot-live-validate: local-configure db test-configs
	cmake --build $(BUILD_DIR) --target worldserver -j"$(JOBS)"
	pixi run python -m tools.bot_ml.run_live_bot_validation --worldserver "$(BUILD_DIR)/src/server/worldserver/worldserver" --config "$(WORLD_TEST_CONF)" --output-dir "$(LIVE_VALIDATION_DIR)"

bot-ml-export:
	pixi run python -m tools.bot_ml.export_bot_dataset --database-url "$(CHARACTER_DB_URL)" --output-dir "$(BOT_DATASET_DIR)/raw"

bot-ml-build-dataset:
	pixi run python -m tools.bot_ml.build_decision_dataset --input-dir "$(BOT_DATASET_DIR)/raw" --output "$(BOT_DATASET_DIR)/decision_dataset.jsonl" --manifest "$(BOT_DATASET_DIR)/decision_dataset_manifest.json" --outcome-window-sec "$(OUTCOME_WINDOW_SEC)" --death-window-sec "$(DEATH_WINDOW_SEC)" --stuck-window-sec "$(STUCK_WINDOW_SEC)" --quest-window-sec "$(QUEST_WINDOW_SEC)" --reward-window-sec "$(REWARD_WINDOW_SEC)"

bot-ml-train:
	pixi run python -m tools.bot_ml.train_policy_model --dataset "$(BOT_DATASET_DIR)/decision_dataset.jsonl" --model-dir "$(BOT_MODEL_DIR)" --model-version "$(MODEL_VERSION)" --backend xgboost

bot-ml-evaluate:
	pixi run python -m tools.bot_ml.evaluate_policy_model --dataset "$(BOT_DATASET_DIR)/decision_dataset.jsonl" --model "$(BOT_MODEL_DIR)/$(MODEL_VERSION)/model.json" --metrics "$(BOT_EVAL_DIR)/$(MODEL_VERSION)_metrics.json" --diagnostics "$(BOT_EVAL_DIR)/$(MODEL_VERSION)_diagnostics.json"

bot-ml-register:
	pixi run python -m tools.bot_ml.register_policy_model --model "$(BOT_MODEL_DIR)/$(MODEL_VERSION)/model.json" --metrics "$(BOT_EVAL_DIR)/$(MODEL_VERSION)_metrics.json" --diagnostics "$(BOT_EVAL_DIR)/$(MODEL_VERSION)_diagnostics.json" --sql-output "$(BOT_MODEL_DIR)/$(MODEL_VERSION)/register_model.sql"

bot-ml-full: bot-ml-export bot-ml-build-dataset
	pixi run python -m tools.bot_ml.validate_data_quality --dataset "$(BOT_DATASET_DIR)/decision_dataset.jsonl" --report "$(BOT_DATASET_DIR)/data_quality.json"
	$(MAKE) bot-ml-train MODEL_VERSION=$(MODEL_VERSION) BOT_DATASET_DIR=$(BOT_DATASET_DIR) BOT_MODEL_DIR=$(BOT_MODEL_DIR)
	$(MAKE) bot-ml-evaluate MODEL_VERSION=$(MODEL_VERSION) BOT_DATASET_DIR=$(BOT_DATASET_DIR) BOT_MODEL_DIR=$(BOT_MODEL_DIR) BOT_EVAL_DIR=$(BOT_EVAL_DIR)
	$(MAKE) bot-ml-register MODEL_VERSION=$(MODEL_VERSION) BOT_MODEL_DIR=$(BOT_MODEL_DIR) BOT_EVAL_DIR=$(BOT_EVAL_DIR)

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
