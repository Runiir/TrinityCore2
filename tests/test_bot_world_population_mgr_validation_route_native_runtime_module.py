"""Source contracts for native route interaction, completion and transport modules."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"


def _source(name: str) -> str:
    return (BOTS / name).read_text(encoding="utf-8")


def _code(text: str) -> str:
    text = re.sub(r"//.*", "", text)
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


OWNED_OR_NEW = (
    "BotValidationRouteNativeJson.h",
    "BotValidationRouteNativeContract.h",
    "BotValidationRouteNativeLogic.h",
    "BotWorldPopulationMgrValidationRouteNativeRuntime.h",
    "BotWorldPopulationMgrValidationRouteNativeRuntime.cpp",
    "BotWorldPopulationMgrValidationRouteBoardingAction.h",
    "BotWorldPopulationMgrValidationRouteBoardingAction.cpp",
    "BotWorldPopulationMgrValidationRouteManifestFields.h",
    "BotWorldPopulationMgrValidationRouteManifest.cpp",
    "BotWorldPopulationMgrValidationRouteRuntime.cpp",
    "BotWorldPopulationMgrValidationRouteTerminalArrival.cpp",
    "BotWorldPopulationMgrValidationRouteTerminalArrival.h",
    "BotWorldPopulationMgrUpdateBotKernelPreparation.cpp",
    "BotWorldPopulationMgrNativeAction.cpp",
    "BotNativeActionIntent.h",
    "BotWorldPopulationMgrEncounterBlackboard.cpp",
)


def test_route_modules_stay_below_the_module_size_limit() -> None:
    for name in OWNED_OR_NEW:
        assert len(_source(name).splitlines()) < 1000, name


def test_kernel_preparation_delegates_native_contracts_to_the_adapter() -> None:
    preparation = _source("BotWorldPopulationMgrUpdateBotKernelPreparation.cpp")
    assert '#include "Bots/BotWorldPopulationMgrValidationRouteNativeRuntime.h"' in preparation
    assert "NativeRoute::Run(nativeInput, nativeCallbacks).OwnsNode" in preparation
    assert "routeNode.NativeContract.Declared()" in preparation
    assert "FailValidationAttemptOnce(context.State, context.Bot, reason," in preparation
    assert '"native_postcondition"' in preparation
    # The lowest-GUID election now lives in the pure owner logic.
    assert "electedInteractor" not in preparation
    assert "AI()->DoAction" not in _code(preparation)


def test_native_runtime_submits_only_player_intents() -> None:
    runtime = _code(_source("BotWorldPopulationMgrValidationRouteNativeRuntime.cpp"))
    for intent in (
        "BotNativeAction::GameObjectUse", "BotNativeAction::GossipOpen",
        "BotNativeAction::GossipSelect", "BotNativeAction::SpellClick",
        "BotNativeAction::VehicleEnter", "BotNativeAction::AreaTrigger",
        "BotNativeAction::TransportBoard", "BotNativeAction::TransportLeave",
        "BotNativeAction::Move",
    ):
        assert intent in runtime, intent
    assert "resolved.Ambiguous = candidates.size() > 1" in runtime
    for forbidden in (
        "TeleportTo(", "NearTeleportTo(", "Relocate(", "UpdatePosition(",
        "AddPassenger(", "SetTransport(", "SetData(", "DoAction(",
        "SummonCreature(", "SetGoState(", "Despawn", "CastSpell(",
    ):
        assert forbidden not in runtime, forbidden


def test_boarding_executor_reports_positions_through_native_handlers() -> None:
    boarding = _code(_source("BotWorldPopulationMgrValidationRouteBoardingAction.cpp"))
    assert "HandleSetActiveMoverOpcode(request)" in boarding
    assert "HandleMovementOpcode(MSG_MOVE_HEARTBEAT, report)" in boarding
    assert "HandleSpellClick(click)" in boarding
    assert "HandleChangeSeatsOnControlledVehicle(request)" in boarding
    assert "CMSG_REQUEST_VEHICLE_SWITCH_SEAT" in boarding
    # The reported position is the bot's own current position.
    assert "info.pos.Relocate(bot->GetPositionX(), bot->GetPositionY(),\n        bot->GetPositionZ(), bot->GetOrientation());" in boarding
    assert "InsideFootprint({ x, y, z, true }, box" in boarding
    assert "native_transport_board_outside_footprint" in boarding
    assert "native_transport_leave_no_static_floor" in boarding
    assert "boarded->GetTransportGUID() == object->GetGUID()" in boarding
    for forbidden in (
        "->TeleportTo(", "->NearTeleportTo(", "->UpdatePosition(", "->AddPassenger(",
        "->SetTransport(", "->EnterVehicle(", "->_EnterVehicle(", "->ChangeSeat(",
        "->AddVehiclePassenger(", "->GetMotionMaster(", "->SetGoState(", "->Relocate(",
    ):
        assert forbidden not in boarding, forbidden


def test_native_action_splits_vehicle_seats_and_checks_object_reach() -> None:
    native = _source("BotWorldPopulationMgrNativeAction.cpp")
    intents = _source("BotNativeActionIntent.h")
    assert "else if constexpr (std::is_same_v<T, BotNativeAction::VehicleEnter>)" in native
    assert "|| std::is_same_v<T, BotNativeAction::VehicleEnter>)" not in native
    assert "BotValidationRouteBoardingAction::EnterVehicle(bot, action)" in native
    assert "BotValidationRouteBoardingAction::BoardTransport(bot, action)" in native
    assert "BotValidationRouteBoardingAction::LeaveTransport(bot, action)" in native
    assert "usable->IsAtInteractDistance(bot)" in native
    assert '"native_gameobject_use_out_of_range"' in native
    # SpellClick (used by Magmaw's head mount) keeps its original executor.
    spellclick = native[native.index("std::is_same_v<T, BotNativeAction::SpellClick>)"):]
    spellclick = spellclick[:spellclick.index("else if constexpr")]
    assert "HandleSpellClick(click)" in spellclick
    assert "native_spellclick_out_of_range" in spellclick
    assert "struct TransportBoard { ObjectGuid Transport; float FootprintMarginYards = 0.5f; };" in intents
    assert "VehicleExit, PetCommand, UseItem, ReleaseSpirit, ReclaimCorpse,\n    TransportBoard, TransportLeave>;" in intents


def test_manifest_parses_native_contracts_structurally_and_fail_closed() -> None:
    manifest = _source("BotWorldPopulationMgrValidationRouteManifest.cpp")
    assert 'BotValidationRouteNativeJson::TopLevelString(routeJson,\n            "kind", ExtractJsonStringField(routeJson, "kind"))' in manifest
    for marker in (
        "NativeRoute::ParseInteraction(object, out)",
        "NativeRoute::ParseCompletion(object, out)",
        "NativeRoute::ParseTransport(object, out)",
        "NativeRoute::ValidateNodeShape(",
        '"native_transport_contract_invalid:"',
        '"native_route_contract_shape_invalid:"',
        "node.NativeCompletionKind = node.NativeContract.Completion.KindName;",
    ):
        assert marker in manifest, marker
    # Unevaluated kinds are no longer accepted anywhere in the runtime.
    for retired in ("intro_complete_and_elevator_ready", "player_in_nefarian_arena"):
        for name in OWNED_OR_NEW:
            assert retired not in _code(_source(name)), (retired, name)


def test_blackboard_keeps_contract_named_creatures_observable() -> None:
    blackboard = _source("BotWorldPopulationMgrEncounterBlackboard.cpp")
    assert "BotValidationRouteNative::ObservedCreatureEntries(routeNode.NativeContract)" in blackboard
    assert "std::binary_search(nativeRouteObservedEntries.begin()," in blackboard
