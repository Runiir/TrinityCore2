# 4.4.2 player interaction checklist

916 operation contracts across 45 families. 444 have a qualified fixture variant; the rest remain pending.

A checked box means the linked evidence qualifies the stated fixture variant. It does not close other content, class, map, permission, persistence or failure variants. Opening a panel qualifies only opening that panel.

Player interaction families and every installed binding. Per-spell/item/quest/encounter variants are expanded by the native content census.

New regression trials use code-controlled ordinary keyboard/mouse inputs under the current AGENTS.md. Historical desktop-isolation evidence retains its actual Laya identity. Controller/model identities are recorded per episode. Screenshots and normal addon-visible state are retained. Fixture setup, cleanup and outcome checks are recorded separately. Input, observer and protocol failures have distinct evidence.

Each successful mutation needs its native or local saved-state oracle and cleanup. Variants include class, race, faction, account versus character, solo versus group, combat versus idle, dead versus alive, zones, permissions and failure paths. Content IDs come from the existing content census.

## lifecycle

Fixture: `disposable_account`.

- [x] `lifecycle.select_realm` (qualified variant; [evidence](#stock_lab_realm_reconnect))
- [ ] `lifecycle.select_character`
- [ ] `lifecycle.create_character`
- [ ] `lifecycle.appearance_preview`
- [ ] `lifecycle.name_validation`
- [ ] `lifecycle.delete_character`
- [x] `lifecycle.enter_world` (qualified variant; [evidence](#logout_reentry))
- [x] `lifecycle.logout_cancel` (qualified variant; [evidence](#logout_reentry))
- [x] `lifecycle.logout_confirm` (qualified variant; [evidence](#logout_reentry))
- [x] `lifecycle.reconnect` (qualified variant; [evidence](#stock_lab_realm_reconnect))
- [ ] `lifecycle.launcher_login`
- [ ] `lifecycle.password_login`
- [ ] `lifecycle.addon_enable`
- [ ] `lifecycle.addon_disable`
- [ ] `lifecycle.character_rename_if_available`

## character

Fixture: `equipped_character`.

- [x] `character.open` (qualified variant; [evidence](#panel_visibility))
- [x] `character.close` (qualified variant; [evidence](#panel_visibility))
- [x] `character.stats` (qualified variant; [evidence](#equipment))
- [x] `character.equipment_tooltips` (qualified variant; [evidence](#stock_equipped_item_tooltip_identity))
- [x] `character.compare_items` (qualified variant; [evidence](#stock_owned_sword_comparison))
- [x] `character.equip` (qualified variant; [evidence](#equipment))
- [x] `character.unequip` (qualified variant; [evidence](#equipment))
- [x] `character.weapon_swap` (qualified variant; [evidence](#stock_twohand_weapon_swap))
- [x] `character.display_helm` (qualified variant; [evidence](#stock_geared_visibility_roundtrip))
- [x] `character.display_cloak` (qualified variant; [evidence](#stock_geared_visibility_roundtrip))
- [x] `character.equipment_set_create` (qualified variant; [evidence](#stock_equipment_set_creation))
- [x] `character.equipment_set_save` (qualified variant; [evidence](#stock_equipment_set_roundtrip))
- [x] `character.equipment_set_equip` (qualified variant; [evidence](#stock_equipment_set_roundtrip))
- [x] `character.equipment_set_delete` (qualified variant; [evidence](#stock_equipment_set_roundtrip))
- [ ] `character.titles`
- [ ] `character.select_title`

## reputation

Fixture: `known_factions`.

- [x] `reputation.open` (qualified variant; [evidence](#panel_visibility))
- [x] `reputation.close` (qualified variant; [evidence](#panel_visibility))
- [x] `reputation.expand` (qualified variant; [evidence](#reputation_standing_watch_headers))
- [x] `reputation.collapse` (qualified variant; [evidence](#reputation_standing_watch_headers))
- [x] `reputation.inspect_standing` (qualified variant; [evidence](#reputation_standing_watch_headers))
- [x] `reputation.at_war_toggle` (qualified variant; [evidence](#reputation_atwar_neutral_roundtrip))
- [x] `reputation.inactive_toggle` (qualified variant; [evidence](#reputation_inactive_roundtrip))
- [x] `reputation.watched_faction` (qualified variant; [evidence](#reputation_standing_watch_headers))
- [x] `reputation.gain_standing` (qualified variant; [evidence](#reputation_earned_positive_negative))
- [x] `reputation.lose_standing` (qualified variant; [evidence](#reputation_earned_positive_negative))
- [x] `reputation.persist` (qualified variant; [evidence](#reputation_watched_reload))

## currency

Fixture: `known_currencies`.

- [x] `currency.open` (qualified variant; [evidence](#currency_stock_catalog))
- [x] `currency.close` (qualified variant; [evidence](#currency_stock_catalog))
- [x] `currency.expand` (qualified variant; [evidence](#currency_stock_catalog))
- [x] `currency.collapse` (qualified variant; [evidence](#currency_stock_catalog))
- [x] `currency.inspect_currency` (qualified variant; [evidence](#currency_stock_catalog))
- [x] `currency.backpack_toggle` (qualified variant; [evidence](#currency_honor_backpack_roundtrip))
- [x] `currency.unused_toggle` (qualified variant; [evidence](#currency_honor_unused_roundtrip))
- [ ] `currency.gain_currency`
- [x] `currency.spend_currency` (qualified variant; [evidence](#archaeology_earned_fragment_solve))
- [ ] `currency.weekly_cap`
- [x] `currency.persist` (qualified variant; [evidence](#currency_honor_watch_reload))

## spellbook

Fixture: `class_variants`.

- [x] `spellbook.open` (qualified variant; [evidence](#panel_visibility))
- [x] `spellbook.close` (qualified variant; [evidence](#panel_visibility))
- [x] `spellbook.general_tab` (qualified variant; [evidence](#stock_spellbook_navigation))
- [x] `spellbook.class_tab` (qualified variant; [evidence](#stock_spellbook_navigation))
- [x] `spellbook.pet_tab` (qualified variant; [evidence](#trained_imp_pet_spellbook_tab))
- [x] `spellbook.professions_tab` (qualified variant; [evidence](#stock_spellbook_profession_catalog))
- [x] `spellbook.next_page` (qualified variant; [evidence](#stock_spellbook_navigation))
- [x] `spellbook.previous_page` (qualified variant; [evidence](#stock_spellbook_navigation))
- [x] `spellbook.spell_tooltip` (qualified variant; [evidence](#stock_spellbook_navigation))
- [x] `spellbook.passive_tooltip` (qualified variant; [evidence](#stock_spellbook_navigation))
- [x] `spellbook.drag_to_bar` (qualified variant; [evidence](#stock_spellbook_action_roundtrip))
- [x] `spellbook.cast_spell` (qualified variant; [evidence](#stock_spellbook_battle_shout_cast))
- [ ] `spellbook.learn_spell`
- [ ] `spellbook.unlearn_spell`
- [ ] `spellbook.rank_resolution`

## talents

Fixture: `class_variants`.

- [x] `talents.open` (qualified variant; [evidence](#panel_visibility))
- [x] `talents.close` (qualified variant; [evidence](#panel_visibility))
- [x] `talents.specialization_preview` (qualified variant; [evidence](#warrior_talent_allocation))
- [x] `talents.choose_specialization` (qualified variant; [evidence](#warrior_talent_allocation))
- [x] `talents.spend_point` (qualified variant; [evidence](#warrior_talent_allocation))
- [ ] `talents.reset_talents`
- [ ] `talents.dual_spec`
- [ ] `talents.switch_spec`
- [ ] `talents.inspect_talents`
- [x] `talents.glyph_open` (qualified variant; [evidence](#glyph_socket_panel))
- [x] `talents.glyph_catalog` (qualified variant; [evidence](#warrior_glyph_catalog_search))
- [x] `talents.glyph_search` (qualified variant; [evidence](#warrior_glyph_catalog_search))
- [x] `talents.glyph_clear_search` (qualified variant; [evidence](#warrior_glyph_catalog_search))
- [x] `talents.glyph_filter_known` (qualified variant; [evidence](#glyph_learned_filters))
- [x] `talents.glyph_filter_unknown` (qualified variant; [evidence](#glyph_learned_filters))
- [x] `talents.glyph_filter_prime` (qualified variant; [evidence](#glyph_type_filters))
- [x] `talents.glyph_filter_major` (qualified variant; [evidence](#glyph_type_filters))
- [x] `talents.glyph_filter_minor` (qualified variant; [evidence](#glyph_type_filters))
- [x] `talents.glyph_learn` (qualified variant; [evidence](#glyph_book_learning))
- [x] `talents.glyph_apply` (qualified variant; [evidence](#glyph_minor_application))
- [ ] `talents.glyph_replace`
- [x] `talents.glyph_remove` (qualified variant; [evidence](#glyph_minor_removal))
- [x] `talents.glyph_tooltip` (qualified variant; [evidence](#stock_learned_battle_glyph_tooltip))
- [x] `talents.persist` (qualified variant; [evidence](#warrior_talent_allocation))

## professions

Fixture: `profession_variants`.

- [x] `professions.open` (qualified variant; [evidence](#panel_visibility))
- [x] `professions.close` (qualified variant; [evidence](#panel_visibility))
- [x] `professions.primary_one` (qualified variant; [evidence](#profession_catalogs))
- [x] `professions.primary_two` (qualified variant; [evidence](#profession_catalogs))
- [x] `professions.cooking` (qualified variant; [evidence](#profession_catalogs))
- [x] `professions.first_aid` (qualified variant; [evidence](#profession_catalogs))
- [ ] `professions.fishing`
- [x] `professions.archaeology` (qualified variant; [evidence](#profession_catalogs))
- [x] `professions.recipe_list` (qualified variant; [evidence](#crafting))
- [x] `professions.recipe_search` (qualified variant; [evidence](#crafting))
- [x] `professions.recipe_filter` (qualified variant; [evidence](#owned_alchemy_makeable_filter))
- [x] `professions.recipe_tooltip` (qualified variant; [evidence](#owned_alchemy_recipe_result_tooltip))
- [x] `professions.recipe_select` (qualified variant; [evidence](#crafting))
- [x] `professions.reagent_tooltip` (qualified variant; [evidence](#owned_alchemy_recipe_reagent_tooltips))
- [x] `professions.craft_one` (qualified variant; [evidence](#crafting))
- [x] `professions.craft_multiple` (qualified variant; [evidence](#crafting))
- [ ] `professions.cancel_craft`
- [x] `professions.craft_result` (qualified variant; [evidence](#crafting))
- [ ] `professions.skill_gain`
- [ ] `professions.learn_recipe`
- [ ] `professions.unlearn_profession`
- [ ] `professions.profession_cooldown`
- [ ] `professions.enchant_item`
- [ ] `professions.enchant_trade`
- [ ] `professions.socket_item`
- [ ] `professions.gather_node`
- [ ] `professions.gather_loot`
- [ ] `professions.persist`

## archaeology

Fixture: `digsite_variants`.

- [x] `archaeology.open` (qualified variant; [evidence](#profession_catalogs))
- [x] `archaeology.close` (qualified variant; [evidence](#archaeology_current_draenei_project))
- [x] `archaeology.race_select` (qualified variant; [evidence](#archaeology_current_draenei_project))
- [x] `archaeology.project_select` (qualified variant; [evidence](#archaeology_current_draenei_project))
- [x] `archaeology.project_tooltip` (qualified variant; [evidence](#archaeology_completed_project_tooltip))
- [x] `archaeology.survey` (qualified variant; [evidence](#archaeology_loop))
- [x] `archaeology.cast_bar` (qualified variant; [evidence](#archaeology_stationary_solve_cast_bar))
- [x] `archaeology.telescope_direction` (qualified variant; [evidence](#archaeology_loop))
- [x] `archaeology.distance_lantern` (qualified variant; [evidence](#archaeology_loop))
- [x] `archaeology.approach_find` (qualified variant; [evidence](#archaeology_loop))
- [x] `archaeology.loot_find` (qualified variant; [evidence](#archaeology_loop))
- [x] `archaeology.solve_project` (qualified variant; [evidence](#archaeology_earned_fragment_solve))
- [x] `archaeology.use_keystone` (qualified variant; [evidence](#archaeology_existing_keystone_solve))
- [x] `archaeology.project_completion` (qualified variant; [evidence](#archaeology_earned_fragment_solve))
- [x] `archaeology.site_completion` (qualified variant; [evidence](#archaeology_loop))
- [x] `archaeology.site_rotation` (qualified variant; [evidence](#archaeology_loop))
- [x] `archaeology.continent_map` (qualified variant; [evidence](#stock_owned_continent_digsite_overlay))
- [ ] `archaeology.fragments_cap`
- [x] `archaeology.persist` (qualified variant; [evidence](#archaeology_earned_reload_persistence))

## bags

Fixture: `inventory_items`.

- [x] `bags.open_all` (qualified variant; [evidence](#panel_visibility))
- [x] `bags.close_all` (qualified variant; [evidence](#panel_visibility))
- [x] `bags.backpack` (qualified variant; [evidence](#panel_visibility))
- [x] `bags.bag_one` (qualified variant; [evidence](#panel_visibility))
- [x] `bags.bag_two` (qualified variant; [evidence](#panel_visibility))
- [x] `bags.bag_three` (qualified variant; [evidence](#panel_visibility))
- [x] `bags.bag_four` (qualified variant; [evidence](#panel_visibility))
- [ ] `bags.combined_bags_toggle`
- [ ] `bags.sort`
- [ ] `bags.search`
- [ ] `bags.quality_filter`
- [x] `bags.item_tooltip` (qualified variant; [evidence](#owned_backpack_tooltip_and_comparison))
- [x] `bags.compare_tooltip` (qualified variant; [evidence](#owned_backpack_tooltip_and_comparison))
- [x] `bags.item_link` (qualified variant; [evidence](#owned_pending_backpack_item_link))
- [x] `bags.move_item` (qualified variant; [evidence](#inventory_movement))
- [ ] `bags.swap_item`
- [x] `bags.split_stack` (qualified variant; [evidence](#stack_split_merge))
- [x] `bags.merge_stack` (qualified variant; [evidence](#stack_split_merge))
- [ ] `bags.use_item`
- [x] `bags.equip_item` (qualified variant; [evidence](#equipment))
- [x] `bags.unequip_item` (qualified variant; [evidence](#equipment))
- [ ] `bags.destroy_confirm`
- [ ] `bags.destroy_cancel`
- [ ] `bags.bag_replace`
- [ ] `bags.keyring_if_available`
- [ ] `bags.cooldown_display`
- [ ] `bags.full_bag_error`
- [ ] `bags.locked_item_error`
- [ ] `bags.persist`

## bank

Fixture: `banker_inventory`.

- [x] `bank.open` (qualified variant; [evidence](#bank))
- [x] `bank.close` (qualified variant; [evidence](#bank))
- [x] `bank.deposit` (qualified variant; [evidence](#bank))
- [x] `bank.withdraw` (qualified variant; [evidence](#bank))
- [ ] `bank.swap`
- [ ] `bank.split`
- [ ] `bank.buy_slot`
- [ ] `bank.equip_bank_bag`
- [ ] `bank.bank_bag_open`
- [ ] `bank.reagent_bank_if_available`
- [ ] `bank.guild_bank_link`
- [ ] `bank.persist`

## merchant

Fixture: `merchant_inventory`.

- [x] `merchant.open` (qualified variant; [evidence](#merchant))
- [x] `merchant.close` (qualified variant; [evidence](#merchant))
- [ ] `merchant.browse_page`
- [ ] `merchant.buy_one`
- [x] `merchant.buy_stack` (qualified variant; [evidence](#purchase))
- [x] `merchant.sell` (qualified variant; [evidence](#merchant))
- [x] `merchant.buyback` (qualified variant; [evidence](#merchant))
- [ ] `merchant.repair_one`
- [x] `merchant.repair_all` (qualified variant; [evidence](#repair_all))
- [ ] `merchant.insufficient_money`
- [ ] `merchant.unavailable_stock`
- [ ] `merchant.currency_cost`
- [ ] `merchant.reputation_discount`
- [ ] `merchant.persist`

## trainer

Fixture: `trainer_skills`.

- [x] `trainer.open` (qualified variant; [evidence](#trainer))
- [x] `trainer.close` (qualified variant; [evidence](#trainer))
- [ ] `trainer.filter_available`
- [ ] `trainer.filter_unavailable`
- [x] `trainer.filter_known` (qualified variant; [evidence](#trainer_known_filter))
- [ ] `trainer.skill_tooltip`
- [x] `trainer.learn_skill` (qualified variant; [evidence](#trainer))
- [ ] `trainer.learn_rank`
- [ ] `trainer.insufficient_money`
- [ ] `trainer.prerequisite_error`
- [ ] `trainer.profession_limit`
- [ ] `trainer.persist`

## quests

Fixture: `quest_variants`.

- [x] `quests.open_log` (qualified variant; [evidence](#panel_visibility))
- [x] `quests.close_log` (qualified variant; [evidence](#panel_visibility))
- [x] `quests.select` (qualified variant; [evidence](#quest_log))
- [x] `quests.expand_zone` (qualified variant; [evidence](#quest_log))
- [x] `quests.collapse_zone` (qualified variant; [evidence](#manual_quest_controls))
- [x] `quests.details` (qualified variant; [evidence](#quest_log))
- [ ] `quests.track`
- [ ] `quests.untrack`
- [x] `quests.abandon_cancel` (qualified variant; [evidence](#manual_quest_controls))
- [x] `quests.abandon_confirm` (qualified variant; [evidence](#quest_log))
- [ ] `quests.share`
- [x] `quests.accept` (qualified variant; [evidence](#manual_quest_controls))
- [x] `quests.decline` (qualified variant; [evidence](#manual_quest_controls))
- [x] `quests.progress` (qualified variant; [evidence](#ordinary_quest_kill_progress))
- [x] `quests.complete` (qualified variant; [evidence](#ordinary_quest_melee_completion))
- [x] `quests.choose_reward` (qualified variant; [evidence](#earned_quest_reward))
- [x] `quests.reward_item` (qualified variant; [evidence](#earned_quest_reward))
- [x] `quests.reward_money` (qualified variant; [evidence](#earned_quest_reward))
- [ ] `quests.escort`
- [ ] `quests.timed`
- [ ] `quests.daily`
- [ ] `quests.repeatable`
- [ ] `quests.auto_accept`
- [ ] `quests.auto_complete`
- [ ] `quests.unavailable_prerequisite`
- [x] `quests.persist` (qualified variant; [evidence](#quest_full_session_persistence))
- [x] `quests.giver_available_marker` (qualified variant; [evidence](#available_quest_marker))
- [x] `quests.giver_trivial_marker` (qualified variant; [evidence](#trivial_quest_marker_tracked))
- [ ] `quests.giver_incomplete_marker`
- [x] `quests.giver_complete_marker` (qualified variant; [evidence](#ordinary_quest_melee_completion))
- [ ] `quests.giver_repeatable_marker`
- [ ] `quests.giver_unavailable_marker`

## map

Fixture: `map_variants`.

- [x] `map.open` (qualified variant; [evidence](#panel_visibility))
- [x] `map.close` (qualified variant; [evidence](#panel_visibility))
- [x] `map.continent` (qualified variant; [evidence](#stock_zone_continent_navigation))
- [x] `map.zone` (qualified variant; [evidence](#stock_zone_continent_navigation))
- [ ] `map.subzone`
- [x] `map.zoom_in` (qualified variant; [evidence](#stock_zone_continent_navigation))
- [x] `map.zoom_out` (qualified variant; [evidence](#stock_zone_continent_navigation))
- [ ] `map.pan`
- [ ] `map.quest_pin`
- [ ] `map.quest_details`
- [ ] `map.quest_route`
- [x] `map.digsite_overlay` (qualified variant; [evidence](#stock_owned_continent_digsite_overlay))
- [ ] `map.taxi_overlay`
- [ ] `map.dungeon_floor`
- [x] `map.coordinates` (qualified variant; [evidence](#stock_player_planar_map_coordinates))
- [x] `map.player_position` (qualified variant; [evidence](#stock_player_planar_map_coordinates))
- [x] `map.tracking_menu` (qualified variant; [evidence](#minimap_quest_tracking_controls))
- [x] `map.world_map_binding` (qualified variant; [evidence](#stock_zone_continent_navigation))
- [x] `map.minimap_zoom` (qualified variant; [evidence](#stock_reversible_minimap_zoom))
- [x] `map.minimap_tracking` (qualified variant; [evidence](#minimap_quest_tracking_controls))
- [ ] `map.minimap_calendar`
- [ ] `map.minimap_clock`
- [ ] `map.minimap_mail`
- [ ] `map.minimap_battleground`

## achievements

Fixture: `achievement_variants`.

- [x] `achievements.open` (qualified variant; [evidence](#panel_visibility))
- [x] `achievements.close` (qualified variant; [evidence](#panel_visibility))
- [x] `achievements.category` (qualified variant; [evidence](#stock_achievement_selection_tracking))
- [x] `achievements.achievement` (qualified variant; [evidence](#stock_achievement_selection_tracking))
- [ ] `achievements.search`
- [ ] `achievements.tooltip`
- [x] `achievements.track` (qualified variant; [evidence](#stock_achievement_selection_tracking))
- [x] `achievements.untrack` (qualified variant; [evidence](#stock_achievement_selection_tracking))
- [ ] `achievements.compare`
- [ ] `achievements.criteria_progress`
- [ ] `achievements.earned_notification`
- [x] `achievements.statistics` (qualified variant; [evidence](#panel_visibility))
- [ ] `achievements.persist`

## collections

Fixture: `mount_pet_variants`.

- [x] `collections.open` (qualified variant; [evidence](#panel_visibility))
- [x] `collections.close` (qualified variant; [evidence](#panel_visibility))
- [ ] `collections.mount_tab`
- [ ] `collections.mount_search`
- [ ] `collections.mount_filter`
- [ ] `collections.mount_preview`
- [ ] `collections.mount_summon`
- [ ] `collections.dismount`
- [ ] `collections.favorite_mount`
- [ ] `collections.ground_mount`
- [ ] `collections.flying_mount`
- [ ] `collections.passenger_mount`
- [ ] `collections.companion_tab`
- [ ] `collections.companion_search`
- [ ] `collections.companion_preview`
- [ ] `collections.companion_summon`
- [ ] `collections.companion_dismiss`
- [ ] `collections.favorite_companion`
- [ ] `collections.pet_battle_if_available`
- [ ] `collections.toy_tab_if_available`
- [ ] `collections.heirloom_tab_if_available`
- [ ] `collections.persist`

## journal

Fixture: `encounter_variants`.

- [x] `journal.open` (qualified variant; [evidence](#panel_visibility))
- [x] `journal.close` (qualified variant; [evidence](#panel_visibility))
- [ ] `journal.expansion`
- [ ] `journal.instance`
- [ ] `journal.difficulty`
- [ ] `journal.boss`
- [ ] `journal.overview`
- [ ] `journal.ability`
- [ ] `journal.loot`
- [ ] `journal.role_filter`
- [ ] `journal.class_filter`
- [ ] `journal.slot_filter`
- [ ] `journal.search`
- [ ] `journal.map_link`
- [ ] `journal.model_preview`

## friends

Fixture: `owned_second_actor`.

- [x] `friends.open` (qualified variant; [evidence](#panel_visibility))
- [x] `friends.close` (qualified variant; [evidence](#panel_visibility))
- [x] `friends.list` (qualified variant; [evidence](#owned_current_offline_friend_and_who_open))
- [x] `friends.add_friend` (qualified variant; [evidence](#party_invitation))
- [x] `friends.online_presence` (qualified variant; [evidence](#owned_friend_presence_whisper))
- [x] `friends.offline_presence` (qualified variant; [evidence](#owned_current_offline_friend_and_who_open))
- [x] `friends.note_edit` (qualified variant; [evidence](#owned_offline_friend_note))
- [x] `friends.note_persist` (qualified variant; [evidence](#owned_offline_friend_note_persistence))
- [x] `friends.remove_friend` (qualified variant; [evidence](#owned_offline_friend_removal_errors))
- [x] `friends.add_ignore` (qualified variant; [evidence](#owned_offline_dwarf_ignore))
- [x] `friends.ignored_chat` (qualified variant; [evidence](#owned_friend_ignored_chat))
- [x] `friends.remove_ignore` (qualified variant; [evidence](#owned_offline_dwarf_ignore))
- [x] `friends.who_open` (qualified variant; [evidence](#owned_current_offline_friend_and_who_open))
- [x] `friends.who_search` (qualified variant; [evidence](#owned_native_who_name_search))
- [x] `friends.whisper` (qualified variant; [evidence](#owned_friend_presence_whisper))
- [x] `friends.self_friend_error` (qualified variant; [evidence](#owned_offline_friend_removal_errors))
- [x] `friends.nonexistent_friend_error` (qualified variant; [evidence](#owned_offline_friend_removal_errors))
- [x] `friends.duplicate_friend_error` (qualified variant; [evidence](#owned_offline_friend_removal_errors))
- [ ] `friends.friend_limit`

## chat

Fixture: `owned_second_actor`.

- [x] `chat.say` (qualified variant; [evidence](#chat))
- [x] `chat.yell` (qualified variant; [evidence](#chat))
- [x] `chat.whisper` (qualified variant; [evidence](#chat))
- [x] `chat.reply` (qualified variant; [evidence](#owned_exact_whisper_reply))
- [x] `chat.party` (qualified variant; [evidence](#owned_party_chat))
- [x] `chat.raid` (qualified variant; [evidence](#chat))
- [x] `chat.raid_warning` (qualified variant; [evidence](#chat))
- [x] `chat.guild` (qualified variant; [evidence](#guild_notes))
- [x] `chat.officer` (qualified variant; [evidence](#guild_notes))
- [x] `chat.channel_join` (qualified variant; [evidence](#owned_native_stock_channel_membership))
- [x] `chat.channel_leave` (qualified variant; [evidence](#owned_native_stock_channel_membership))
- [x] `chat.channel_list` (qualified variant; [evidence](#owned_native_stock_channel_ui_roster))
- [x] `chat.channel_password` (qualified variant; [evidence](#owned_native_channel_password_gate))
- [x] `chat.channel_owner` (qualified variant; [evidence](#owned_native_stock_channel_owner_query))
- [x] `chat.emote` (qualified variant; [evidence](#chat))
- [x] `chat.language_switch` (qualified variant; [evidence](#owned_native_racial_stock_language))
- [x] `chat.combat_log` (qualified variant; [evidence](#owned_native_stock_combat_log_timestamps))
- [x] `chat.chat_settings` (qualified variant; [evidence](#stock_general_say_filter_roundtrip))
- [x] `chat.chat_tab_create` (qualified variant; [evidence](#owned_stock_chat_window_lifecycle))
- [x] `chat.chat_tab_rename` (qualified variant; [evidence](#owned_stock_chat_window_lifecycle))
- [x] `chat.chat_tab_close` (qualified variant; [evidence](#owned_stock_chat_window_lifecycle))
- [x] `chat.font_size` (qualified variant; [evidence](#owned_stock_chat_window_lifecycle))
- [x] `chat.timestamps` (qualified variant; [evidence](#owned_native_stock_combat_log_timestamps))
- [x] `chat.chat_links` (qualified variant; [evidence](#owned_item_link_native_say_delivery))
- [x] `chat.scroll_history` (qualified variant; [evidence](#owned_native_chat_history_scroll))
- [x] `chat.copy_if_available` (qualified variant; [evidence](#owned_player_chat_link_name_copy))
- [x] `chat.mute_voice` (qualified variant; [evidence](#owned_stock_local_voice_self_mute))
- [x] `chat.report_ui_cancel` (qualified variant; [evidence](#owned_player_chat_link_report_cancel))

## party

Fixture: `owned_second_actor`.

- [x] `party.invite` (qualified variant; [evidence](#party_invitation))
- [x] `party.accept` (qualified variant; [evidence](#party_invitation))
- [ ] `party.decline`
- [ ] `party.cancel_pending`
- [ ] `party.duplicate_invite`
- [ ] `party.full_group_error`
- [ ] `party.cross_map_invite`
- [ ] `party.leader_promote`
- [x] `party.role_poll` (qualified variant; [evidence](#roles))
- [x] `party.role_assign` (qualified variant; [evidence](#roles))
- [ ] `party.loot_method`
- [ ] `party.loot_threshold`
- [ ] `party.master_looter`
- [ ] `party.target_marker`
- [ ] `party.ready_check`
- [ ] `party.ready_accept`
- [ ] `party.ready_decline`
- [ ] `party.party_chat`
- [ ] `party.leave`
- [ ] `party.kick`
- [ ] `party.disband`
- [ ] `party.disconnect_rejoin`
- [ ] `party.persist`

## raid

Fixture: `owned_group`.

- [x] `raid.convert_from_party` (qualified variant; [evidence](#group_conversion))
- [x] `raid.convert_to_party` (qualified variant; [evidence](#group_conversion))
- [ ] `raid.raid_panel`
- [x] `raid.roster` (qualified variant; [evidence](#group_roster))
- [x] `raid.roster_health_bars` (qualified variant; [evidence](#group_roster))
- [ ] `raid.subgroup_move`
- [ ] `raid.assistant_promote`
- [ ] `raid.assistant_demote`
- [x] `raid.everyone_assistant` (qualified variant; [evidence](#raid_profiles))
- [x] `raid.frame_lock` (qualified variant; [evidence](#raid_profiles))
- [x] `raid.frame_unlock` (qualified variant; [evidence](#raid_profiles))
- [x] `raid.frame_show` (qualified variant; [evidence](#raid_profiles))
- [x] `raid.frame_hide` (qualified variant; [evidence](#raid_profiles))
- [ ] `raid.main_tank`
- [ ] `raid.main_assist`
- [x] `raid.ready_check` (qualified variant; [evidence](#ready_check))
- [x] `raid.ready_timeout` (qualified variant; [evidence](#ready_timeout))
- [ ] `raid.raid_target`
- [x] `raid.world_marker` (qualified variant; [evidence](#world_markers))
- [x] `raid.clear_marker` (qualified variant; [evidence](#world_markers))
- [x] `raid.raid_warning` (qualified variant; [evidence](#chat))
- [ ] `raid.loot_method`
- [ ] `raid.leave`
- [ ] `raid.kick`
- [ ] `raid.disband`
- [ ] `raid.raid_info`
- [ ] `raid.lockout_extend`
- [ ] `raid.reset_instance`
- [ ] `raid.difficulty_normal`
- [ ] `raid.difficulty_heroic`
- [ ] `raid.raid_size_10`
- [ ] `raid.raid_size_25`

## guild

Fixture: `disposable_guild`.

- [x] `guild.open` (qualified variant; [evidence](#guild_open))
- [ ] `guild.close`
- [x] `guild.roster` (qualified variant; [evidence](#guild_membership))
- [ ] `guild.online_filter`
- [x] `guild.member_detail` (qualified variant; [evidence](#guild_notes))
- [x] `guild.note` (qualified variant; [evidence](#guild_notes))
- [x] `guild.officer_note` (qualified variant; [evidence](#guild_notes))
- [x] `guild.invite` (qualified variant; [evidence](#guild_membership))
- [x] `guild.accept` (qualified variant; [evidence](#guild_membership))
- [x] `guild.decline` (qualified variant; [evidence](#guild_membership))
- [x] `guild.rank_promote` (qualified variant; [evidence](#guild_ranks))
- [x] `guild.rank_demote` (qualified variant; [evidence](#guild_ranks))
- [x] `guild.remove_member` (qualified variant; [evidence](#guild_ranks))
- [ ] `guild.leadership_transfer`
- [x] `guild.motd` (qualified variant; [evidence](#guild_membership))
- [x] `guild.information` (qualified variant; [evidence](#guild_notes))
- [x] `guild.chat` (qualified variant; [evidence](#guild_notes))
- [ ] `guild.permissions`
- [ ] `guild.news`
- [ ] `guild.achievements`
- [ ] `guild.reputation`
- [ ] `guild.rewards`
- [ ] `guild.recruitment`
- [ ] `guild.charter_buy`
- [ ] `guild.charter_sign`
- [ ] `guild.charter_turn_in`
- [x] `guild.leave` (qualified variant; [evidence](#guild_membership))
- [x] `guild.disband` (qualified variant; [evidence](#guild_disband))
- [ ] `guild.persist`

## guild bank

Fixture: `disposable_guild_bank`.

- [ ] `guild_bank.open`
- [ ] `guild_bank.close`
- [ ] `guild_bank.tab_select`
- [ ] `guild_bank.view_item`
- [ ] `guild_bank.deposit`
- [ ] `guild_bank.withdraw`
- [ ] `guild_bank.split_stack`
- [ ] `guild_bank.deposit_money`
- [ ] `guild_bank.withdraw_money`
- [ ] `guild_bank.buy_tab`
- [ ] `guild_bank.tab_name`
- [ ] `guild_bank.tab_icon`
- [ ] `guild_bank.tab_text`
- [ ] `guild_bank.log_view`
- [ ] `guild_bank.permissions_error`
- [ ] `guild_bank.persist`

## trade

Fixture: `owned_second_actor`.

- [x] `trade.request` (qualified variant; [evidence](#trade_roundtrip))
- [x] `trade.accept` (qualified variant; [evidence](#trade_roundtrip))
- [x] `trade.cancel` (qualified variant; [evidence](#trade_cancel))
- [x] `trade.offer_item` (qualified variant; [evidence](#trade_roundtrip))
- [ ] `trade.remove_item`
- [x] `trade.offer_stack` (qualified variant; [evidence](#trade_roundtrip))
- [ ] `trade.offer_money`
- [ ] `trade.nontraded_item`
- [ ] `trade.enchant_nontraded`
- [x] `trade.confirm` (qualified variant; [evidence](#trade_roundtrip))
- [ ] `trade.changed_offer_reconfirm`
- [ ] `trade.out_of_range`
- [ ] `trade.reject`
- [ ] `trade.full_bag_error`
- [ ] `trade.persist`

## mail

Fixture: `owned_second_actor_mailbox`.

- [x] `mail.open` (qualified variant; [evidence](#mail_read))
- [x] `mail.close` (qualified variant; [evidence](#mail_read))
- [x] `mail.inbox` (qualified variant; [evidence](#mail_read))
- [x] `mail.read` (qualified variant; [evidence](#mail_read))
- [x] `mail.attachment_money` (qualified variant; [evidence](#mail_collection))
- [x] `mail.take_item` (qualified variant; [evidence](#mail_collection))
- [ ] `mail.take_all`
- [x] `mail.return` (qualified variant; [evidence](#player_mail))
- [x] `mail.delete` (qualified variant; [evidence](#mail_read))
- [x] `mail.reply` (qualified variant; [evidence](#player_mail))
- [x] `mail.compose` (qualified variant; [evidence](#player_mail))
- [x] `mail.add_recipient` (qualified variant; [evidence](#player_mail))
- [ ] `mail.attach_item`
- [x] `mail.attach_money` (qualified variant; [evidence](#player_mail))
- [ ] `mail.cod_send`
- [ ] `mail.cod_accept`
- [x] `mail.send` (qualified variant; [evidence](#player_mail))
- [x] `mail.postage` (qualified variant; [evidence](#player_mail))
- [ ] `mail.insufficient_money`
- [ ] `mail.full_bag_error`
- [ ] `mail.expired_mail`
- [ ] `mail.persist`

## auction

Fixture: `disposable_auction`.

- [x] `auction.open` (qualified variant; [evidence](#auction_read))
- [x] `auction.close` (qualified variant; [evidence](#auction_read))
- [x] `auction.browse` (qualified variant; [evidence](#auction_read))
- [x] `auction.search` (qualified variant; [evidence](#auction_read))
- [ ] `auction.category`
- [ ] `auction.filter`
- [ ] `auction.sort`
- [x] `auction.select` (qualified variant; [evidence](#auction_roundtrip))
- [ ] `auction.inspect`
- [ ] `auction.bid`
- [ ] `auction.buyout`
- [x] `auction.sell_item` (qualified variant; [evidence](#auction_roundtrip))
- [ ] `auction.sell_stack`
- [ ] `auction.duration`
- [x] `auction.deposit` (qualified variant; [evidence](#auction_roundtrip))
- [x] `auction.auction_cancel` (qualified variant; [evidence](#auction_roundtrip))
- [x] `auction.owned_auctions` (qualified variant; [evidence](#auction_roundtrip))
- [ ] `auction.bids_outbid`
- [x] `auction.mail_delivery` (qualified variant; [evidence](#auction_roundtrip))
- [ ] `auction.persist`

## calendar

Fixture: `disposable_calendar`.

- [x] `calendar.open` (qualified variant; [evidence](#panel_visibility))
- [x] `calendar.close` (qualified variant; [evidence](#panel_visibility))
- [ ] `calendar.previous_month`
- [ ] `calendar.next_month`
- [ ] `calendar.event_view`
- [ ] `calendar.event_create`
- [ ] `calendar.event_edit`
- [ ] `calendar.event_delete`
- [ ] `calendar.invite`
- [ ] `calendar.rsvp_accept`
- [ ] `calendar.rsvp_decline`
- [ ] `calendar.rsvp_tentative`
- [ ] `calendar.moderator`
- [ ] `calendar.recurring_event`
- [ ] `calendar.server_time`
- [ ] `calendar.persist`

## keybindings

Fixture: `saved_local_bindings`.

- [x] `keybindings.open` (qualified variant; [evidence](#owned_keybinding_native_roundtrip))
- [x] `keybindings.close` (qualified variant; [evidence](#owned_keybinding_native_roundtrip))
- [x] `keybindings.category_search` (qualified variant; [evidence](#keybinding_mutation))
- [x] `keybindings.select_action` (qualified variant; [evidence](#keybinding_mutation))
- [x] `keybindings.assign_key` (qualified variant; [evidence](#owned_keybinding_native_roundtrip))
- [x] `keybindings.assign_second_key` (qualified variant; [evidence](#keybinding_mutation))
- [x] `keybindings.modifier_chord` (qualified variant; [evidence](#keybinding_mutation))
- [ ] `keybindings.conflict_replace`
- [ ] `keybindings.conflict_cancel`
- [x] `keybindings.clear_binding` (qualified variant; [evidence](#owned_binding_cancel_clear))
- [x] `keybindings.per_character_toggle` (qualified variant; [evidence](#owned_character_binding_set_roundtrip))
- [x] `keybindings.defaults_cancel` (qualified variant; [evidence](#owned_defaults_cancel))
- [ ] `keybindings.defaults_apply`
- [x] `keybindings.save` (qualified variant; [evidence](#keybinding_mutation))
- [x] `keybindings.cancel` (qualified variant; [evidence](#owned_binding_cancel_clear))
- [x] `keybindings.persistence` (qualified variant; [evidence](#keybinding_mutation))
- [x] `keybindings.restore_original` (qualified variant; [evidence](#keybinding_mutation))

## macros

Fixture: `saved_local_macros`.

- [x] `macros.open` (qualified variant; [evidence](#panel_visibility))
- [x] `macros.close` (qualified variant; [evidence](#panel_visibility))
- [x] `macros.account_tab` (qualified variant; [evidence](#owned_macro_editor_controls))
- [x] `macros.character_tab` (qualified variant; [evidence](#owned_macro_editor_controls))
- [x] `macros.create` (qualified variant; [evidence](#macro_mutation))
- [x] `macros.name` (qualified variant; [evidence](#macro_mutation))
- [x] `macros.icon` (qualified variant; [evidence](#owned_macro_editor_controls))
- [x] `macros.select` (qualified variant; [evidence](#owned_macro_selection_after_reload))
- [x] `macros.edit_body` (qualified variant; [evidence](#macro_mutation))
- [x] `macros.save` (qualified variant; [evidence](#macro_mutation))
- [x] `macros.rename` (qualified variant; [evidence](#owned_macro_editor_controls))
- [x] `macros.drag_to_actionbar` (qualified variant; [evidence](#macro_mutation))
- [x] `macros.execute` (qualified variant; [evidence](#macro_mutation))
- [x] `macros.delete_confirm` (qualified variant; [evidence](#macro_mutation))
- [x] `macros.delete_cancel` (qualified variant; [evidence](#owned_macro_editor_controls))
- [x] `macros.macro_limit` (qualified variant; [evidence](#owned_character_macro_limit))
- [x] `macros.persistence` (qualified variant; [evidence](#macro_mutation))
- [x] `macros.restore_original` (qualified variant; [evidence](#macro_mutation))

## actionbars

Fixture: `saved_local_bars`.

- [x] `actionbars.drag_spell` (qualified variant; [evidence](#stock_spellbook_action_roundtrip))
- [ ] `actionbars.drag_item`
- [x] `actionbars.drag_macro` (qualified variant; [evidence](#macro_mutation))
- [x] `actionbars.clear_slot` (qualified variant; [evidence](#stock_spellbook_action_roundtrip))
- [ ] `actionbars.swap_slots`
- [x] `actionbars.page_next` (qualified variant; [evidence](#stock_actionbar_paging))
- [x] `actionbars.page_previous` (qualified variant; [evidence](#stock_actionbar_paging))
- [x] `actionbars.direct_page` (qualified variant; [evidence](#stock_actionbar_paging))
- [x] `actionbars.extra_bars_toggle` (qualified variant; [evidence](#stock_extra_actionbar_native_toggle))
- [x] `actionbars.lock_toggle` (qualified variant; [evidence](#stock_boolean_settings_roundtrip))
- [ ] `actionbars.cooldown`
- [ ] `actionbars.charges`
- [ ] `actionbars.range_indicator`
- [ ] `actionbars.resource_indicator`
- [ ] `actionbars.vehicle_bar`
- [x] `actionbars.stance_bar` (qualified variant; [evidence](#stock_warrior_stance_bar))
- [ ] `actionbars.pet_bar`
- [ ] `actionbars.override_bar`
- [ ] `actionbars.extra_action_button`
- [x] `actionbars.persist` (qualified variant; [evidence](#stock_spellbook_action_roundtrip))
- [x] `actionbars.restore_original` (qualified variant; [evidence](#macro_mutation))

## settings

Fixture: `saved_local_settings`.

- [x] `settings.open` (qualified variant; [evidence](#stock_boolean_settings_roundtrip))
- [x] `settings.close` (qualified variant; [evidence](#stock_boolean_settings_roundtrip))
- [x] `settings.graphics` (qualified variant; [evidence](#owned_render_scale_apply_roundtrip))
- [x] `settings.resolution` (qualified variant; [evidence](#owned_pending_display_selection_discard))
- [x] `settings.window_mode` (qualified variant; [evidence](#owned_pending_display_selection_discard))
- [x] `settings.monitor_selection` (qualified variant; [evidence](#owned_pending_display_selection_discard))
- [x] `settings.render_scale` (qualified variant; [evidence](#owned_render_scale_apply_roundtrip))
- [x] `settings.quality` (qualified variant; [evidence](#owned_pending_graphics_quality_discard))
- [x] `settings.sound_volume` (qualified variant; [evidence](#owned_master_volume_stepper_roundtrip))
- [x] `settings.mute` (qualified variant; [evidence](#stock_boolean_settings_roundtrip))
- [x] `settings.interface` (qualified variant; [evidence](#owned_move_pad_enable_roundtrip))
- [x] `settings.mouse_sensitivity` (qualified variant; [evidence](#owned_mouse_sensitivity_enable_roundtrip))
- [x] `settings.keyboard_controls` (qualified variant; [evidence](#owned_interact_key_enable_roundtrip))
- [x] `settings.accessibility` (qualified variant; [evidence](#owned_ui_colorblind_checkbox_roundtrip))
- [x] `settings.camera` (qualified variant; [evidence](#stock_interface_boolean_settings))
- [x] `settings.nameplates` (qualified variant; [evidence](#stock_interface_boolean_settings))
- [x] `settings.floating_combat_text` (qualified variant; [evidence](#stock_interface_boolean_settings))
- [x] `settings.auto_loot` (qualified variant; [evidence](#stock_boolean_settings_roundtrip))
- [x] `settings.tutorials` (qualified variant; [evidence](#stock_interface_boolean_settings))
- [x] `settings.addons` (qualified variant; [evidence](#owned_addons_version_check_roundtrip))
- [x] `settings.apply` (qualified variant; [evidence](#owned_render_scale_apply_roundtrip))
- [x] `settings.cancel` (qualified variant; [evidence](#owned_settings_exit_cancel_discard))
- [x] `settings.defaults_cancel` (qualified variant; [evidence](#owned_defaults_cancel))
- [x] `settings.defaults_apply` (qualified variant; [evidence](#owned_colorblind_current_category_defaults))
- [x] `settings.persistence` (qualified variant; [evidence](#owned_render_scale_ui_reload_persistence))
- [x] `settings.restore_original` (qualified variant; [evidence](#stock_boolean_settings_roundtrip))

## menu

Fixture: `in_world`.

- [x] `menu.open` (qualified variant; [evidence](#panel_visibility))
- [x] `menu.close` (qualified variant; [evidence](#panel_visibility))
- [x] `menu.options` (qualified variant; [evidence](#owned_keybinding_native_roundtrip))
- [x] `menu.keybindings` (qualified variant; [evidence](#owned_keybinding_native_roundtrip))
- [x] `menu.macros` (qualified variant; [evidence](#owned_macro_menu_route))
- [x] `menu.addons` (qualified variant; [evidence](#owned_addon_menu_route))
- [x] `menu.help` (qualified variant; [evidence](#owned_support_shell_navigation))
- [x] `menu.logout` (qualified variant; [evidence](#owned_menu_logout_reused))
- [ ] `menu.exit_cancel`

## help

Fixture: `offline_local_server`.

- [x] `help.open` (qualified variant; [evidence](#owned_support_shell_navigation))
- [x] `help.close` (qualified variant; [evidence](#owned_support_shell_navigation))
- [ ] `help.unstuck`
- [ ] `help.support_category`
- [ ] `help.ticket_create_if_supported`
- [ ] `help.ticket_status_if_supported`
- [ ] `help.report_bug_if_supported`
- [ ] `help.survey_if_supported`

## movement

Fixture: `safe_terrain_variants`.

- [x] `movement.forward` (qualified variant; [evidence](#stock_ground_bindings_native_peer))
- [x] `movement.backward` (qualified variant; [evidence](#stock_ground_bindings_native_peer))
- [x] `movement.turn_left` (qualified variant; [evidence](#stock_ground_bindings_native_peer))
- [x] `movement.turn_right` (qualified variant; [evidence](#stock_ground_bindings_native_peer))
- [x] `movement.strafe_left` (qualified variant; [evidence](#stock_ground_bindings_native_peer))
- [x] `movement.strafe_right` (qualified variant; [evidence](#follow))
- [x] `movement.mouse_turn` (qualified variant; [evidence](#owned_stationary_mouse_turn_roundtrip))
- [x] `movement.autorun` (qualified variant; [evidence](#stock_walk_run_autorun))
- [x] `movement.stop` (qualified variant; [evidence](#stock_ground_bindings_native_peer))
- [x] `movement.walk_toggle` (qualified variant; [evidence](#stock_walk_run_autorun))
- [x] `movement.jump` (qualified variant; [evidence](#flat_ground_jump_landing))
- [x] `movement.sit` (qualified variant; [evidence](#stock_sit_stand_native_pose))
- [x] `movement.stand` (qualified variant; [evidence](#stock_sit_stand_native_pose))
- [x] `movement.sheath` (qualified variant; [evidence](#standing_scout_weapon_cycle))
- [ ] `movement.swim`
- [ ] `movement.dive`
- [ ] `movement.surface`
- [ ] `movement.breath`
- [ ] `movement.falling`
- [ ] `movement.fall_damage`
- [ ] `movement.collision`
- [ ] `movement.slope`
- [ ] `movement.water_entry`
- [ ] `movement.water_exit`
- [ ] `movement.mount_ground`
- [ ] `movement.mount_fly`
- [ ] `movement.takeoff`
- [ ] `movement.ascend`
- [ ] `movement.descend`
- [ ] `movement.land`
- [ ] `movement.dismount`
- [ ] `movement.indoor_mount_error`
- [ ] `movement.taxi`
- [ ] `movement.board_transport`
- [ ] `movement.leave_transport`
- [ ] `movement.vehicle_enter`
- [ ] `movement.vehicle_exit`
- [ ] `movement.vehicle_seat`
- [x] `movement.follow` (qualified variant; [evidence](#follow))
- [ ] `movement.interact_with_target`

## targeting

Fixture: `owned_targets`.

- [x] `targeting.click_target` (qualified variant; [evidence](#owned_party_targeting_focus))
- [ ] `targeting.tab_enemy`
- [ ] `targeting.previous_enemy`
- [x] `targeting.friendly_target` (qualified variant; [evidence](#nearby_target))
- [x] `targeting.clear_target` (qualified variant; [evidence](#owned_party_targeting_focus))
- [x] `targeting.target_self` (qualified variant; [evidence](#owned_party_targeting_focus))
- [x] `targeting.party_target` (qualified variant; [evidence](#owned_party_targeting_focus))
- [ ] `targeting.raid_target`
- [x] `targeting.assist` (qualified variant; [evidence](#owned_party_assist_target_target))
- [x] `targeting.focus` (qualified variant; [evidence](#owned_party_targeting_focus))
- [x] `targeting.clear_focus` (qualified variant; [evidence](#owned_party_targeting_focus))
- [x] `targeting.target_target` (qualified variant; [evidence](#owned_party_assist_target_target))
- [x] `targeting.target_last` (qualified variant; [evidence](#owned_party_targeting_focus))
- [x] `targeting.mouseover` (qualified variant; [evidence](#owned_world_player_hover))
- [x] `targeting.tooltip` (qualified variant; [evidence](#owned_world_player_hover))
- [ ] `targeting.nameplate`
- [x] `targeting.inspect_player` (qualified variant; [evidence](#inspect))
- [ ] `targeting.trade_context`
- [ ] `targeting.duel_context`
- [ ] `targeting.follow_context`
- [ ] `targeting.invite_context`
- [ ] `targeting.report_context_cancel`

## combat

Fixture: `class_variants`.

- [x] `combat.melee_start` (qualified variant; [evidence](#ordinary_quest_melee_completion))
- [x] `combat.melee_stop` (qualified variant; [evidence](#owned_owner_melee_stop))
- [ ] `combat.ranged_attack`
- [ ] `combat.instant_cast`
- [ ] `combat.cast_time`
- [ ] `combat.channel`
- [ ] `combat.cast_cancel`
- [ ] `combat.interrupt`
- [x] `combat.auto_attack` (qualified variant; [evidence](#ordinary_quest_melee_completion))
- [ ] `combat.cooldown`
- [ ] `combat.resource_cost`
- [ ] `combat.insufficient_resource`
- [x] `combat.range_error` (qualified variant; [evidence](#owned_primary_native_melee_range_feedback))
- [ ] `combat.line_of_sight_error`
- [ ] `combat.facing_error`
- [ ] `combat.moving_cast_error`
- [ ] `combat.aura_apply`
- [ ] `combat.aura_expire`
- [ ] `combat.aura_cancel`
- [ ] `combat.dispel`
- [ ] `combat.combat_flag`
- [ ] `combat.threat`
- [ ] `combat.aggro`
- [ ] `combat.equipment_lock`
- [ ] `combat.immunity`
- [ ] `combat.crowd_control`
- [ ] `combat.shapeshift`
- [x] `combat.stance` (qualified variant; [evidence](#stock_warrior_stance_bar))
- [ ] `combat.combo_points`
- [ ] `combat.rune_resource`
- [ ] `combat.holy_power`
- [ ] `combat.eclipse`
- [ ] `combat.totems`
- [ ] `combat.resurrection`
- [ ] `combat.persist`

## pets

Fixture: `pet_class_variants`.

- [x] `pets.summon` (qualified variant; [evidence](#owned_trained_imp_summon_from_absence))
- [x] `pets.dismiss` (qualified variant; [evidence](#owned_trained_imp_dismiss))
- [x] `pets.command_attack` (qualified variant; [evidence](#owned_trained_imp_attack))
- [x] `pets.command_follow` (qualified variant; [evidence](#owned_trained_imp_stay_follow))
- [x] `pets.command_stay` (qualified variant; [evidence](#owned_trained_imp_stay_follow))
- [x] `pets.command_move_to` (qualified variant; [evidence](#owned_trained_imp_move_to))
- [x] `pets.passive` (qualified variant; [evidence](#owned_trained_imp_passive_assist))
- [x] `pets.defensive` (qualified variant; [evidence](#owned_trained_imp_defensive))
- [x] `pets.assist` (qualified variant; [evidence](#owned_trained_imp_passive_assist))
- [x] `pets.autocast_toggle` (qualified variant; [evidence](#owned_trained_imp_autocast))
- [x] `pets.spell_cast` (qualified variant; [evidence](#owned_trained_imp_blood_pact))
- [x] `pets.pet_target` (qualified variant; [evidence](#owned_imp_target_and_health))
- [x] `pets.pet_health` (qualified variant; [evidence](#owned_imp_target_and_health))
- [x] `pets.pet_power` (qualified variant; [evidence](#owned_imp_power))
- [ ] `pets.happiness_if_available`
- [x] `pets.rename` (qualified variant; [evidence](#owned_hunter_one_time_rename))
- [x] `pets.stable_open` (qualified variant; [evidence](#owned_hunter_native_stable_open))
- [ ] `pets.stable_slot`
- [ ] `pets.stable_swap`
- [ ] `pets.tame`
- [ ] `pets.abandon_confirm`
- [ ] `pets.abandon_cancel`
- [ ] `pets.revive`
- [ ] `pets.vehicle_pet_bar`
- [x] `pets.persist` (qualified variant; [evidence](#owned_imp_persistence))

## loot

Fixture: `loot_variants`.

- [ ] `loot.open`
- [ ] `loot.close`
- [ ] `loot.corpse_money`
- [ ] `loot.item_pickup`
- [ ] `loot.auto_loot`
- [ ] `loot.quest_loot`
- [ ] `loot.gather_loot`
- [ ] `loot.fishing_loot`
- [ ] `loot.skinning`
- [ ] `loot.disenchant`
- [ ] `loot.prospect`
- [ ] `loot.mill`
- [ ] `loot.group_roll_need`
- [ ] `loot.group_roll_greed`
- [ ] `loot.group_roll_pass`
- [ ] `loot.master_loot`
- [ ] `loot.free_for_all`
- [ ] `loot.round_robin`
- [ ] `loot.full_bag_error`
- [ ] `loot.bind_confirm`
- [ ] `loot.loot_release`
- [ ] `loot.persist`

## death

Fixture: `disposable_actor`.

- [ ] `death.death_animation`
- [ ] `death.release_spirit`
- [ ] `death.graveyard`
- [ ] `death.movement_ghost`
- [ ] `death.corpse_reclaim`
- [ ] `death.resurrection_accept`
- [ ] `death.resurrection_decline`
- [ ] `death.spirit_healer`
- [ ] `death.resurrection_sickness`
- [ ] `death.durability_loss`
- [ ] `death.disconnect_dead`
- [ ] `death.persist`

## travel

Fixture: `travel_variants`.

- [ ] `travel.hearthstone`
- [ ] `travel.teleport_spell`
- [ ] `travel.portal_enter`
- [ ] `travel.boat`
- [ ] `travel.zeppelin`
- [ ] `travel.tram`
- [ ] `travel.taxi_open`
- [ ] `travel.taxi_learn`
- [ ] `travel.taxi_select`
- [ ] `travel.taxi_cost`
- [ ] `travel.taxi_animation`
- [ ] `travel.taxi_complete`
- [ ] `travel.taxi_instant_experiment_only`
- [ ] `travel.flight_ground_control`
- [ ] `travel.flight_master_license`
- [ ] `travel.cold_weather_flying`
- [ ] `travel.outland_flying`
- [ ] `travel.cross_continent_transfer`
- [ ] `travel.instance_enter`
- [ ] `travel.instance_leave`
- [ ] `travel.dungeon_portal`
- [ ] `travel.summon_accept`
- [ ] `travel.summon_decline`
- [ ] `travel.summon_expire`

## pve group finder

Fixture: `owned_group_and_queue`.

- [x] `pve_group_finder.open` (qualified variant; [evidence](#panel_visibility))
- [x] `pve_group_finder.close` (qualified variant; [evidence](#panel_visibility))
- [ ] `pve_group_finder.role_choose`
- [ ] `pve_group_finder.dungeon_select`
- [ ] `pve_group_finder.random_dungeon`
- [ ] `pve_group_finder.queue`
- [ ] `pve_group_finder.cancel_queue`
- [ ] `pve_group_finder.role_check`
- [ ] `pve_group_finder.accept_proposal`
- [ ] `pve_group_finder.decline_proposal`
- [ ] `pve_group_finder.teleport_in`
- [ ] `pve_group_finder.teleport_out`
- [ ] `pve_group_finder.vote_kick`
- [ ] `pve_group_finder.deserter`
- [ ] `pve_group_finder.reward`
- [ ] `pve_group_finder.raid_browser`
- [ ] `pve_group_finder.raid_finder_if_available`
- [ ] `pve_group_finder.difficulty_lock`
- [ ] `pve_group_finder.instance_reset`
- [ ] `pve_group_finder.saved_instances`

## pvp

Fixture: `owned_pvp_fixture`.

- [x] `pvp.open` (qualified variant; [evidence](#panel_visibility))
- [x] `pvp.close` (qualified variant; [evidence](#panel_visibility))
- [ ] `pvp.battleground_select`
- [ ] `pvp.battleground_queue`
- [ ] `pvp.group_queue`
- [ ] `pvp.cancel_queue`
- [ ] `pvp.accept_invite`
- [ ] `pvp.decline_invite`
- [ ] `pvp.leave_battleground`
- [ ] `pvp.scoreboard`
- [ ] `pvp.objective_flag`
- [ ] `pvp.objective_capture`
- [ ] `pvp.honor_gain`
- [ ] `pvp.honor_purchase`
- [ ] `pvp.arena_team_create`
- [ ] `pvp.arena_team_invite`
- [ ] `pvp.arena_team_leave`
- [ ] `pvp.arena_queue`
- [ ] `pvp.arena_rating`
- [ ] `pvp.arena_reward`
- [ ] `pvp.duel_request`
- [ ] `pvp.duel_accept`
- [ ] `pvp.duel_decline`
- [ ] `pvp.duel_complete`
- [ ] `pvp.duel_cancel`
- [ ] `pvp.world_pvp_toggle`
- [ ] `pvp.persist`

## world objects

Fixture: `object_variants`.

- [ ] `world_objects.gossip_open`
- [ ] `world_objects.gossip_select`
- [ ] `world_objects.gossip_back`
- [ ] `world_objects.close`
- [ ] `world_objects.inspect`
- [ ] `world_objects.text_page`
- [ ] `world_objects.door`
- [ ] `world_objects.chest`
- [ ] `world_objects.lever`
- [ ] `world_objects.quest_object`
- [ ] `world_objects.fishing_pool`
- [ ] `world_objects.destructible_object`
- [ ] `world_objects.chair`
- [ ] `world_objects.transport`
- [ ] `world_objects.gameobject_cast`
- [ ] `world_objects.cancel_gameobject_cast`
- [ ] `world_objects.unavailable_object`
- [ ] `world_objects.error_distance`

## ui misc

Fixture: `in_world`.

- [x] `ui_misc.dressup_open` (qualified variant; [evidence](#stock_dressup_sword_preview))
- [x] `ui_misc.dressup_item` (qualified variant; [evidence](#stock_dressup_sword_preview))
- [x] `ui_misc.dressup_rotate` (qualified variant; [evidence](#stock_dressup_sword_preview))
- [x] `ui_misc.dressup_close` (qualified variant; [evidence](#stock_dressup_sword_preview))
- [x] `ui_misc.item_text_open` (qualified variant; [evidence](#owned_native_letter_text))
- [x] `ui_misc.item_text_page` (qualified variant; [evidence](#owned_native_letter_text))
- [x] `ui_misc.item_text_close` (qualified variant; [evidence](#owned_native_letter_text))
- [x] `ui_misc.tooltip_compare` (qualified variant; [evidence](#stock_owned_sword_comparison))
- [x] `ui_misc.achievement_link` (qualified variant; [evidence](#owned_pending_achievement_link))
- [x] `ui_misc.quest_link` (qualified variant; [evidence](#owned_existing_quest_link_cancel))
- [x] `ui_misc.item_link` (qualified variant; [evidence](#owned_pending_backpack_item_link))
- [x] `ui_misc.spell_link` (qualified variant; [evidence](#owned_pending_known_spell_link))
- [x] `ui_misc.copy_name` (qualified variant; [evidence](#owned_player_chat_link_name_copy))
- [x] `ui_misc.screenshot` (qualified variant; [evidence](#stock_display_controls))
- [x] `ui_misc.toggle_ui` (qualified variant; [evidence](#stock_display_controls))
- [x] `ui_misc.zoom_camera` (qualified variant; [evidence](#stock_camera_zoom_latency))
- [ ] `ui_misc.camera_reset`
- [ ] `ui_misc.cinematics_skip`
- [ ] `ui_misc.movie_skip`
- [x] `ui_misc.cursor_pickup` (qualified variant; [evidence](#stock_spellbook_action_roundtrip))
- [x] `ui_misc.cursor_cancel` (qualified variant; [evidence](#stock_spellbook_action_roundtrip))
- [x] `ui_misc.popup_confirm` (qualified variant; [evidence](#owned_macro_confirmation_controls))
- [x] `ui_misc.popup_cancel` (qualified variant; [evidence](#owned_macro_confirmation_controls))
- [x] `ui_misc.latency_display` (qualified variant; [evidence](#stock_camera_zoom_latency))
- [x] `ui_misc.fps_display` (qualified variant; [evidence](#stock_display_controls))
- [x] `ui_misc.network_disconnect_notification` (qualified variant; [evidence](#owned_bridge_restart_disconnect_notification))

## account services

Fixture: `unsupported_service_contract`.

- [ ] `account_services.shop_open`
- [ ] `account_services.store_offer_request`
- [ ] `account_services.token_ui`
- [ ] `account_services.character_boost`
- [ ] `account_services.race_change`
- [ ] `account_services.faction_change`
- [ ] `account_services.paid_rename`
- [ ] `account_services.paid_transfer`
- [ ] `account_services.social_contract`
- [ ] `account_services.battlenet_friends`
- [ ] `account_services.battlenet_whisper`
- [ ] `account_services.voice_chat`
- [ ] `account_services.collections_account_sync`
- [ ] `account_services.support_ticket`

## Installed bindings

Run `pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_inventory capture-bindings --output <owned-evidence-directory>`. This reads all binding names, categories and current keys from build 60895. Every command is an additional parametrized test contract; headers are classified rather than counted as actions. The generated catalog and screenshots belong in DVC.

## Qualification evidence

Each checked operation refers to one reviewed record below. Receipt paths are members of the linked DVC archive; hashes identify the reviewed JSON receipt.

### panel_visibility

Ordinary installed bindings and visible controls open and close the listed panels on build 60895. All four equipped bags open individually.

Remaining limits: Panel contents, mutations and unsampled variants remain open; bags with other sizes and layouts are unqualified.

- [442_interactions_20261002_02.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_02.tar.gz.dvc), member `evidence/client_interactions_20261002_followup/panel_diagnostic_01/episode.json`, SHA-256 `1712c3bcfe29754345b5c8ff03afb6831957fd235a44263fa61fbf017a89c77f`.
  Checked cases: `bags.backpack` (panel_open_pass), `bags.bag_one` (panel_open_pass), `bags.bag_two` (panel_open_pass), `bags.bag_three` (panel_open_pass), `bags.bag_four` (panel_open_pass), `bags.open_all` (panel_open_pass), `bags.open_all.close` (panel_close_pass), `character.open` (panel_open_pass), `character.open.close` (panel_close_pass), `reputation.open` (panel_open_pass), `reputation.open.close` (panel_close_pass), `professions.open` (panel_open_pass), `professions.open.close` (panel_close_pass), `spellbook.open` (panel_open_pass), `spellbook.open.close` (panel_close_pass), `talents.open` (panel_open_pass), `talents.open.close` (panel_close_pass), `quests.open_log` (panel_open_pass), `quests.open_log.close` (panel_close_pass), `map.open` (panel_open_pass), `map.open.close` (panel_close_pass), `collections.open` (panel_open_pass), `collections.open.close` (panel_close_pass), `journal.open` (panel_open_pass), `journal.open.close` (panel_close_pass), `achievements.open` (panel_open_pass), `achievements.open.close` (panel_close_pass), `achievements.statistics` (panel_open_pass), `friends.open` (panel_open_pass), `friends.open.close` (panel_close_pass), `pve_group_finder.open` (panel_open_pass), `pve_group_finder.open.close` (panel_close_pass), `pvp.open` (panel_open_pass), `pvp.open.close` (panel_close_pass), `menu.open` (panel_open_pass), `menu.open.close` (panel_close_pass), `macros.open` (panel_open_pass), `macros.open.close` (panel_close_pass), `calendar.open` (panel_open_pass), `calendar.open.close` (panel_close_pass).

### world_markers

Eight outdoor Northshire world markers placed through ordinary ground clicks, observed on both clients, individually removed and cleared together. Native five spells and three modern-only annotations are attributed.

Remaining limits: Other maps/phases, transport-ground coordinates, range boundaries and relog/restart persistence remain open.

- [442_interactions_20261002_01.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_01.tar.gz.dvc), member `evidence/client_interactions_20261002/world_markers_trial_02/episode.json`, SHA-256 `2a9498b60cc74f87bf97f1f58cef25542a0102becd25381fc24ccbc5b614db71`.
  Checked cases: `raid.world_marker.place.1` (world_marker_visible_pass), `raid.world_marker.place.2` (world_marker_visible_pass), `raid.world_marker.place.3` (world_marker_visible_pass), `raid.world_marker.place.4` (world_marker_visible_pass), `raid.world_marker.place.5` (world_marker_visible_pass), `raid.world_marker.place.6` (world_marker_visible_pass), `raid.world_marker.place.7` (world_marker_visible_pass), `raid.world_marker.place.8` (world_marker_visible_pass), `raid.world_marker.clear.individual` (world_marker_clear_pass), `raid.world_marker.clear.all` (world_marker_clear_pass).

### group_roster

Both owned characters show valid native member contents and visible health bars on the main screen.

Remaining limits: Two clients on map 0, in different zones; larger rosters, pets and cross-map variants remain open.

- [442_interactions_20261002_01.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_01.tar.gz.dvc), member `evidence/client_interactions_20261002/group_display_02/cohort.json`, SHA-256 `599f24ddb05fbe55b00640662cd5824c8a5e376788b65939ae2d84d1950c6558`.

### roles

Ordinary role poll completes with Tank and Damage; both clients agree on both assignments.

Remaining limits: Healer, rejection permissions and larger groups remain open.

- [442_interactions_20261002_01.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_01.tar.gz.dvc), member `evidence/client_interactions_20261002/roles_trial_02/cohort.json`, SHA-256 `d135d79783e9b533bced976c919c81a502ebe5af10d4c3063c03c787139cd6fd`.

### raid_profiles

Everyone-assistant changed both ways with peer flags; raid frame lock/unlock and show/hide controls change the saved profile and restore it.

Remaining limits: Individual assistant promotion/demotion, reconnect persistence and combat variants remain open.

- [442_interactions_20261002_03.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_03.tar.gz.dvc), member `evidence/client_interactions_20261002_ui02/raid_controls_01/episode.json`, SHA-256 `542b14fc867f1b1dbde6d9c7c221f0dff21600350ef9235216a4644c119215d1`.
  Checked cases: `raid.everyone_assistant.false` (assistant_change_pass), `raid.everyone_assistant.true` (assistant_change_pass), `raid.profile.locked.false` (raid_profile_change_pass), `raid.profile.locked.true` (raid_profile_change_pass), `raid.profile.shown.false` (raid_profile_change_pass), `raid.profile.shown.true` (raid_profile_change_pass).

### group_conversion

Both party-to-raid and raid-to-party conversions agree with native group state and the peer client.

Remaining limits: Larger groups, permission rejections and conversion during combat remain open.

- [442_interactions_20261002_03.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_03.tar.gz.dvc), member `evidence/client_interactions_20261002_ui02/group_conversions_02/episode.json`, SHA-256 `df30e5321a720951bef6855caf1c6420e89448194a375defe2a94ebbd45db3c0`.
  Checked cases: `raid.convert_to_party` (group_conversion_pass), `raid.convert_from_party` (group_conversion_pass).

### ready_check

Raid ready checks initiated and answered Ready and Not Ready by the two owned accounts, with native completion and both dialogs closed.

Remaining limits: Party-only mode, larger rosters and permissions remain open.

- [442_interactions_20261002_03.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_03.tar.gz.dvc), member `evidence/client_interactions_20261002_ui02/ready_checks_04/ready/cohort.json`, SHA-256 `a399814abf99954035833bc5cb4849f9668356a1b2fa0739d458ac026ec4e2fb`.
- [442_interactions_20261002_03.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_03.tar.gz.dvc), member `evidence/client_interactions_20261002_ui02/ready_checks_04/not_ready/cohort.json`, SHA-256 `b92f1ac5093161793970d590516199267cc6bf87501b60b11ab441726b228c05`.

### ready_timeout

No client answer; native timer completion is observed on both sessions and both dialogs close.

Remaining limits: Other group sizes and disconnect timing remain open.

- [442_interactions_20261002_03.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_03.tar.gz.dvc), member `evidence/client_interactions_20261002_ui02/ready_timeout_01/cohort.json`, SHA-256 `e514a36cd465fad32d51a8433b60ec1c809482d3281f34835358da250e22d71a`.

### party_invitation

Native friend addition, normal party invitation and acceptance by the second account are attributed.

Remaining limits: Decline, duplicate/full-group errors, remove/notes/ignore and cross-map variants remain open.

- [442_interactions_20261002_01.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_01.tar.gz.dvc), member `evidence/client_interactions_20261002/social_trial_07/primary/episode.json`, SHA-256 `084cf3964ca335ec4668efab6045bf9dd93909062d9dc9e51fe09bda7b1833d1`.
  Checked cases: `friends.add_friend` (friend_add_pass), `party.invite` (invitation_submitted).
- [442_interactions_20261002_01.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_01.tar.gz.dvc), member `evidence/client_interactions_20261002/social_trial_07/scout/episode.json`, SHA-256 `c79fd90b076f648676771d586b875bdf0d19f4166fe75f30e606e89c687dd29e`.
  Checked cases: `party.accept` (party_accept_pass).

### keybinding_mutation

Secondary Ctrl-Shift-F12 FPS binding searched, selected, assigned, saved, reloaded, executed twice and restored.

Remaining limits: First-slot replacement, conflicts, defaults and full client reconnect persistence remain open.

- [442_interactions_20261002_02.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_02.tar.gz.dvc), member `evidence/client_interactions_20261002_followup/keybindings_trial_03/episode.json`, SHA-256 `edd3f452aa1faa1590c03477d5209c2a38e8b3f90946ddcfcc4e9467e6586ed2`.
  Checked cases: `keybindings.search` (ui_edit_pass), `keybindings.listen` (binding_listener_pass), `keybindings.assign` (binding_assign_pass), `keybindings.save` (binding_save_pass), `keybindings.reload` (binding_reload_pass), `keybindings.execute` (binding_execute_pass), `keybindings.toggle_back` (binding_execute_pass).

### macro_mutation

Temporary account macro created, saved, physically dragged to an action slot, reloaded and executed with native Battle Shout completion. Ordinary code cleanup confirms deletion and empty original macro/action slot state.

Remaining limits: Character macro variants, rename/icon selection, cancellation/limits and full reconnect persistence remain open.

- [442_interactions_20261002_02.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_02.tar.gz.dvc), member `evidence/client_interactions_20261002_followup/macro_trial_01/episode.json`, SHA-256 `dab77c3fa1773db6f19d94f3e7ea7c565a3e883f963d2d9beead65353b2f23f7`.
  Checked cases: `macros.create` (macro_create_pass), `macros.name` (ui_edit_pass), `macros.body` (ui_edit_pass), `macros.save` (macro_save_pass), `macros.drag_to_bar` (macro_bar_pass), `macros.reload` (macro_reload_pass), `macros.execute` (macro_execute_pass).

### profession_catalogs

Alchemy, Tailoring, Cooking and First Aid recipe catalogs and the Archaeology panel display through ordinary controls.

Remaining limits: Other professions, filters, recipe metadata and archaeology panel mutations remain open.

- [442_interactions_20261002_03.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_03.tar.gz.dvc), member `evidence/client_interactions_20261002_ui02/profession_trial_01/episode.json`, SHA-256 `72892c1026504b1f96b5174831c892775cfc5e20e79da95967851d5310414ad9`.
  Checked cases: `professions.primary_one` (profession_recipe_pass), `professions.primary_two` (profession_recipe_pass), `professions.cooking` (profession_recipe_pass), `professions.first_aid` (profession_recipe_pass), `professions.archaeology` (panel_open_pass).

### crafting

Alchemy recipe searched/selected; one and two crafts complete with exact native/client reagent and product accounting and restored resources.

Remaining limits: Other recipes/professions, cancellation, skill gains and cooldowns remain open.

- [442_interactions_20261002_04.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_04.tar.gz.dvc), member `evidence/client_interactions_20261002_ui03/crafting_04/episode.json`, SHA-256 `9b89a460135227b0f5dc80f44e40dd4348c31b2d8b811996281c4fc66ea37d61`.
  Checked cases: `professions.alchemy` (recipe_list_pass), `professions.recipe_search` (ui_edit_pass), `professions.recipe_select` (recipe_select_pass), `professions.craft_one` (craft_result_pass), `professions.craft_multiple` (craft_result_pass).

### equipment

One helmet unequipped and reequipped; native and visible strength, armor, damage and maximum-health deltas agree and the entire fixture is restored. The geared physical damage modifier, attack speed and finite rendered melee DPS also match exact native fields after the bridge correction; full resources and sidebar restore. Public melee/ranged crit, all seven spell-school crit values, ranged speed/damage/percentage and rendered melee crit/ranged DPS match native fields on login and during ordinary helmet removal/re-equip; exact sparse updates and complete fixture restoration pass. Native/public supported ratings, melee/ranged haste, mastery, both expertise values and dodge/parry agree in a complete ordinary helmet and haste-belt roundtrip. Five reviewed stock phases render the expected melee haste, mastery and expertise values; four native sparse updates and full original fixture/sidebar restoration pass. Public spell haste and visible spell/defense haste/dodge/parry rows agree throughout the complete ordinary haste-belt roundtrip. Three reviewed phases show3.22/1.51/3.22% haste, two sparse native cast-multiplier updates are attributable, and all original native resources plus32-bit category settings/order/sidebar/panels restore. All22 equipment observations are passive.

Remaining limits: Owned geared warrior and documented helmet/belt/damage/combat variants only. Item level, other ranged/spell/defense rows, actual dual-wield and shield-block gameplay, offhand/shield-block crit APIs, other classes and unsampled variants remain open. Compiled school modifier gate tests do not imply a newly proven live buff mutation. Separate weapon/set/comparison records do not imply broader equipment coverage. Cached reconnect stayed disconnected and remains unqualified; fresh launcher entries pass separately.

- [442_interactions_20261002_04.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_04.tar.gz.dvc), member `evidence/client_interactions_20261002_ui03/equipment_02/episode.json`, SHA-256 `44214da3f31946df95c34cedc4a2ef828f8d15adbe3dc98fd39ca9797abe3a0c`.
  Checked cases: `character.unequip` (equipment_change_pass), `character.equip` (equipment_change_pass), `character.stats.unequipped` (character_stats_pass), `character.stats.equipped_after` (character_stats_pass).
- [442_interactions_20261003_39.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_39.tar.gz.dvc), member `evidence/client_interactions_20261003_ui38/character_damage_after_01/episode.json`, SHA-256 `d62e1482b818d6a30dace94d80f489351944387c71d8c4a2d2856107f18b9fbf`.
  Checked cases: `character.stats.damage_modifiers` (character_damage_display_pass).
- [442_interactions_20261003_39.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_39.tar.gz.dvc), member `evidence/client_interactions_20261003_ui38/character_damage_after_review.json`, SHA-256 `7fd49c603b7b6656696bed7ada8ce7e6d54a8f1ef026d9ab36b374f24c54d283`.
- [442_interactions_20261003_41.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_41.tar.gz.dvc), member `evidence/client_interactions_20261003_ui40/character_combat_after_02/episode.json`, SHA-256 `e2a3ae008cf24dd69f05162dbb451af5603b1f186c77b82d746c06153ff0e84b`.
  Checked cases: `character.stats.combat.equipped_before` (character_combat_display_pass), `character.stats.combat.unequipped` (character_combat_display_pass), `character.stats.combat.equipped_after` (character_combat_display_pass).
- [442_interactions_20261003_41.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_41.tar.gz.dvc), member `evidence/client_interactions_20261003_ui40/character_combat_after_review.json`, SHA-256 `8716a9d4def29c9dcad1db87b9f744651e99237e8fb115164a7fcaa4bc2e0981`.
- [442_interactions_20261003_42.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_42.tar.gz.dvc), member `evidence/client_interactions_20261003_ui41/character_ratings_after_03/episode.json`, SHA-256 `91407b407c4e93e16fedc96adbff63f5dcca02583b5e13f157314213cd8717c1`.
  Checked cases: `character.stats.ratings.equipped_before` (character_ratings_display_pass), `character.stats.ratings.unequipped` (character_ratings_display_pass), `character.stats.ratings.equipped_after` (character_ratings_display_pass), `character.stats.ratings.waist_unequipped` (character_ratings_display_pass), `character.stats.ratings.waist_equipped_after` (character_ratings_display_pass).
- [442_interactions_20261003_42.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_42.tar.gz.dvc), member `evidence/client_interactions_20261003_ui41/character_ratings_after_review.json`, SHA-256 `eef0402a3ea6a219ca8be101521023af7bc231e03d71192f6d0ae405e45a40bd`.
- [442_interactions_20261003_43.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_43.tar.gz.dvc), member `evidence/client_interactions_20261003_ui42/character_spell_after_01/episode.json`, SHA-256 `14ea34d1cd625f11cc2c0627ae59ddea89c718f27c01a279ba96a776aa904dfb`.
  Checked cases: `character.stats.spell.equipped_before` (character_spell_defense_pass), `character.stats.spell.waist_unequipped` (character_spell_defense_pass), `character.stats.spell.waist_equipped_after` (character_spell_defense_pass).
- [442_interactions_20261003_43.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_43.tar.gz.dvc), member `evidence/client_interactions_20261003_ui42/character_spell_after_review.json`, SHA-256 `c0c5b26290a08016b445fac96f064313bd046ec1163b2513764ece5ae3a73113`.

### inventory_movement

Hearthstone moved and restored, then an existing stack moved to an equipped bag and back with exact native identity/count, UI and complete resource agreement.

Remaining limits: Other bag types, persistence and error paths remain open.

- [442_interactions_20261002_03.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_03.tar.gz.dvc), member `evidence/client_interactions_20261002_ui02/inventory_moves_03/episode.json`, SHA-256 `3aa66e8d3128c998d7c32269d5b3cd56f4b65b1e205508cb98f17dab11ccf02a`.
  Checked cases: `bags.move_item` (inventory_move_pass), `bags.move_item_restore` (inventory_move_pass).
- [442_interactions_20261002_03.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_03.tar.gz.dvc), member `evidence/client_interactions_20261002_ui02/cross_bag_01/episode.json`, SHA-256 `5253326841cc1e7f56a5abf91fb0ec0c50e53b9878b7f8993f1d5d8efe1263f0`.
  Checked cases: `bags.move_to_equipped_bag` (inventory_move_pass), `bags.move_from_equipped_bag` (inventory_move_pass).

### stack_split_merge

One keystone split from a five-item stack, placed and merged; original identity/count and full resources restored.

Remaining limits: Other quantities, full bags and persistence remain open.

- [442_interactions_20261002_03.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_03.tar.gz.dvc), member `evidence/client_interactions_20261002_ui02/stack_split_01/episode.json`, SHA-256 `8ebc84f1af3dc985124f3a63e5f44fedf507873da73ab46f1bdfb4f05b4e4a9e`.
  Checked cases: `bags.split_stack` (inventory_split_pass), `bags.merge_stack` (inventory_merge_pass).

### chat

Six normal chat sends reach native handlers; raid, raid-warning and whisper are independently received by the peer.

Remaining limits: Say/yell/emote peer delivery, other languages/channels and failure variants remain open.

- [442_interactions_20261002_04.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_04.tar.gz.dvc), member `evidence/client_interactions_20261002_ui03/chat_03/primary/episode.json`, SHA-256 `b8c8ae5b0c7720b781bb374924f45d764ff4f93d121c7da395355b6eca553809`.
  Checked cases: `chat.say` (chat_send_pass), `chat.yell` (chat_send_pass), `chat.emote` (chat_send_pass), `chat.raid` (chat_send_pass), `chat.raid_warning` (chat_send_pass), `chat.whisper` (chat_send_pass).
- [442_interactions_20261002_04.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_04.tar.gz.dvc), member `evidence/client_interactions_20261002_ui03/chat_03/scout/episode.json`, SHA-256 `2c667f6d1f464d89398de4619c954ae2739835a334f477ff56174ede5a2180d4`.
  Checked cases: `chat.receive.raid` (chat_receive_pass), `chat.receive.raid_warning` (chat_receive_pass), `chat.receive.whisper` (chat_receive_pass).

### logout_reentry

Scout logout countdown cancelled, later completed and reentered through the visible selected character; primary sees offline/online and original resources/equipment/group/profile restored.

Remaining limits: Character creation/deletion and other lifecycle failure variants remain open.

- [442_interactions_20261002_04.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_04.tar.gz.dvc), member `evidence/client_interactions_20261002_ui03/lifecycle_06/scout/episode.json`, SHA-256 `188949c5d63e88ea9b8c39d08adac51dfef9eb1a10916d85c083ba09d5cf8325`.
  Checked cases: `lifecycle.logout_cancel` (logout_cancel_pass), `lifecycle.logout_complete` (logout_complete_pass), `lifecycle.reenter` (reenter_pass).

### guild_membership

Disposable guild invitations declined and accepted, both rosters shown, MOTD delivered to peer, then ordinary leave and native fixture restoration.

Remaining limits: Guild bank/rank permissions, recruitment and larger rosters remain open.

- [442_interactions_20261002_05.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_05.tar.gz.dvc), member `evidence/client_interactions_20261002_ui04/guild_membership_02/primary/episode.json`, SHA-256 `558fc277b3219275dace71dfded918f0924649a037dcdcec185508abdfb3c2e3`.
  Checked cases: `guild.invite` (guild_invite_submitted), `guild.open_roster` (guild_roster_pass), `guild.motd` (guild_motd_pass).
- [442_interactions_20261002_05.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_05.tar.gz.dvc), member `evidence/client_interactions_20261002_ui04/guild_membership_02/scout/episode.json`, SHA-256 `f220f0ef7c03496d229fc6309d98e2a711b93148bd1900985b40fb912acc9d81`.
  Checked cases: `guild.decline` (guild_decline_pass), `guild.accept` (guild_accept_pass), `guild.open_roster` (guild_roster_pass), `guild.leave` (guild_leave_pass).

### guild_open

Classic guild preference enabled through ordinary controls and populated native roster rendered.

Remaining limits: The stock six-tab/eight-tab Lua mismatch still affects Guild Control; this qualifies opening and roster display only.

- [442_interactions_20261002_05.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_05.tar.gz.dvc), member `evidence/client_interactions_20261002_ui04/guild_open_03/episode.json`, SHA-256 `e7c1d62ec684cb7ad81ec3cb904a129a0c619439b5f226a07cfdb6017f788c41`.
  Checked cases: `guild.classic_open` (panel_open_pass), `guild.roster_contents` (guild_roster_pass).

### guild_notes

Public/officer notes use separate native columns; nonempty information saved/refreshed and guild/officer messages reach native.

Remaining limits: Empty information emits no request. Guild Control permission mutations remain blocked by stock XML/Lua mismatch.

- [442_interactions_20261002_05.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_05.tar.gz.dvc), member `evidence/client_interactions_20261002_ui04/guild_notes_02/episode.json`, SHA-256 `7faeeb192614a10f72a2b7656447fe1e6cd3634bce9cc4ea2d2ff62a0fa45a1b`.
  Checked cases: `guild.member_details` (guild_details_pass), `guild.public_note_save` (guild_note_pass), `guild.officer_note_save` (guild_note_pass), `guild.information_save` (guild_info_native_pass), `guild.information_refresh` (guild_info_visible_pass), `guild.chat.guild` (guild_chat_pass), `guild.chat.officer` (guild_chat_pass).

### guild_ranks

Visible promotion/demotion controls change native rank and peer roster; removal reaches native and peer.

Remaining limits: These episodes retain Guild Control Lua errors (ui_clean=false). Bare-name promotion slash command emits no request. Wider rank/permission variants remain open.

- [442_interactions_20261002_06.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_06.tar.gz.dvc), member `evidence/client_interactions_20261002_ui05/guild_commands_06/primary/episode.json`, SHA-256 `f1a22d34a37f82e37e3423fe0e38d6ee3d9229dc617269015838831fcb3d3450`.
  Checked cases: `guild.rank_promote` (guild_rank_pass), `guild.rank_demote` (guild_rank_pass), `guild.remove_member` (guild_remove_pass).
- [442_interactions_20261002_06.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_06.tar.gz.dvc), member `evidence/client_interactions_20261002_ui05/guild_commands_06/scout/episode.json`, SHA-256 `8031711a326e8e885acbaaa16581e31977070f20362bee83035e3530f12fb380`.
  Checked cases: `guild.rank_promote_peer` (guild_rank_peer_pass), `guild.rank_demote_peer` (guild_rank_peer_pass), `guild.remove_member_peer` (guild_remove_peer_pass).

### guild_disband

Ordinary disband confirmation removes the disposable native guild and shows an unguilded leader.

Remaining limits: Other leadership/rank constraints remain open.

- [442_interactions_20261002_06.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_06.tar.gz.dvc), member `evidence/client_interactions_20261002_ui05/guild_disband_01/episode.json`, SHA-256 `276600bec3147d04c8da60ac7f0c62a4ba32302d8d0fbeb57655599f044865a7`.
  Checked cases: `guild.disband` (guild_disband_pass).

### nearby_target

Both owned clients create the native nearby geared player and target the peer by normal exact-name chat input.

Remaining limits: Mouse/tab targeting, enemies and larger groups remain open.

- [442_interactions_20261002_07.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_07.tar.gz.dvc), member `evidence/client_interactions_20261002_ui06/nearby_players_02/primary/episode.json`, SHA-256 `a9a1e006090de63c3b9fcbafac9e6994c83b99fd53a5788617af800899b4b452`.
  Checked cases: `player.target_nearby` (nearby_target_pass).
- [442_interactions_20261002_07.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_07.tar.gz.dvc), member `evidence/client_interactions_20261002_ui06/nearby_players_02/scout/episode.json`, SHA-256 `cf6f74c4d86c4e7edc44a77623b71b0112cac370eab695671d7ec279fdfb8cef`.
  Checked cases: `player.target_nearby` (nearby_target_pass).

### follow

Ordinary strafe/follow/stop with peer position agreement and 11 attributed native/modern movement pairs; both original poses restored.

Remaining limits: Other directions, combat, transports and cross-map follow remain open.

- [442_interactions_20261002_07.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_07.tar.gz.dvc), member `evidence/client_interactions_20261002_ui06/public_follow_02/primary/episode.json`, SHA-256 `b6ebf7c4eaa59b4ac295335bd9c7b72ab6f953708ad4a4f0480640ed7cfc660b`.
  Checked cases: `movement.strafe_public` (movement_pass), `movement.follow_nearby` (follow_pass), `movement.stop_follow` (stop_follow_pass).

### inspect

Both clients inspect the visible peer and sampled equipment agrees with native identity.

Remaining limits: Unsampled slots, PvP/item-level/customizations remain open.

- [442_interactions_20261002_08.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_08.tar.gz.dvc), member `evidence/client_interactions_20261002_ui07/peer_services_03/primary/episode.json`, SHA-256 `aa447b9803de659c4c8ee74a8219654e5f198d6273fd5045792c4f01fbfc9000`.
  Checked cases: `player.inspect_nearby` (inspect_equipment_pass).
- [442_interactions_20261002_08.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_08.tar.gz.dvc), member `evidence/client_interactions_20261002_ui07/peer_services_03/scout/episode.json`, SHA-256 `68ab2e352bf1c8e70bcaf9a526ccafb160831aa9647b97bee38d7ec254c381b6`.
  Checked cases: `player.inspect_nearby` (inspect_equipment_pass).

### trade_cancel

Ordinary cancel closes both owned trade windows.

Remaining limits: Range, permission, inventory and gold error paths remain open.

- [442_interactions_20261002_08.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_08.tar.gz.dvc), member `evidence/client_interactions_20261002_ui07/peer_services_03/primary/episode.json`, SHA-256 `aa447b9803de659c4c8ee74a8219654e5f198d6273fd5045792c4f01fbfc9000`.
  Checked cases: `trade.cancel` (trade_cancel_pass).

### trade_roundtrip

Five-item stack offered, both parties confirm, then the exact stack returns in another normal trade; full native inventories/money and poses restored.

Remaining limits: Gold, enchantment, unaccept, changed offers and bag errors remain open.

- [442_interactions_20261002_08.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_08.tar.gz.dvc), member `evidence/client_interactions_20261002_ui07/trade_roundtrip_02/primary/episode.json`, SHA-256 `38901a2ebc037620ae9e167aebbede479c631631528e020b67f93270d0b84eac`.
  Checked cases: `trade.outbound.open` (trade_open_pass), `trade.outbound.offer` (trade_offer_pass), `trade.outbound.accept_sender` (trade_accept_pass), `trade.return.accept_recipient` (trade_complete_pass).
- [442_interactions_20261002_08.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_08.tar.gz.dvc), member `evidence/client_interactions_20261002_ui07/trade_roundtrip_02/scout/episode.json`, SHA-256 `0679d6c5bd514499823ca6a33a7f5902048991deb616333ca2236a10bc85caf7`.
  Checked cases: `trade.outbound.accept_recipient` (trade_complete_pass), `trade.return.open` (trade_open_pass), `trade.return.offer` (trade_offer_pass), `trade.return.accept_sender` (trade_accept_pass).

### bank

Stock 28-slot base bank opens; existing stack deposited/withdrawn with exact identity/count and UI agreement; full fixture and pose restored.

Remaining limits: Bank bags/slots, split variants, reconnect persistence and negative paths remain open.

- [442_interactions_20261002_09.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_09.tar.gz.dvc), member `evidence/client_interactions_20261002_ui08/bank_roundtrip_01/episode.json`, SHA-256 `c2cdbe04b1a9594afe8604243a1be23c2ba442628386e74374aa79ff07789145`.
  Checked cases: `bank.gossip` (bank_open_pass), `bank.deposit_existing_stack` (bank_transfer_pass), `bank.withdraw_existing_stack` (bank_transfer_pass), `bank.close` (bank_close_pass).

### merchant

All nine native vendor rows display; existing pants sold, bought back and moved to original slot with exact identity/money and pose restoration.

Remaining limits: Individual repair, discounts, stock and negative variants remain open.

- [442_interactions_20261002_10.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_10.tar.gz.dvc), member `evidence/client_interactions_20261002_ui09/merchant_sale_02/episode.json`, SHA-256 `a811157d5743bf82ecf7151f7781579b603a71ac211c8535cf731d82b6d651ea`.
  Checked cases: `merchant.gossip` (service_open_pass), `merchant.sell_existing_pants` (sale_pass), `merchant.buyback.item` (buyback_pass), `merchant.close` (service_close_pass).

### purchase

One five-item water bundle purchased with exact native/public quantity, price and received-item chat; fixture restored.

Remaining limits: Single-item purchase, stock/currency/discount and error paths remain open.

- [442_interactions_20261003_11.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_11.tar.gz.dvc), member `evidence/client_interactions_20261003_ui10/merchant_purchase_04/episode.json`, SHA-256 `3df30263483070cfe021582b94f7adbd66bb544a419df5029e0518c12207cc07`.
  Checked cases: `merchant.buy_bundle` (purchase_pass).

### repair_all

Repair-all quote and native/visible charge agree after isolated opt-in rounding correction; damaged fixture restored.

Remaining limits: Individual/guild repairs, other prices and discounts remain open.

- [442_interactions_20261003_13.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_13.tar.gz.dvc), member `evidence/client_interactions_20261003_ui12/repair_all_03/episode.json`, SHA-256 `1b0f33d31ac0439f1a55fda0f152c64910789133d164c74930468ab42a3d0070`.
  Checked cases: `merchant.repair_all` (repair_all_pass).

### trainer

Warrior learns Parry through stock trainer with native/public learned spell, price and notification agreement, then fixture restored.

Remaining limits: Profession learning/unlearning, rank upgrades and errors remain open.

- [442_interactions_20261003_13.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_13.tar.gz.dvc), member `evidence/client_interactions_20261003_ui12/trainer_learn_02/episode.json`, SHA-256 `088bf9d0b8d920841efa3109439c8e275a86d6c2d85263d5bc33f1c0cbf74672`.
  Checked cases: `trainer.gossip` (service_open_pass), `trainer.learn` (trainer_learning_pass), `trainer.close` (service_close_pass).

### trainer_known_filter

Already Known filter shows and hides all 141 native known Alchemy recipes.

Remaining limits: Available/unavailable filters and new profession learning remain open.

- [442_interactions_20261003_15.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_15.tar.gz.dvc), member `evidence/client_interactions_20261003_ui14/profession_trainer_filters_02/episode.json`, SHA-256 `42c34504bbbb94817481a3ab0a1141e0a68cd1a7594010658e6749d3f5de7219`.
  Checked cases: `trainer.known_filter.show` (trainer_filter_change_pass), `trainer.known_filter.hide` (trainer_filter_change_pass).

### quest_log

Auto-accepted kill quest displayed with native 0/6 objective; log zone expanded, selected and abandoned with exact quest/inventory/money restoration.

Remaining limits: Manual acceptance, progress/rewards, sharing, POIs and other objective types remain open.

- [442_interactions_20261003_14.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_14.tar.gz.dvc), member `evidence/client_interactions_20261003_ui13/quest_details_04/episode.json`, SHA-256 `151fd23a865d052d623486b6ad04eac8dcc5d3d784dc36bf402302f1b1b61eeb`.
  Checked cases: `quests.select_giver_quest` (quest_details_open_pass).
- [442_interactions_20261003_14.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_14.tar.gz.dvc), member `evidence/client_interactions_20261003_ui13/quest_log_02/episode.json`, SHA-256 `6e3116e8ab34f4b47dfd12bd82d953eae3b9f39ab3716d1ddac7c4dee58d4360`.
  Checked cases: `quests.expand_zone` (quest_zone_expand_pass), `quests.select_log_entry` (quest_log_details_pass), `quests.confirm_abandon` (quest_abandon_pass).

### mail_read

Existing native reward catalog displays correct senders, subjects and attachment counts. Disposable plain letter body visually reviewed, read-marked natively and deleted; original mailbox/resources/pose restored.

Remaining limits: COD, HTML/invoices, text-copy, attachment limits and delay/error variants remain open.

- [442_interactions_20261003_15.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_15.tar.gz.dvc), member `evidence/client_interactions_20261003_ui14/mailbox_open_02/episode.json`, SHA-256 `8d0178529d61c9ff391d60e5682977665b23d838c0d2bfa07b31910147c6161f`.
  Checked cases: `mail.open` (mailbox_open_pass), `mail.close` (mailbox_close_pass).
- [442_interactions_20261003_16.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_16.tar.gz.dvc), member `evidence/client_interactions_20261003_ui15/mail_read_delete_01/episode.json`, SHA-256 `ab9bafe8c343252db2d20da5a6d8bbb8dc3647bae936a49775114fb3748bef9c`.
  Checked cases: `mail.read` (mail_read_pass), `mail.delete` (mail_delete_pass).

### mail_collection

Five native water items and exactly 12,345 copper collected from separate disposable letters, with native/public agreement and original mail/inventory/money/pose restored.

Remaining limits: Take-all, COD, gems and limit/error variants remain open.

- [442_interactions_20261003_17.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_17.tar.gz.dvc), member `evidence/client_interactions_20261003_ui16/mail_collect_item_01/episode.json`, SHA-256 `afb9567c379b9c10f3ede392eccaa6ff17b951526462ff2d161b4c847cf9f0df`.
  Checked cases: `mail.collect_item` (mail_collect_pass).
- [442_interactions_20261003_17.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_17.tar.gz.dvc), member `evidence/client_interactions_20261003_ui16/mail_collect_money_01/episode.json`, SHA-256 `e014dec9f844490b678e5d663711563244e0aebf89314f419e42ef80f270efad`.
  Checked cases: `mail.collect_money` (mail_collect_pass).

### player_mail

Real two-account plain sends, return and reply; one-copper attachment returned/collected and exact 30-copper postage charges agree. Rendered bodies reviewed; all native mail/resources and both poses restored.

Remaining limits: Item attachment via player compose, COD, invoices and delay/error paths remain open.

- [442_interactions_20261003_18.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_18.tar.gz.dvc), member `evidence/client_interactions_20261003_ui17/mail_return_04/primary/episode.json`, SHA-256 `0dd24b5f7972a506ed16e1ded97c75798fcb0db1442e2262ef1d737f3a64b58a`.
  Checked cases: `mail.compose` (mail_compose_open_pass), `mail.recipient` (ui_edit_pass), `mail.attach_money` (ui_edit_pass), `mail.send` (mail_send_pass), `mail.take_returned_money` (mail_collect_pass).
- [442_interactions_20261003_18.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_18.tar.gz.dvc), member `evidence/client_interactions_20261003_ui17/mail_return_04/scout/episode.json`, SHA-256 `7a19c6913a61ae9d2ec5a0b6918a8d3949bf34260e93acb8bdf524747fde4219`.
  Checked cases: `mail.return` (mail_return_pass).
- [442_interactions_20261003_18.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_18.tar.gz.dvc), member `evidence/client_interactions_20261003_ui17/mail_reply_01/scout/episode.json`, SHA-256 `0a846b0d02a1482b2bdc7c1d417885ffb044296ec9b226ad9ef77061c6cdcb8f`.
  Checked cases: `mail.reply` (mail_reply_open_pass), `mail.send` (mail_send_pass).

### auction_read

Stock AuctionHouse opens/closes, complete empty browse search for an absent name agrees with native/public response and event.

Remaining limits: Populated browse, categories, filters, sorting/paging and bids remain open.

- [442_interactions_20261003_20.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_20.tar.gz.dvc), member `evidence/client_interactions_20261003_ui19/auction_browse_02/episode.json`, SHA-256 `6e908ce3302245a4327ff8298166a4f918629d9b7820a6196059ccc419e34889`.
  Checked cases: `auction.gossip` (auction_open_pass), `auction.search_name` (ui_edit_pass), `auction.search` (auction_catalog_pass), `auction.close` (auction_close_pass).

### auction_roundtrip

One uninterrupted 14-input run posts plain one-gold pants, displays/selects the populated owned row, cancels through Accept and collects the original GUID into its original slot. Zero quote/native deposit/charge agree for one-copper one-day pants. Complete two-character mail/resources/poses restored without refund.

Remaining limits: Bids/buyouts, stacks/commodities, other fees, suffixes, paging and negative variants remain open.

- [442_interactions_20261003_23.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_23.tar.gz.dvc), member `evidence/client_interactions_20261003_ui22/auction_roundtrip_01/episode.json`, SHA-256 `463c910eb290963fcf7f05c9703982720e151fd836fd9f7ef0cf1a6797a24083`.
  Checked cases: `auction.post` (auction_post_pass), `auction.show_owned` (auction_owned_populated_pass), `auction.select_owned_item_end` (auction_select_owned_pass), `auction.confirm_cancel` (auction_cancel_pass), `auction.collect_return` (auction_return_collect_pass), `auction.restore_slot` (inventory_move_pass).

### archaeology_loop

Historical accepted loop 89 performs six finds at two fresh Outland sites (351 and 363), awards 44 fragments and replaces both sites without manual gameplay interventions or teacher click annotations. Survey instrument bearing/lantern observations drive approaches.

Remaining limits: Bounded two-site proof, using historical Laya identities. Indefinite operation, other races/terrain, solve/keystones, caps and reconnect persistence remain open. New runs use code under current AGENTS.md.

- [442_archaeology_loop_proof_20261002.tar.gz.dvc](../../artifacts/client_harness/442_archaeology_loop_proof_20261002.tar.gz.dvc), member `evidence/laya_archaeology_travel_loop_89/episode.json`, SHA-256 `2b3ce1bc3d87851b49c052a734eeec411af1ff04a8a2692fc45398d1b5187968`.

### manual_quest_controls

Primary warrior manually accepts native Guard Thomas quest 52 through stock UI, reads the correctly named wolf 0/8 and unseen Young Forest Bear 0/5 objectives, collapses/reexpands its zone, cancels abandonment, then abandons it. A separate trial declines without accepting. Native/public quest state and complete quest/inventory/money/pose restoration agree, without fallback cleanup.

Remaining limits: Code-controlled fixture inputs qualify client behavior. Completion and rewards have separately qualified receipts. Sharing, persistence, other questgiver types, eligibility and objective variants remain open.

- [442_interactions_20261003_24.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_24.tar.gz.dvc), member `evidence/client_interactions_20261003_ui23/manual_quest_accept_11/episode.json`, SHA-256 `d0777925ada8a4ae8be930d95b59912ab50136d45872dd53242baa2bc724b386`.
  Checked cases: `quests.manual_accept` (quest_manual_accept_pass), `quests.manual_collapse` (quest_zone_collapse_pass), `quests.manual_abandon_cancel` (quest_abandon_cancel_pass), `quests.manual_read_log` (quest_log_details_pass), `quests.manual_abandon_confirm` (quest_abandon_pass).
- [442_interactions_20261003_24.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_24.tar.gz.dvc), member `evidence/client_interactions_20261003_ui23/manual_quest_decline_12/episode.json`, SHA-256 `56635a814a344dd1d2f7d3d53b2f9d78edfc482b749a7138df0b67781b33b23e`.
  Checked cases: `quests.manual_decline` (quest_manual_decline_pass).

### glyph_socket_panel

Stock glyph panel opens with nine cropped enabled sockets in the correct Major/Minor/Minor/Major/Minor/Major/Prime/Prime/Prime order. Public socket types are 1/2/2/1/2/1/3/3/3; pending Battle independently matches Minor sockets 2/3/5. Native talents/glyphs/inventory/money unchanged in the complete panel readback.

Remaining limits: Other classes and level/locked variants remain open. UI26 socket-position oracle was incorrect and is superseded by the corrected UI27 readback; historical receipts are retained.

- [442_interactions_20261003_28.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_28.tar.gz.dvc), member `evidence/client_interactions_20261003_ui27/glyph_socket_types_11/episode.json`, SHA-256 `310acd68c711cea04f064ee9d2586e7dac044ff14e5c61601a59a9f85e57e6d6`.
  Checked cases: `talents.glyph_open_repaired` (glyph_panel_pass).
- [442_interactions_20261003_28.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_28.tar.gz.dvc), member `evidence/client_interactions_20261003_ui27/glyph_apply_04/episode.json`, SHA-256 `c0ef7ac20d89ab361628d06c8e3d576ff379b07bc43bb3c8599c9676b517b318`.
  Checked cases: `glyphs.select_learned` (glyph_pending_pass).

### available_quest_marker

The level-one scout sees Marshal McBride with a yellow available quest marker after native status 256 is semantically translated to modern 0x400000; reviewed before/after screenshots and captured packets identify the same giver.

Remaining limits: Trivial, incomplete, completed, repeatable, unavailable, tracked and other giver variants remain open.

- [442_interactions_20261003_25.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_25.tar.gz.dvc), member `evidence/client_interactions_20261003_ui24/marker_visual_review.json`, SHA-256 `066daa557f0e7c6fe4c851e0d30188ffca115150e37ebea8031388f1d69d51f1`.

### ordinary_quest_kill_progress

Ordinary melee kills one existing Prowler after manual quest 52 acceptance; native and addon-visible wolf objective counts both advance from 0/8 to 1/8. Normal abandonment restores native quest, inventory, money and pose baselines.

Remaining limits: Fixture teleports do not qualify navigation. This checks one kill objective counter, not progress notification, complete objectives, rewards, other objective types or learned autonomy.

- [442_interactions_20261003_25.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_25.tar.gz.dvc), member `evidence/client_interactions_20261003_ui24/quest_progress_04/episode.json`, SHA-256 `487b5b1539e8acdc484e97b6b732f3528051dd5ae245984615ae1973a8fc9a02`.
  Checked cases: `quests.progress_kill` (quest_progress_pass).

### warrior_talent_allocation

Primary warrior stock Arms selection, one Blitz point preview and confirmation: native tree 746 and spell 80976, public unspent points 41 to 40; learned state persists through ordinary addon reload.

Remaining limits: Other talents/specs/classes, multi-point allocation, reset, dual spec and logout/login persistence remain open. The v34 diagnostic per-tree total was corrected separately; slot positions were not qualified.

- [442_interactions_20261003_26.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_26.tar.gz.dvc), member `evidence/client_interactions_20261003_ui25/talent_learn_01/episode.json`, SHA-256 `8e471cf86b5e8bfa38c45bf165d8f72524999c58d351abbff23cc2338be80e98`.

### warrior_glyph_catalog_search

Complete primary warrior public catalog of 34 glyph IDs/types and three headers, checked against native GlyphProperties. Ordinary Battle search and clearing to the stock Search placeholder restore the catalog.

Remaining limits: Socket panel, Battle learning/application/removal and stock filters have separate qualified receipts. Other glyphs/classes, tooltips, effects and persistence remain open. Catalog type agreement alone does not establish GlyphSlot mapping.

- [442_interactions_20261003_26.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_26.tar.gz.dvc), member `evidence/client_interactions_20261003_ui25/talent_glyph_catalog_02/episode.json`, SHA-256 `2a654b0848ea92421b16ff362beff3a3feb3313d469f199b39ba4d02050c4655`.
- [442_interactions_20261003_26.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_26.tar.gz.dvc), member `evidence/client_interactions_20261003_ui25/talent_glyph_catalog_02/glyph_catalog_review.json`, SHA-256 `b1c89757271a444870323ce1f31eea6a80ad302aaff8de8b1ab2f85db9d540f8`.

### ordinary_quest_melee_completion

One quest 52 run earns five bear and eight wolf kills through ordinary melee against existing creatures. Each attack start and native/public/translated credit matches its victim; 8/5 objectives complete and Guard Thomas shows a visible yellow turn-in question mark.

Remaining limits: The original reward attempt failed its capped XP oracle before claiming; a later earned turn-in is qualified separately. Setup uses native pose staging and does not qualify navigation. Repeated swing cadence, damage values, alive-target stop, ranged/spell combat and other marker categories remain open.

- [442_interactions_20261003_26.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_26.tar.gz.dvc), member `evidence/client_interactions_20261003_ui25/quest_reward_03/episode.json`, SHA-256 `82dbeca029d751b5a8bd5e8bbe2b7d6e9c41ac9df3d46cce95381f51738c1a22`.
- [442_interactions_20261003_26.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_26.tar.gz.dvc), member `evidence/client_interactions_20261003_ui25/quest_reward_03/melee_review.json`, SHA-256 `5345ded64629c637902dd9e8c6d04ed69cb0a151198e860248d67b5fa8536036`.

### glyph_book_learning

An ordinary bag right-click consumes one Glyph of Battle book 43395, learns native spell 58276 and shows Battle known in the stock glyph catalog. Unrelated spells, talents, inventory and money are preserved.

Remaining limits: Only the owned level-85 warrior Battle book is qualified. Obtaining/crafting the book, other glyphs/classes and reload persistence remain open.

- [442_interactions_20261003_28.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_28.tar.gz.dvc), member `evidence/client_interactions_20261003_ui27/glyph_learn_07/episode.json`, SHA-256 `3efc9fef928c4b8e12168bd9a9771d573ac2fd66b9575fb74ca0d70770caf8aa`.
  Checked cases: `glyphs.learn_book` (glyph_learn_pass).

### glyph_minor_application

Ordinary learned Battle selection and Minor socket 2 click apply native glyph 483 and public aura spell 58095. Correct socket types and pending matches agree; learned spells, talents, inventory and money are preserved.

Remaining limits: Only empty Minor socket 2 on the owned level-85 warrior is qualified. Replacement, other sockets/classes, locked/error variants, aura effects and reload persistence remain open.

- [442_interactions_20261003_28.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_28.tar.gz.dvc), member `evidence/client_interactions_20261003_ui27/glyph_apply_04/episode.json`, SHA-256 `c0ef7ac20d89ab361628d06c8e3d576ff379b07bc43bb3c8599c9676b517b318`.
  Checked cases: `glyphs.select_learned` (glyph_pending_pass), `glyphs.application` (glyph_application_pass).

### glyph_minor_removal

Ordinary Shift-right-click and stock Yes confirmation clear Battle from native/public Minor socket 2. Clear Glyph 89964 consumes exactly one Vanishing Powder 64670; learned spells, talents, original inventory/money and fixture permission are restored.

Remaining limits: Only the owned level-85 warrior Battle socket and one staged powder are qualified. Reagent acquisition, other glyphs/classes and insufficient-reagent variants remain open.

- [442_interactions_20261003_28.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_28.tar.gz.dvc), member `evidence/client_interactions_20261003_ui27/glyph_remove_03/episode.json`, SHA-256 `809ad4687e996bf28ece2097baae7280a74e3810fae560c65b89621bffaf2e35`.
  Checked cases: `glyphs.remove_dialog` (glyph_remove_dialog_pass), `glyphs.removal` (glyph_removal_pass).

### earned_quest_reward

Primary level-85 warrior resumes an attributable thirteen-kill quest 52 completion, selects the first stock reward and completes the turn-in. Native and public inventory gain item 57523 once and two potions 858; money gains 640 copper. Native and modern completion packets agree. Earned history, items and money are retained; fixture pose is restored.

Remaining limits: Only this plain-item reward and level-capped turn-in are qualified. XP gain, leveling, other reward choices, currencies, persistence and quest variants remain open. Fixture teleports do not qualify navigation. Historical failed request, cleanup and representation guard receipts remain unchanged.

- [442_interactions_20261003_29.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_29.tar.gz.dvc), member `evidence/client_interactions_20261003_ui28/quest_reward_06/episode.json`, SHA-256 `662df730a997bdd3dab8c398e96cf39f2f035ff604e2cbb3f301a05ac7f5b46e`.
  Checked cases: `quests.reward_interact` (questgiver_open_pass), `quests.reward_select` (quest_turnin_open_pass), `quests.reward_choice` (quest_reward_choice_pass), `quests.reward_confirm` (quest_reward_pass).

### glyph_learned_filters

Stock Already Known and Unavailable checkboxes produce Battle-only, the other 33 glyphs, and the restored complete 34-glyph catalog. Identities, names, types, learned flags and filter settings agree; native spells, talents, glyphs, inventory and money are preserved.

Remaining limits: Only the owned level-85 warrior catalog with Battle learned is qualified. Other classes, empty/fully learned catalogs, persistence and glyph effects remain open. The failed caption trial and separate restoration are retained.

- [442_interactions_20261003_29.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_29.tar.gz.dvc), member `evidence/client_interactions_20261003_ui28/glyph_filters_02/episode.json`, SHA-256 `5daa622d4c8191cdc8f8caab51e74097d618ff4b9891c55023f1a6baba1c56f8`.
  Checked cases: `glyphs.application_open` (talents_open_pass), `glyphs.filter_menu.known_only` (glyph_filter_menu_pass), `glyphs.filter_unknown.known_only` (glyph_filter_pass), `glyphs.filter_menu.unknown_restore` (glyph_filter_menu_pass), `glyphs.filter_unknown.unknown_restore` (glyph_filter_pass), `glyphs.filter_menu.unknown_only` (glyph_filter_menu_pass), `glyphs.filter_known.unknown_only` (glyph_filter_pass), `glyphs.filter_menu.known_restore` (glyph_filter_menu_pass), `glyphs.filter_known.known_restore` (glyph_filter_pass).

### glyph_type_filters

Ordinary stock Prime, Major and Minor header clicks collapse all types then restore them in reverse order, giving 25/8/0/8/25/34 glyphs with exact type/catalog checks. All five filters and original native spells, talents, glyphs, inventory and money are restored.

Remaining limits: Only the owned level-85 warrior catalog is qualified. Other classes, persistence and glyph effects remain open. Catalog types and socket API types have separate identities.

- [442_interactions_20261003_29.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_29.tar.gz.dvc), member `evidence/client_interactions_20261003_ui28/glyph_type_filters_01/episode.json`, SHA-256 `092110d03cf1107c7e49bcc64f20385eccfc7c6d9089c22e44f1707e1e085829`.
  Checked cases: `glyphs.application_open` (talents_open_pass), `glyphs.type_prime.prime_collapse` (glyph_type_filter_pass), `glyphs.type_major.major_collapse` (glyph_type_filter_pass), `glyphs.type_minor.minor_collapse` (glyph_type_filter_pass), `glyphs.type_minor.minor_expand` (glyph_type_filter_pass), `glyphs.type_major.major_expand` (glyph_type_filter_pass), `glyphs.type_prime.prime_expand` (glyph_type_filter_pass).

### minimap_quest_tracking_controls

Ordinary minimap tracking menu clicks enable and disable Low Level Quests. The complete public tracking catalog differs only at that boolean. Quest history, inventory, money, tracking and staged pose return to their exact baselines.

Remaining limits: This UI28 receipt qualifies the menu and setting controls only; its overhead marker was absent and tracked query unmapped. UI29 separately repairs and qualifies that trivial marker. Other tracking categories, minimap icons and persistence remain open.

- [442_interactions_20261003_29.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_29.tar.gz.dvc), member `evidence/client_interactions_20261003_ui28/quest_tracking_01/episode.json`, SHA-256 `a18c0253fb47b0c7ab87aea8b66b5dfcd9e5d93d520de300a821df648bc41cf3`.
  Checked cases: `tracking.menu.enabled` (tracking_menu_pass), `tracking.low_level.enabled` (tracking_filter_pass), `tracking.menu.disabled` (tracking_menu_pass), `tracking.low_level.disabled` (tracking_filter_pass).

### trivial_quest_marker_tracked

Stock Low Level Quests enable/disable shows and hides the reviewed overhead marker on the exact visible Guard Thomas GUID. Both two-GUID tracked requests refresh authoritative native visible status; native 4 and modern 64 agree. Quest history, inventory, money, tracking and staged pose are restored.

Remaining limits: Only this eligible trivial creature on the owned level-85 warrior is qualified. Other eligibility categories, game-object questgivers, minimap pins and retired cached reads remain open. Native 4.3.4 refreshes all visible givers because it has no subset request. Teleport staging does not qualify navigation.

- [442_interactions_20261003_30.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_30.tar.gz.dvc), member `evidence/client_interactions_20261003_ui29/quest_tracking_02/episode.json`, SHA-256 `9ce05fcca7cd96ef74715d1fd7adb99ed6315abea05c4cd493dc07e6dfe0e3f1`.
  Checked cases: `tracking.low_level.enabled` (tracking_filter_pass), `tracking.low_level.disabled` (tracking_filter_pass).
- [442_interactions_20261003_30.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_30.tar.gz.dvc), member `evidence/client_interactions_20261003_ui29/trivial_marker_visual_review.json`, SHA-256 `e9bd965a6bbd49927537b27f30099bfbd57b4aa0f6f0b9a953321f1ee23b8528`.

### reputation_standing_watch_headers

All ten displayed faction standings and native flags match racial/class bases plus saved offsets. Ordinary Stormwind detail and watch show/hide agree with native index 19, total 4165 and rendered green progress 1165/6000. Alliance header collapse/expand hides and restores exact child identities. All faction rows, public catalog, inventory and money are restored.

Remaining limits: Only the owned human warrior catalog, Stormwind watched faction and Alliance header are qualified. Other factions, ranks, thresholds, guild state, at-war controls and persistence remain open. Initial scalar-mask and repeated-detail oracle failures remain unchanged in the archive.

- [442_interactions_20261003_30.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_30.tar.gz.dvc), member `evidence/client_interactions_20261003_ui29/reputation_controls_03/episode.json`, SHA-256 `5a39cc4d976f6e151b1a1f9bbbf402c5d05b5f76899b58983fcc57eaad84e6e2`.
  Checked cases: `reputation.inspect_stormwind` (reputation_standing_pass), `reputation.watch.show` (reputation_watch_pass), `reputation.watch.hide` (reputation_watch_pass), `reputation.header.collapse` (reputation_header_pass), `reputation.header.expand` (reputation_header_pass).
- [442_interactions_20261003_30.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_30.tar.gz.dvc), member `evidence/client_interactions_20261003_ui29/reputation_watch_visual_review.json`, SHA-256 `1fd17cf203e04564ddfa3126ba3df4be1bf59421fb71825b0deef53e502c3e9d`.

### reputation_inactive_roundtrip

Ordinary Stormwind inactive checkbox moves it to Inactive. Stock header navigation reveals its reselected inactive detail and checked control; a second ordinary checkbox click restores Active. Native flags change only at this faction; complete native reputation, public catalog, inventory and money are restored.

Remaining limits: Only Stormwind on the owned level-85 human warrior and the tested destination-header state are qualified. Other factions, multiple inactive rows, persistence and scrollbar variants remain open. Earlier selection assumptions and source-bound recovery remain in the archive.

- [442_interactions_20261003_30.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_30.tar.gz.dvc), member `evidence/client_interactions_20261003_ui29/reputation_inactive_03/episode.json`, SHA-256 `0a4735def3d903bfe29e651f20f050ad0a594d85ddab180c79e9f6e4c0700dff`.
  Checked cases: `reputation.inactive.move` (reputation_inactive_pass), `reputation.inactive_reselect.move` (reputation_standing_pass), `reputation.inactive.restore` (reputation_inactive_pass).

### reputation_watched_reload

Ordinary Stormwind watch survives /reload with native index 19, total 4165 and visible green progress 1165/6000 preserved. Stock hide restores no-watch, all native faction rows, inventory and money.

Remaining limits: Only watched-faction addon reload persistence on the owned level-85 Human warrior. Full-session reconnect and other reputation persistence variants remain open.

- [442_interactions_20261003_31.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_31.tar.gz.dvc), member `evidence/client_interactions_20261003_ui30/reputation_persist_01/episode.json`, SHA-256 `24c1aa0696e469c0ffb262169c378ee786b05e77a390292636a66bbb2c61d275`.
  Checked cases: `reputation.persist_reload` (reputation_persistence_pass).
- [442_interactions_20261003_31.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_31.tar.gz.dvc), member `evidence/client_interactions_20261003_ui30/reputation_outcome_visual_review.json`, SHA-256 `2dcd8468b4c4be843faa462aa710d227d9c13c08d9b985760304ff674df48413`.

### reputation_atwar_neutral_roundtrip

Stock eligible Neutral Booty Bay At War checkbox changes and restores flags 65/67/65. Captured modern uint16 index 1 and native uint32-plus-byte requests agree. Complete native reputation, public catalog, inventory and money are restored; checked/unchecked frames are reviewed.

Remaining limits: Only this eligible faction on the owned Human warrior. Hostile peace restrictions, other reactions and persistence remain open. The original protocol disconnection and source-bound recovery are retained.

- [442_interactions_20261003_31.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_31.tar.gz.dvc), member `evidence/client_interactions_20261003_ui30/reputation_atwar_02/episode.json`, SHA-256 `997f4016f66f0a54dda5cc3b60e7e27d0fd2c3cd5d27189de374bbe914fedc45`.
  Checked cases: `reputation.at_war.change` (reputation_atwar_pass), `reputation.at_war.restore` (reputation_atwar_pass).
- [442_interactions_20261003_31.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_31.tar.gz.dvc), member `evidence/client_interactions_20261003_ui30/reputation_atwar_visual_review.json`, SHA-256 `894814f9a55b7c29dd18155a3d53ac4c50002f76dd1797135a79de6bb249ab05`.

### reputation_earned_positive_negative

Ordinary melee kills an existing Bloodsail Raider. Exact native victim health reaches zero after stock deselection. Native/public standing and packets agree on +5 Booty Bay, -22 Bloodsail and +2 to each other goblin faction. Pose, inventory and money are restored; earned reputation is retained.

Remaining limits: Only this ordinary kill and owned Human warrior. Fixture pose staging does not qualify navigation; corpse loot, other sources/ranks and learned-model autonomy remain open. Earlier death-oracle and loading failures are retained.

- [442_interactions_20261003_31.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_31.tar.gz.dvc), member `evidence/client_interactions_20261003_ui30/reputation_combat_03/episode.json`, SHA-256 `4d14717d628b84d97d81e92a9c5e1b753e74708eae19bc9f9ade1515169047b3`.
  Checked cases: `reputation.combat_target` (reputation_target_pass), `reputation.combat_kill` (reputation_kill_pass).
- [442_interactions_20261003_31.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_31.tar.gz.dvc), member `evidence/client_interactions_20261003_ui30/reputation_outcome_visual_review.json`, SHA-256 `2dcd8468b4c4be843faa462aa710d227d9c13c08d9b985760304ff674df48413`.

### currency_stock_catalog

Stock Currencies tab opens and closes on the owned level-85 Human warrior. Public Justice, Conquest and active Honor IDs, names and zero quantities agree with native saved balances. Justice options open; Dungeon and Raid collapse hides Justice and expand restores the complete semantic catalog. Native currency rows, inventory and money are unchanged.

Remaining limits: Only these zero-balance stock rows, Justice inspection and this category. Other currencies, nonzero amounts, caps, earning/spending and other UI variants remain open. Original Honor-ID and header-oracle failures are retained.

- [442_interactions_20261003_32.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_32.tar.gz.dvc), member `evidence/client_interactions_20261003_ui31/currency_read_03/episode.json`, SHA-256 `ddc2b7f123b8814c2b9be5274d4d24bbf3188d7a518e13387c4440f35316dfaa`.
  Checked cases: `currency.open` (currency_open_pass), `currency.inspect_currency` (currency_inspect_pass), `currency.collapse` (currency_header_pass), `currency.expand` (currency_header_pass), `currency.close` (currency_close_pass).
- [442_interactions_20261003_32.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_32.tar.gz.dvc), member `evidence/client_interactions_20261003_ui31/currency_outcome_visual_review.json`, SHA-256 `4f67e1f6a5551214bac604794a6a77719ebf9af42146fbb5310ae29fe8f29d02`.

### currency_honor_backpack_roundtrip

On the owned level-1 scout, stock Honor Points Show on Backpack enables and renders the watched zero amount in the backpack, then disables. Captured modern uint32 ID/flags and native reversed uint32 flags/ID agree for active Honor 1901 versus native 392. Exact saved flags 0/4/0, complete public/native catalogs, inventory and money restore.

Remaining limits: One zero-balance Honor watch with an initially empty watched list. Three-watch capacity, shift-click, nonzero amounts and other currency variants remain open. The first request-width disconnect and source-bound reentry are preserved.

- [442_interactions_20261003_32.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_32.tar.gz.dvc), member `evidence/client_interactions_20261003_ui31/currency_scout_backpack_02/episode.json`, SHA-256 `ebe6fd02ba5c86b387cd77c01b89f9ed78e81bce49258d60da011a39e1592cdb`.
  Checked cases: `currency.backpack.change` (currency_flag_pass), `currency.backpack.visible` (currency_backpack_visible_pass), `currency.backpack.restore` (currency_flag_pass).
- [442_interactions_20261003_32.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_32.tar.gz.dvc), member `evidence/client_interactions_20261003_ui31/currency_outcome_visual_review.json`, SHA-256 `4f67e1f6a5551214bac604794a6a77719ebf9af42146fbb5310ae29fe8f29d02`.

### currency_honor_watch_reload

Ordinary /reload on the owned level-1 scout retains watched Honor Points, exact native flag 4, identity, equipment, money and group/profile state without Lua errors or blocked actions. Stock disable then restores the complete native/public catalog and inventory/money baseline.

Remaining limits: Watched Honor addon-reload persistence only. Full-session reconnect, other currency mutations and other persistence variants remain open.

- [442_interactions_20261003_32.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_32.tar.gz.dvc), member `evidence/client_interactions_20261003_ui31/currency_scout_backpack_02/episode.json`, SHA-256 `ebe6fd02ba5c86b387cd77c01b89f9ed78e81bce49258d60da011a39e1592cdb`.
  Checked cases: `currency.persist_reload` (currency_persistence_pass), `currency.backpack.restore` (currency_flag_pass).
- [442_interactions_20261003_32.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_32.tar.gz.dvc), member `evidence/client_interactions_20261003_ui31/currency_outcome_visual_review.json`, SHA-256 `4f67e1f6a5551214bac604794a6a77719ebf9af42146fbb5310ae29fe8f29d02`.

### currency_honor_unused_roundtrip

Stock Honor Points Unused checkbox moves the owned level-85 warrior's zero-balance row into Unused, permits ordinary reselection, then restores Player vs. Player placement. Captured modern/native requests agree; exact saved flags 0/8/0, complete native/public catalogs, inventory and money restore.

Remaining limits: One eligible zero-balance Honor currency on this actor. Other currencies, collapsed destination-category reveal, earning/spending, caps and persistence remain open. The original request-width failure is retained.

- [442_interactions_20261003_32.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_32.tar.gz.dvc), member `evidence/client_interactions_20261003_ui31/currency_unused_02/episode.json`, SHA-256 `17127ed939badb0641d7fd8f7cab8d7af4e17d827295857616d309d6c52e3950`.
  Checked cases: `currency.unused.change` (currency_flag_pass), `currency.unused.reselect` (currency_inspect_pass), `currency.unused.restore` (currency_flag_pass).
- [442_interactions_20261003_32.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_32.tar.gz.dvc), member `evidence/client_interactions_20261003_ui31/currency_outcome_visual_review.json`, SHA-256 `4f67e1f6a5551214bac604794a6a77719ebf9af42146fbb5310ae29fe8f29d02`.

### archaeology_current_draenei_project

Stock Draenei race button selects the owned level-85 warrior current project. Native DBC project/spell/name, fragment quantity, cost, zero keystone adjustment and Solve enablement agree with public APIs and the rendered page. Ordinary Escape closes archaeology.

Remaining limits: Current common Draenei project through its race button only. Other races, rare historical-project selection, tooltips and pagination remain open.

- [442_interactions_20261003_33.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_33.tar.gz.dvc), member `evidence/client_interactions_20261003_ui32/archaeology_project_solve_03/episode.json`, SHA-256 `e4fccf89f8609bc0882fdb2fa768110bfc68e8005e3dedb50b225d45a9ee28a8`.
  Checked cases: `archaeology.select_race` (archaeology_project_pass), `archaeology.close.after_solve_history` (archaeology_close_pass).

### archaeology_earned_fragment_solve

One uninterrupted stationary fragment-only Solve of Strange Silver Paperweight, native project 243 and spell 90861, spends exactly 46 earned Draenei fragments (93 to 47), creates item 64443 x1 visible in the ordinary backpack and records exact native/public completion count and timestamp. All old items, other currencies and money are preserved; both completed artifacts render in the stock Completed tab.

Remaining limits: One common Draenei project and archaeology-currency spend. Moving solves, keystones, repeats, rare artifacts, other races/currencies and caps remain open. Both original protocol failures and earned-state recovery remain evidence; this does not qualify learned autonomy.

- [442_interactions_20261003_33.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_33.tar.gz.dvc), member `evidence/client_interactions_20261003_ui32/archaeology_project_solve_03/episode.json`, SHA-256 `e4fccf89f8609bc0882fdb2fa768110bfc68e8005e3dedb50b225d45a9ee28a8`.
  Checked cases: `archaeology.solve_project` (archaeology_solve_pass), `archaeology.artifact_bag` (archaeology_artifact_visible_pass), `archaeology.completed_history.after_solve_history` (archaeology_history_pass).
- [442_interactions_20261003_33.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_33.tar.gz.dvc), member `evidence/client_interactions_20261003_ui32/archaeology_earned_history_inspection_02/episode.json`, SHA-256 `fa36ee2039a9c9c5eb4ed0c3435daecd7c17a4eae70ddf251d35ee9df0e7e9e6`.
  Checked cases: `archaeology.completed_tab` (archaeology_history_inspected).
- [442_interactions_20261003_33.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_33.tar.gz.dvc), member `evidence/client_interactions_20261003_ui32/archaeology_history_alignment_review.json`, SHA-256 `36fab4ac35d78ff942e1ca2a41e1bb516f149413a925cec1bfffd7be00c1b338`.

### archaeology_earned_reload_persistence

Ordinary /reload retains the earned Draenei fragment balance, current project, both crafted items, all native completion counts/first timestamps and complete rendered stock history without Lua errors or blocked actions. UI34 normal menu logout/cancel/completion and reviewed Enter reentry retain all three earned Draenei artifacts, exact native completed counts/first timestamps, current project, 13 fragments and four keystones; complete stock history renders after login.

Remaining limits: Interface reload and one ordinary full-session logout/reentry on the owned level-85 actor. Other races, repeated/rare completions and server-restart persistence remain open.

- [442_interactions_20261003_33.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_33.tar.gz.dvc), member `evidence/client_interactions_20261003_ui32/archaeology_project_solve_03/episode.json`, SHA-256 `e4fccf89f8609bc0882fdb2fa768110bfc68e8005e3dedb50b225d45a9ee28a8`.
  Checked cases: `archaeology.reload_persistence` (archaeology_reload_pass), `archaeology.completed_history.after_reload_history` (archaeology_history_pass).
- [442_interactions_20261003_35.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_35.tar.gz.dvc), member `evidence/client_interactions_20261003_ui34/session_logout_01/episode.json`, SHA-256 `4d6492077afc10016b24148087f651589674a6c79729bc0e712006e8b2909a7d`.
  Checked cases: `lifecycle.logout_cancel` (logout_cancel_pass), `lifecycle.logout_complete` (logout_complete_pass).
- [442_interactions_20261003_35.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_35.tar.gz.dvc), member `evidence/client_interactions_20261003_ui34/session_reenter_01/episode.json`, SHA-256 `0492b5dc32c503c8219ee9aa986d1a1b56167a646d4b910c6acf5a476584ea4e`.
  Checked cases: `lifecycle.reenter` (session_persistence_pass), `archaeology.completed_history.after_reentry_history` (archaeology_history_pass).
- [442_interactions_20261003_35.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_35.tar.gz.dvc), member `evidence/client_interactions_20261003_ui34/session_persistence_review.json`, SHA-256 `67f497647a642d79688375b521527f1f5757d64fc5e2373466577b79d0721e13`.

### archaeology_existing_keystone_solve

Ordinary add, remove and re-add of one existing Draenei Tome on common project 245 shows exact socket/icon and +12 fragment adjustment without native mutation. Stationary Solve sends native currency 398 quantity 34 and keystone 64394 quantity 1; earned fragments 47 to 13, existing stack 5 to 4, one artifact 64444 and exact completed history. All other resources and items preserved.

Remaining limits: One keystone on one common Draenei project only; additional socket counts, other races, rares and repeated completions remain open.

- [442_interactions_20261003_34.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_34.tar.gz.dvc), member `evidence/client_interactions_20261003_ui33/archaeology_keystone_solve_01/episode.json`, SHA-256 `1d16c7381c6fb658ad2e198ccbf9679ba79347b4f3b60740e839c66bca924211`.
  Checked cases: `archaeology.keystone.add` (archaeology_keystone_pass), `archaeology.keystone.remove` (archaeology_keystone_pass), `archaeology.solve_project` (archaeology_solve_pass).
- [442_interactions_20261003_34.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_34.tar.gz.dvc), member `evidence/client_interactions_20261003_ui33/archaeology_keystone_review.json`, SHA-256 `6f507103aeda5551fe0f851115155df2b2d1dea748fab84cf94bbf9578a1cb05`.

### archaeology_completed_project_tooltip

Physical hover over the disabled stock Scepter of the Nathrezim common-artifact button shows the exact native project title, completion count 1 and first-completion date. Public timestamp/count and rendered history match all three legitimate native completed projects; native resources unchanged.

Remaining limits: One common completed Draenei tooltip; rare selection, repeated counts, other races and history pagination remain open.

- [442_interactions_20261003_34.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_34.tar.gz.dvc), member `evidence/client_interactions_20261003_ui33/archaeology_keystone_solve_01/episode.json`, SHA-256 `1d16c7381c6fb658ad2e198ccbf9679ba79347b4f3b60740e839c66bca924211`.
  Checked cases: `archaeology.project_tooltip` (archaeology_tooltip_pass).
- [442_interactions_20261003_34.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_34.tar.gz.dvc), member `evidence/client_interactions_20261003_ui33/archaeology_keystone_review.json`, SHA-256 `6f507103aeda5551fe0f851115155df2b2d1dea748fab84cf94bbf9578a1cb05`.

### archaeology_stationary_solve_cast_bar

Original immediate weighted-Solve frame and public UnitCastingInfo show active spell 90864, matching Scepter of the Nathrezim text, visible stock bar and exact 3000 ms duration. Source-bound review pins the original episode at 899bd592f2, before the later helper, and the captured valid native weighted request.

Remaining limits: Stationary common-project Solve only. Survey cast-bar visibility, cancellation and movement variants remain open; no learned autonomy is qualified.

- [442_interactions_20261003_34.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_34.tar.gz.dvc), member `evidence/client_interactions_20261003_ui33/archaeology_keystone_solve_01/episode.json`, SHA-256 `1d16c7381c6fb658ad2e198ccbf9679ba79347b4f3b60740e839c66bca924211`.
  Checked cases: `archaeology.solve_project` (archaeology_solve_pass).
- [442_interactions_20261003_34.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_34.tar.gz.dvc), member `evidence/client_interactions_20261003_ui33/archaeology_keystone_review.json`, SHA-256 `6f507103aeda5551fe0f851115155df2b2d1dea748fab84cf94bbf9578a1cb05`.

### quest_full_session_persistence

Ordinary full logout/reentry retains active quest 28825 A Personal Summons and rewarded quest 52, with exact saved native quest rows/objectives. Public log entries and headers match before/after; the stock log displays A Personal Summons details after login. All gear, items, money, archaeology and group/profile baselines preserved.

Remaining limits: One active and one rewarded quest on this level-85 actor; broader objective types, timers, quest sharing and server restart remain open.

- [442_interactions_20261003_35.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_35.tar.gz.dvc), member `evidence/client_interactions_20261003_ui34/session_logout_01/episode.json`, SHA-256 `4d6492077afc10016b24148087f651589674a6c79729bc0e712006e8b2909a7d`.
  Checked cases: `quests.session_log` (quest_session_log_pass).
- [442_interactions_20261003_35.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_35.tar.gz.dvc), member `evidence/client_interactions_20261003_ui34/session_reenter_01/episode.json`, SHA-256 `0492b5dc32c503c8219ee9aa986d1a1b56167a646d4b910c6acf5a476584ea4e`.
  Checked cases: `lifecycle.reenter` (session_persistence_pass), `quests.session_log` (quest_session_log_pass).
- [442_interactions_20261003_35.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_35.tar.gz.dvc), member `evidence/client_interactions_20261003_ui34/session_persistence_review.json`, SHA-256 `67f497647a642d79688375b521527f1f5757d64fc5e2373466577b79d0721e13`.

### stock_zone_continent_navigation

Observed M binding opens Badlands map 1418, right-clicking the owned canvas navigates to Eastern Kingdoms 1415, and physical left-click at public Hammertoe digsite coordinates enters Badlands. Bound close/reopen restores the player zone. Native resources/project/history/inventory unchanged; no Lua errors or blocked actions.

Remaining limits: Compact stock map, one outdoor zone and its continent; other worlds/zones, dungeon floors, pan and quest/taxi routes remain open. Original hidden-Zoom-Out-button trial remains failed evidence.

- [442_interactions_20261003_35.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_35.tar.gz.dvc), member `evidence/client_interactions_20261003_ui34/map_navigation_03/episode.json`, SHA-256 `37bf8d3e0391d35fca480f3b0db33dbb96ea9abf1538efcaa90d0a068aa9a7d1`.
  Checked cases: `map.bound_open` (map_navigation_pass), `map.continent_zoom_out` (map_navigation_pass), `map.zone_zoom_in` (map_navigation_pass), `map.bound_close` (map_close_pass), `map.bound_reopen_zone` (map_navigation_pass).
- [442_interactions_20261003_35.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_35.tar.gz.dvc), member `evidence/client_interactions_20261003_ui34/map_navigation_review.json`, SHA-256 `f1fab98c7f1976b87359857e2bbd1335114a790e1b3cb89af81cab09c130bbf0`.

### stock_player_planar_map_coordinates

Public player world XY and normalized Badlands map position match saved native character coordinates and an independent pinned WorldMapArea.dbc rectangle within 0.1 world unit and 0.0001 normalized coordinate. Owned player marker and digsite boundary are visually reviewed in the stock map.

Remaining limits: Planar XY in Badlands only. Public UnitPosition Z returns zero while native Z is 241.668; height, other maps/floors and movement updates remain unqualified.

- [442_interactions_20261003_35.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_35.tar.gz.dvc), member `evidence/client_interactions_20261003_ui34/map_navigation_03/episode.json`, SHA-256 `37bf8d3e0391d35fca480f3b0db33dbb96ea9abf1538efcaa90d0a068aa9a7d1`.
- [442_interactions_20261003_35.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_35.tar.gz.dvc), member `evidence/client_interactions_20261003_ui34/map_navigation_review.json`, SHA-256 `f1fab98c7f1976b87359857e2bbd1335114a790e1b3cb89af81cab09c130bbf0`.

### stock_owned_continent_digsite_overlay

Eastern Kingdoms exposes four unique owned public research-site IDs, blobs and positions. Stock Show Digsites checkbox removes/restores exactly four visible shovel icons whose names match every public site. Normal left-click enters the current site zone and its rendered blob boundary. Original display preference and all native resources are preserved.

Remaining limits: Four current Eastern Kingdoms sites and one Badlands blob; other continents, rotated site sets, boundary geometry gameplay and fragment caps remain separate variants.

- [442_interactions_20261003_35.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_35.tar.gz.dvc), member `evidence/client_interactions_20261003_ui34/map_navigation_03/episode.json`, SHA-256 `37bf8d3e0391d35fca480f3b0db33dbb96ea9abf1538efcaa90d0a068aa9a7d1`.
  Checked cases: `map.digsites_False` (map_digsite_overlay_pass), `map.digsites_True` (map_digsite_overlay_pass), `map.zone_zoom_in` (map_navigation_pass).
- [442_interactions_20261003_35.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_35.tar.gz.dvc), member `evidence/client_interactions_20261003_ui34/map_navigation_review.json`, SHA-256 `f1fab98c7f1976b87359857e2bbd1335114a790e1b3cb89af81cab09c130bbf0`.

### stock_reversible_minimap_zoom

Physical clicks on observed stock minimap button rectangles change public zoom from zero to one and back to zero, retaining the six-level public zoom catalog and every native resource. Both zoom frames are visually reviewed.

Remaining limits: Adjacent zoom levels zero/one on this owned outdoor actor; max-level disablement, other levels and minimap services remain open.

- [442_interactions_20261003_35.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_35.tar.gz.dvc), member `evidence/client_interactions_20261003_ui34/map_navigation_03/episode.json`, SHA-256 `37bf8d3e0391d35fca480f3b0db33dbb96ea9abf1538efcaa90d0a068aa9a7d1`.
  Checked cases: `map.minimap_zoom.change` (minimap_zoom_pass), `map.minimap_zoom.restore` (minimap_zoom_pass).
- [442_interactions_20261003_35.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_35.tar.gz.dvc), member `evidence/client_interactions_20261003_ui34/map_navigation_review.json`, SHA-256 `f1fab98c7f1976b87359857e2bbd1335114a790e1b3cb89af81cab09c130bbf0`.

### stock_equipped_item_tooltip_identity

Stock pointer hovers on the native equipped head, cloak and two-handed sword show exact item names and links for 78688, 77097 and 78478 with their expected owner frames. Rendered frames reviewed; full native inventory, money, archaeology, talents, glyphs and spells unchanged.

Remaining limits: Three slots and this warrior only; effective stats, all tooltip lines and account appearance collection remain open. Observer reads only 16 of 29 helmet lines and partly obscures its heading; public stock text checks its full name.

- [442_interactions_20261003_36.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_36.tar.gz.dvc), member `evidence/client_interactions_20261003_ui35/equipment_tooltips_01/episode.json`, SHA-256 `888cd850c0680e351f449d0f33bd29456ad3db4c829dd51c37e42df6e49c35da`.
  Checked cases: `character.equipment_tooltip.CharacterHeadSlot` (stock_tooltip_pass), `character.equipment_tooltip.CharacterBackSlot` (stock_tooltip_pass), `character.equipment_tooltip.CharacterMainHandSlot` (stock_tooltip_pass).
- [442_interactions_20261003_36.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_36.tar.gz.dvc), member `evidence/client_interactions_20261003_ui35/tooltip_review.json`, SHA-256 `583e0d9194fa124df730f7b3150c7233164bfa35a36a0a0d391af83e2a98999e`.

### stock_learned_battle_glyph_tooltip

Ordinary search and pointer hover on the already learned Battle glyph show the stock Glyph of Battle minor tooltip matching native GlyphProperties 483/aura 58095/learned spell 58276. Fresh whole trial restores search and closes the stock window normally; full native baseline unchanged and rendered tooltip reviewed.

Remaining limits: Learned Battle catalog tooltip only; replacement and effects remain open. Original search-focus cleanup failure stays failed, with a separate source-bound cleanup receipt and a fresh successful trial.

- [442_interactions_20261003_36.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_36.tar.gz.dvc), member `evidence/client_interactions_20261003_ui35/glyph_tooltip_02/episode.json`, SHA-256 `aa4d6b87ce30668db928a7d334591cd428064dd17364fc868bca163246c43f5a`.
  Checked cases: `talents.glyph_tooltip` (stock_tooltip_pass), `glyphs.tooltip_search_restore` (ui_edit_pass), `glyphs.tooltip_close` (glyph_panel_closed).
- [442_interactions_20261003_36.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_36.tar.gz.dvc), member `evidence/client_interactions_20261003_ui35/tooltip_review.json`, SHA-256 `583e0d9194fa124df730f7b3150c7233164bfa35a36a0a0d391af83e2a98999e`.

### stock_equipment_set_creation

Normally create the stock HarnessUI36 equipment set for the owned geared warrior. Native GUID assignment and all 19 native slots match the current inventory; public catalog shows the one equipped set and the stock manager rendering is reviewed. Full normal logout/reentry preserves the first created set; a second fresh creation also passes and restores the original collapsed sidebar.

Remaining limits: Owned human warrior, ASCII set and catalog variants only. Save/use/delete are separately qualified by stock_equipment_set_roundtrip. Specialization assignment, cosmetic/appearance sets, larger catalogs and full-inventory failure variants remain open.

- [442_interactions_20261003_37.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_37.tar.gz.dvc), member `evidence/client_interactions_20261003_ui36/equipment_sets_create_02/episode.json`, SHA-256 `e76f7a0d18063e9e2b0e83094621dbdd29be64b0df4ef368426b3ecd71d6a38b`.
  Checked cases: `character.equipment_set_create` (equipment_set_create_pass).
- [442_interactions_20261003_37.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_37.tar.gz.dvc), member `evidence/client_interactions_20261003_ui36/equipment_sets_create_03/episode.json`, SHA-256 `fc8ceebf84110c30c17c63715d338806c635870a10b4fbff94ffbed66d2ac5e4`.
  Checked cases: `character.equipment_set_create` (equipment_set_create_pass).
- [442_interactions_20261003_37.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_37.tar.gz.dvc), member `evidence/client_interactions_20261003_ui36/equipment_creation_review.json`, SHA-256 `eb0c4164bb3b4589351796dbdc72870d00d03bc73e3470e6f6b89cee5fa0d633`.
- [442_interactions_20261003_37.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_37.tar.gz.dvc), member `evidence/client_interactions_20261003_ui36/equipment_creation_repeat_review.json`, SHA-256 `38cfc97ceea8d010b5bf6641bcc5f64f8e02468349d465136b688c58163aca10`.
- [442_interactions_20261003_37.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_37.tar.gz.dvc), member `evidence/client_interactions_20261003_ui36/equipment_set_reenter_02/episode.json`, SHA-256 `bd949907a3782f9e52011a57b937f5e571d05a04ca0162bcd0415b00c90e30f6`.
- [442_interactions_20261003_37.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_37.tar.gz.dvc), member `evidence/client_interactions_20261003_ui36/equipment_session_review.json`, SHA-256 `46e4eb487f5e1ac73722db60ea38e5de89ee13c58668e0e2b5a0a47e73e22062`.

### stock_equipment_set_roundtrip

Normally created owned set GUID 2: stock Change Name/Icon to HarnessSaved, native and public name/item identities, reload persistence; ordinary helmet displacement, stock Equip restores all gear/resources; stock delete confirmation clears native/public catalogs and survives reload. Full successful root restores layout/resources, and a source-bound inspection confirms the empty rendered manager.

Remaining limits: One level-85 human warrior, one ASCII set, one displaced helmet on bridge 715ee470/build60895. Larger catalogs, specialization assignment, cosmetic sets, cancellation and full-bag failure variants remain open. Prior failed roots do not qualify this lifecycle. Immediate equip frame precedes rendering; following deletion-dialog frame confirms restored gear.

- [442_interactions_20261003_38.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_38.tar.gz.dvc), member `evidence/client_interactions_20261003_ui37/equipment_set_roundtrip_05/episode.json`, SHA-256 `4eed6a4cfff2b1e85ba059727806ccf1278acf0937d266151a55b3eb65e87064`.
  Checked cases: `character.equipment_set_save` (equipment_set_save_pass), `character.equipment_set_equip` (equipment_set_equip_pass), `character.equipment_set_delete` (equipment_set_delete_pass).
- [442_interactions_20261003_38.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_38.tar.gz.dvc), member `evidence/client_interactions_20261003_ui37/equipment_empty_02/episode.json`, SHA-256 `2dd09e2b4133ca1a6099bc28b3f4c110f98bd8885595ec79873946920d07d43c`.
- [442_interactions_20261003_38.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_38.tar.gz.dvc), member `evidence/client_interactions_20261003_ui37/equipment_roundtrip_packet_review.json`, SHA-256 `fd60f3dbbfebf137e6c4feb0252dfdfba9f44a5f597117ef70711b10983c575c`.
- [442_interactions_20261003_38.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_38.tar.gz.dvc), member `evidence/client_interactions_20261003_ui37/equipment_roundtrip_render_review.json`, SHA-256 `1c830f3baec3f06f662feb54760cef7ea43860f85280b88e7615164d5744952f`.

### stock_twohand_weapon_swap

Normal backpack right-click exchanges owned Worn Greatsword49778 and Gurthalak78478, then reverses the exact item GUIDs. Public equipment/bag slots, native resources and rendered strength/armor/health/damage changes agree; original full fixture and sidebar restored. Actual modern40ff2cff2c/nativeff20 requests captured for both swaps.

Remaining limits: One owned human warrior and two two-hand swords with empty offhand. One-hand/offhand pairs, bag pressure, class/level restrictions, combat changes and failure variants remain open.

- [442_interactions_20261003_39.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_39.tar.gz.dvc), member `evidence/client_interactions_20261003_ui38/weapon_swap_01/episode.json`, SHA-256 `cb2516f042c70972465ec332fef4b8a6fe0fa4fab36f8112941993b00d56b75f`.
  Checked cases: `weapon.character.open` (character_open_pass), `weapon.backpack` (backpack_open_pass), `character.weapon_swap` (weapon_swap_pass), `character.stats.alternate_weapon` (character_stats_pass), `weapon.restore` (weapon_swap_pass), `character.stats.original_weapon` (character_stats_pass).
- [442_interactions_20261003_39.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_39.tar.gz.dvc), member `evidence/client_interactions_20261003_ui38/weapon_swap_review.json`, SHA-256 `4886fa148a6d3c22e3233bb4de74f64645e171839c0451c2f0ae159563440be1`.

### stock_geared_visibility_roundtrip

Fresh whole stock Show Helm/Show Cloak trial hides and shows both equipped items. All four paired stock character/world renders reviewed; exact requests00->00 and80->01, native flags1024/0/2048/0 and Classic PlayerFlagsEx128/0/256/0 match. Full native resources, original visibility, search, panels and model camera restored. Three normal logout/reentry phases preserve hidden world/API settings and restore both original flags/resources. Paired character-selection bare-head/helmet models reviewed; selection0xc00/0 masks and all19 gear slots match native state.

Remaining limits: One geared human warrior and stock controls. Sword partially occludes rear world cloak. Rear selection cloak rendering, other models/customizations, unrelated login flags and arbitrary bindings remain open. Failed roots and source-bound recovery do not qualify normal behavior.

- [442_interactions_20261003_39.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_39.tar.gz.dvc), member `evidence/client_interactions_20261003_ui38/character_visibility_02/episode.json`, SHA-256 `d78beb105316f8728dd5246cf742cfad4f12362177c7bad65ee3b82c363ef7f5`.
  Checked cases: `character.display_helm` (character_appearance_pass), `appearance.restore.helm` (character_appearance_pass), `character.display_cloak` (character_appearance_pass), `appearance.restore.cloak` (character_appearance_pass).
- [442_interactions_20261003_39.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_39.tar.gz.dvc), member `evidence/client_interactions_20261003_ui38/character_visibility_review.json`, SHA-256 `a6cda1075d07c550bd0eae4c91213f25e15778608f831e782abc3c4672198e3d`.
- [442_interactions_20261003_40.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_40.tar.gz.dvc), member `evidence/client_interactions_20261003_ui39/visibility_session_01/cohort.json`, SHA-256 `c2b3468af214d693016baa2fdbbef2c5cd5eb10b35f02f8462933ca310941ae3`.
- [442_interactions_20261003_40.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_40.tar.gz.dvc), member `evidence/client_interactions_20261003_ui39/visibility_session_hidden_logout_01/episode.json`, SHA-256 `d1bf3075230c94aebc5877575be1387dbee6412461c68d6f8462b527d126a7c4`.
  Checked cases: `character.selection_visibility.hidden` (character_selection_wire_pass).
- [442_interactions_20261003_40.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_40.tar.gz.dvc), member `evidence/client_interactions_20261003_ui39/visibility_session_restored_logout_01/episode.json`, SHA-256 `e8b5ffe091c032e4413c0ff70171c957bfa11ef6dda9bd2886d839abe216765b`.
  Checked cases: `character.visibility_reentry.hidden` (appearance_session_pass), `character.selection_visibility.restored` (character_selection_wire_pass).
- [442_interactions_20261003_40.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_40.tar.gz.dvc), member `evidence/client_interactions_20261003_ui39/visibility_session_finished_01/episode.json`, SHA-256 `01e1866f446f3009c3943815d645f47e827334cbcef7c0c2642e8a3e480b2047`.
  Checked cases: `character.visibility_reentry.restored` (appearance_session_pass).

### stock_owned_sword_comparison

Ordinary private Shift-hover on owned backpack Worn Greatsword renders its tooltip and Currently Equipped Gurthalak tooltip with exact native item IDs/names. Whole trial preserves all native resources and panels. Shift release is verified and hides the comparison; full frame reviewed.

Remaining limits: One human warrior, two two-hand swords, empty offhand and original automatic comparison false. Numeric comparison deltas, all tooltip lines, offhand/two-comparison variants and CVar mutation remain open. Observer captures16 of20 comparison lines.

- [442_interactions_20261003_40.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_40.tar.gz.dvc), member `evidence/client_interactions_20261003_ui39/item_comparison_01/episode.json`, SHA-256 `4bfa967fc815afb8811aa5270b9cd93f92a5dfdf9c2dd6510dd2a760bc83cacb`.
  Checked cases: `character.compare_items` (stock_item_comparison_pass).
- [442_interactions_20261003_40.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_40.tar.gz.dvc), member `evidence/client_interactions_20261003_ui39/item_comparison_review.json`, SHA-256 `8011e47e02f64f675301ffe7b304cb595e0447d67d6e26206440a45358991f95`.

### stock_spellbook_navigation

Both owned human warriors (levels85 and1) navigate General pages1->2->1 and the first Arms/Fury/Protection pages through ordinary stock controls. Rendered names and public slots agree; learned rows belong to the exact native login known-spell packet, including default spells. Active and passive tooltips show the native-known identity. Sixteen exact phase frames are reviewed. Full inventory, money, persisted spells and original book category/pages restore; the two private HDMI-1 sessions overlap by101.7 seconds and all spellbook observations send no input.

Remaining limits: Sampled warrior pages and two tooltip variants only. Other classes, pet/profession tabs, unsampled pages/ranks, drag/cast/learn/unlearn and future guild-perk trainer labels remain open. Initial SQL-only oracle failures remain archived and unqualified.

- [442_interactions_20261004_44.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_44.tar.gz.dvc), member `evidence/client_interactions_20261004_ui43/primary_spellbook_navigation_02/episode.json`, SHA-256 `3f2520ecdf2bb811c3e4070ef4c2594e4cdbe074aee4f65c6b8baa5e00f18f5d`.
  Checked cases: `spellbook.general_tab` (spellbook_navigation_pass), `spellbook.next_page` (spellbook_navigation_pass), `spellbook.previous_page` (spellbook_navigation_pass), `spellbook.spell_tooltip` (spellbook_tooltip_pass), `spellbook.passive_tooltip` (spellbook_tooltip_pass), `spellbook.class_tab.2` (spellbook_navigation_pass), `spellbook.class_tab.3` (spellbook_navigation_pass), `spellbook.class_tab.4` (spellbook_navigation_pass).
- [442_interactions_20261004_44.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_44.tar.gz.dvc), member `evidence/client_interactions_20261004_ui43/scout_spellbook_navigation_02/episode.json`, SHA-256 `8e5db928c77186746e5b96504c3d8b2bfc6e4cdb71c46670e6c7da266a532293`.
  Checked cases: `spellbook.general_tab` (spellbook_navigation_pass), `spellbook.next_page` (spellbook_navigation_pass), `spellbook.previous_page` (spellbook_navigation_pass), `spellbook.spell_tooltip` (spellbook_tooltip_pass), `spellbook.passive_tooltip` (spellbook_tooltip_pass), `spellbook.class_tab.2` (spellbook_navigation_pass), `spellbook.class_tab.3` (spellbook_navigation_pass), `spellbook.class_tab.4` (spellbook_navigation_pass).
- [442_interactions_20261004_44.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_44.tar.gz.dvc), member `evidence/client_interactions_20261004_ui43/spellbook_navigation_after_review.json`, SHA-256 `dc8c2a18a6abea4e30f85cad139d8e04212fd09d3e2f4efaa992469bd4eeb661`.

### stock_spellbook_profession_catalog

Open the stock professions tab on the trained level85 and untrained level1 human warriors. The trained six profession names, rendered rank text and bars match native skill rows; the untrained actor shows six placeholders. Both complete trials restore the original book layout, native inventory, money, skills and saved spells.

Remaining limits: These two profession catalogs only. Pet tabs, other classes and profession mutations remain open. Initial premature-tab verdicts remain failed.

- [442_interactions_20261004_45.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_45.tar.gz.dvc), member `evidence/client_interactions_20261004_ui45/primary_professions_02/episode.json`, SHA-256 `6f16d46d9251d61d90f5faaca6fd01cf97dfcee098209070008cb44af216e0fc`.
- [442_interactions_20261004_45.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_45.tar.gz.dvc), member `evidence/client_interactions_20261004_ui45/scout_professions_02/episode.json`, SHA-256 `3c372c8c54b801447066a1ef938b3bef2a49ed9cbb49b1725076e6c45e73d7c7`.
- [442_interactions_20261004_45.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_45.tar.gz.dvc), member `evidence/client_interactions_20261004_ui45/profession_visual_review.json`, SHA-256 `a1a90d5db4385a67d1423eec3c5061aced93ef1d411c225e4e831de5947ec3e6`.

### stock_spellbook_action_roundtrip

On the level85 and level1 human warriors, physically drag native-known Auto Attack from the observed stock book button to empty visible ActionButton12 (slot84/native83). Public action state, exact native action writes and saved character_action rows agree. Shift-drag removes the action into a carried cursor; an ordinary right-click cancels it. Both complete trials restore saved action rows, book layout, native inventory, money and saved spells.

Remaining limits: One empty slot and one spell on two warrior fixtures; save-backed persistence does not qualify reconnect persistence, other bars or action types. Failed trials and their cleanup defects remain failed.

- [442_interactions_20261004_45.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_45.tar.gz.dvc), member `evidence/client_interactions_20261004_ui45/scout_spellbook_actions_03/episode.json`, SHA-256 `233c1e4fa90df0d8210b62d56e32a9945f50de97abef2eec55dff1d981bba03e`.
  Checked cases: `spellbook.drag_to_bar` (spellbook_drag_pass).
- [442_interactions_20261004_45.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_45.tar.gz.dvc), member `evidence/client_interactions_20261004_ui45/primary_spellbook_actions_04/episode.json`, SHA-256 `e7286ab09f8a91490b3b828771d8ae9cdca6edbf586b200084b66608ecbe76f8`.
  Checked cases: `spellbook.drag_to_bar` (spellbook_drag_pass).
- [442_interactions_20261004_45.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_45.tar.gz.dvc), member `evidence/client_interactions_20261004_ui45/spellbook_actions_visual_review.json`, SHA-256 `12b43d5d27a5c81599ecf8a676e145560f629af77e6ef45476e731368f5257ef`.

### stock_spellbook_battle_shout_cast

Right-click native-known Battle Shout (6673) on the primary level85 warrior Fury book page. Native SMSG_SPELL_GO identifies caster1 and spell6673, the public aura appears, no native cast failure or Lua error occurs, and normal /cancelaura restores the original buff set. The complete action trial also restores book layout, bars, inventory, money and saved spells.

Remaining limits: One reversible instant self-cast on one warrior. Other spells, classes, targets, learning, unlearning and rank transitions remain open. Earlier partial action trials remain unqualified.

- [442_interactions_20261004_45.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_45.tar.gz.dvc), member `evidence/client_interactions_20261004_ui45/primary_spellbook_actions_04/episode.json`, SHA-256 `e7286ab09f8a91490b3b828771d8ae9cdca6edbf586b200084b66608ecbe76f8`.
  Checked cases: `spellbook.cast_spell` (spellbook_cast_pass).
- [442_interactions_20261004_45.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_45.tar.gz.dvc), member `evidence/client_interactions_20261004_ui45/spellbook_actions_visual_review.json`, SHA-256 `12b43d5d27a5c81599ecf8a676e145560f629af77e6ef45476e731368f5257ef`.

### stock_display_controls

On both idle human warrior fixtures, use the observed stock bindings to show a positive numeric FPS display and restore it, save one valid 1280x720 game-generated JPEG, and hide then restore the complete HUD while the world remains rendered. Complete trials preserve native inventory, money and saved spells. Exact PNG and JPEG frames receive visual and archive digest review.

Remaining limits: These stock bindings on two idle fixtures only. Other graphics settings, performance thresholds, cinematics and movies remain open. Scout observer64 reload timeout remains failed; separate read-only verification establishes the installed version and preserved baseline.

- [442_interactions_20261004_46.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_46.tar.gz.dvc), member `evidence/client_interactions_20261004_ui46/primary_display_01/episode.json`, SHA-256 `bdb197bfa1f855bd12c972a58520f4c390ebc0dc822ee2b5a39304b1fd5192c0`.
- [442_interactions_20261004_46.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_46.tar.gz.dvc), member `evidence/client_interactions_20261004_ui46/scout_display_01/episode.json`, SHA-256 `633689341f841dcd6559aac671573f4e33ad92eef86a0073afb221b7f8d928bd`.
- [442_interactions_20261004_46.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_46.tar.gz.dvc), member `evidence/client_interactions_20261004_ui46/display_visual_review.json`, SHA-256 `0631938abb0051f077b138a09cedfd832380d72ffd8aefd6f040986b7b8966e9`.

### stock_dressup_sword_preview

On the geared primary human warrior, ordinary Ctrl-click previews equipped Gurthalak78478 and backpack Worn Greatsword49778 in the stock dressing room. Geometry-ready frames show the exact sword change. Stock right and left arrows change and restore public facing; Reset renders the original appearance again; Close removes the window. Native equipment, inventory, money, currencies, archaeology, talents, glyphs and saved spells remain unchanged.

Remaining limits: Two swords on one idle warrior only. Other item types, model frames, races and classes remain open. Primary dressup01/02 failures remain unqualified; dressup03 is also unqualified because visual review rejected its blank reset frame despite machine completion. Only dressup04 receives qualification.

- [442_interactions_20261004_47.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_47.tar.gz.dvc), member `evidence/client_interactions_20261004_ui47/primary_dressup_04/episode.json`, SHA-256 `02f68849f2cdfa32978b4b3ecdd7d02b1ba0b236f56e85df83e1f439897e7391`.
  Checked cases: `ui_misc.dressup_open` (stock_dressup_preview_pass), `ui_misc.dressup_item` (stock_dressup_preview_pass), `ui_misc.dressup_rotate.right` (stock_dressup_rotation_pass), `ui_misc.dressup_rotate.left` (stock_dressup_rotation_pass), `dressup.reset` (stock_dressup_reset_pass), `ui_misc.dressup_close` (stock_dressup_close_pass).
- [442_interactions_20261004_47.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_47.tar.gz.dvc), member `evidence/client_interactions_20261004_ui47/dressup_visual_review.json`, SHA-256 `6013c53929f042b3669d534806f067d1e198e68728d52e49a4915d2fb4cf2c27`.

### stock_achievement_selection_tracking

On the owned level1 scout, select stock General category92 and compare six visible achievement names, point values and earned membership against the native Achievement DBC and character tables. Select unearned Level10 achievement6, check Track and observe its checked box, public tracked ID and Objectives row; uncheck it and observe their removal. Collapse selection, restore the original Summary layout, and close. Native earned/progress tables, inventory, money and saved spells remain unchanged.

Remaining limits: Six General rows and one unearned tracked achievement on one scout only. Summary earned-row contents, search, achievement tooltips, comparison, progress mutation, earned notifications and reconnect persistence remain open. Earlier scout01 restoration failure and its cleanup-only episode do not qualify operations.

- [442_interactions_20261004_47.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_47.tar.gz.dvc), member `evidence/client_interactions_20261004_ui47/scout_achievements_02/episode.json`, SHA-256 `73f5e06267ac701b6bfe2e8c007b4f0811ea851014353f29649c5de188d61f7d`.
  Checked cases: `achievements.category` (stock_achievement_category_pass), `achievements.achievement` (stock_achievement_selection_pass), `achievements.track` (stock_achievement_tracking_pass), `achievements.untrack` (stock_achievement_tracking_pass).
- [442_interactions_20261004_47.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_47.tar.gz.dvc), member `evidence/client_interactions_20261004_ui47/achievement_visual_review.json`, SHA-256 `c794c3d66d74d6dd4192eb66dd6a293632fe508318645e8cb99e894d9066cf95`.

### stock_actionbar_paging

On both idle human warrior fixtures, the installed next/previous and direct numbered-page bindings change the stock main bar between pages1 and2. All12 public slot assignments match native saved action rows for the active spec and effective stance page, including the primary learned mount32235 exposed as a companion action with its native mounted-aura contract. The original page, every slot assignment, native action rows, inventory, money and saved spells restore.

Remaining limits: Pages1/2 on two idle warriors only. Other pages, classes, combat, extra bars, items, macros and vehicle/pet/override bars remain open. Both page01 missing-binding preflights and primary page02 companion-type oracle failure stay failed and unqualified. Only primary page03 and scout page02 qualify this mapping.

- [442_interactions_20261004_48.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_48.tar.gz.dvc), member `evidence/client_interactions_20261004_ui48/primary_pages_03/episode.json`, SHA-256 `8a1dae2fd4ea9cb2825e11e44c3a19ec5c862e4dc55afc739d8de0ee354df381`.
- [442_interactions_20261004_48.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_48.tar.gz.dvc), member `evidence/client_interactions_20261004_ui48/scout_pages_02/episode.json`, SHA-256 `36cda97c02670cffa478df24642af78ad2414c210e73bd21916eeff075933ded`.
- [442_interactions_20261004_48.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_48.tar.gz.dvc), member `evidence/client_interactions_20261004_ui48/paging_visual_review.json`, SHA-256 `efeedc53ce26bad78a8f31836db9032d908f327d95041e971f54450b6b92ce2b`.

### stock_camera_zoom_latency

On both idle owned warriors, one installed wheel-up camera step decreases public distance by1 and the inverse step returns it exactly to the baseline, without moving the character. Ordinary hover over the stock main-menu microbutton renders home/world0ms latency lines matching the fresh public GetNetStats event and exact stock format. Both complete trials restore camera distance, panels, native inventory, money and saved spells, and receive exact-frame visual review.

Remaining limits: One unclamped zoom pair and stock latency format on two local fixtures only. Camera presets/reset, remote latency accuracy, performance thresholds and disconnection notifications remain open. Scout camera/latency01 stays failed because its observer helper discarded two latency return values; only primary01 and scout02 qualify this mapping. Observer reload timeouts stay failed with separate read-only installed-version/baseline verification.

- [442_interactions_20261004_48.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_48.tar.gz.dvc), member `evidence/client_interactions_20261004_ui48/primary_camera_latency_01/episode.json`, SHA-256 `428ea09ca445d48cd5d4eb35189b0ed7a19c4a706d4d4fb050b2ffacfac2f83a`.
- [442_interactions_20261004_48.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_48.tar.gz.dvc), member `evidence/client_interactions_20261004_ui48/scout_camera_latency_02/episode.json`, SHA-256 `ed958caa6382ac6ca5bba99445fb87149f9afa327d7c818ce8a6b7c75403bb61`.
- [442_interactions_20261004_48.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_48.tar.gz.dvc), member `evidence/client_interactions_20261004_ui48/camera_latency_visual_review.json`, SHA-256 `965a731b6381edb0005ae65eb69b1471922aa0d9a80ce3cbe23081285cb94b82`.

### stock_boolean_settings_roundtrip

On both owned idle human warriors, open stock Settings, use its ordinary search field to find Auto Loot, Lock Action Bars and Enable Sound, click each observed checkbox once and reverse it. Exact public CVars and Settings values agree with each visible checkbox. Restore original empty search, Controls category and all17 observed settings, close Settings and the game menu, and preserve native inventory, money and saved spells. Eighteen exact frames receive visual review.

Remaining limits: Three boolean settings on two fixtures only. Audio output and volumes, Apply/Cancel/defaults, other settings and reconnect persistence remain open. Both failed01 attempts, cleanup-only episodes and scout observer71 reload timeout stay unqualified; a separate read-only episode verifies the late installed observer without repeating reload.

- [442_interactions_20261004_49.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_49.tar.gz.dvc), member `evidence/client_interactions_20261004_ui49/primary_booleans_02/episode.json`, SHA-256 `7fd2c6c32ab5b41c062370c0795e6b5e36832259011669be2e763ff0b54b54f6`.
  Checked cases: `settings.inspect_menu` (panel_open_pass), `settings.inspect_open` (panel_open_pass), `settings.auto_loot.search` (ui_edit_pass), `settings.auto_loot.change` (stock_boolean_setting_pass), `settings.auto_loot.restore` (stock_boolean_setting_pass), `actionbars.lock_toggle.search` (ui_edit_pass), `actionbars.lock_toggle.change` (stock_boolean_setting_pass), `actionbars.lock_toggle.restore` (stock_boolean_setting_pass), `settings.mute.search` (ui_edit_pass), `settings.mute.change` (stock_boolean_setting_pass), `settings.mute.restore` (stock_boolean_setting_pass), `settings.restore_search` (ui_edit_pass), `settings.trial_close` (stock_settings_close_pass).
- [442_interactions_20261004_49.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_49.tar.gz.dvc), member `evidence/client_interactions_20261004_ui49/scout_booleans_02/episode.json`, SHA-256 `087fd1fdcf8af1ff34e7482427db9d076e53e0b40bd348591aaab93f9ca0f079`.
  Checked cases: `settings.inspect_menu` (panel_open_pass), `settings.inspect_open` (panel_open_pass), `settings.auto_loot.search` (ui_edit_pass), `settings.auto_loot.change` (stock_boolean_setting_pass), `settings.auto_loot.restore` (stock_boolean_setting_pass), `actionbars.lock_toggle.search` (ui_edit_pass), `actionbars.lock_toggle.change` (stock_boolean_setting_pass), `actionbars.lock_toggle.restore` (stock_boolean_setting_pass), `settings.mute.search` (ui_edit_pass), `settings.mute.change` (stock_boolean_setting_pass), `settings.mute.restore` (stock_boolean_setting_pass), `settings.restore_search` (ui_edit_pass), `settings.trial_close` (stock_settings_close_pass).
- [442_interactions_20261004_49.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_49.tar.gz.dvc), member `evidence/client_interactions_20261004_ui49/boolean_visual_review.json`, SHA-256 `320ac112fe054220c8a4177959db20d0cf20a6da2406541c75bd649e939ec1f9`.

### stock_interface_boolean_settings

On both owned idle human warriors, ordinary Settings search finds Follow Terrain, Tutorials, Enemy Units and Enable Floating Combat Text. Each observed stock checkbox changes once and reverses, with matching public Settings value and CVar. Original empty search, Controls category and all17 observed settings restore, the panels close, and native inventory, money and saved spells remain unchanged. Twenty-two exact frames receive visual review.

Remaining limits: Checkbox configuration on two idle fixtures only. Terrain-following motion, camera presets, tutorial popups/reset, rendered enemy nameplates, floating combat-text events, other settings and reconnect persistence remain open. This batch has no failed episodes.

- [442_interactions_20261004_50.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_50.tar.gz.dvc), member `evidence/client_interactions_20261004_ui50/primary_booleans_01/episode.json`, SHA-256 `28117623b60a0644a9fd56873db2a6db687fd286f2f7fd50fbbcb26f2dc56379`.
- [442_interactions_20261004_50.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_50.tar.gz.dvc), member `evidence/client_interactions_20261004_ui50/scout_booleans_01/episode.json`, SHA-256 `4a84765e631f6b11fae8756501cb123cfa41876bdca316de00619c0f8ea3f342`.
- [442_interactions_20261004_50.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_50.tar.gz.dvc), member `evidence/client_interactions_20261004_ui50/primary_boolean_visual_review.json`, SHA-256 `b373c1eaf6c49efb3f4aaeea89970ad67aa7271c0745efbb831b45f8cf021268`.
- [442_interactions_20261004_50.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_50.tar.gz.dvc), member `evidence/client_interactions_20261004_ui50/scout_boolean_visual_review.json`, SHA-256 `311a258e82f4f19ef3a61ebfd03a7587d4dd836b440da8119d4aff7c66a3be36`.

### stock_warrior_stance_bar

In complete primary_stance_04, click the stock Defensive, Berserker and original Battle Stance buttons on one idle zero-rage human warrior. Public active/checked buttons, native completed cast spells71/2458/2457, native shapeshift byte18/19/17, effective pages8/9/7 and all12 main-bar assignments agree with native learned-spell/SpellEffect/action-row contracts. The original stance/bar, zero rage, health, integer stats, native weapon damage, inventory, money and saved spell/action rows restore. Five exact frames receive visual review.

Remaining limits: Only primary04 from its recorded Battle baseline qualifies. Primary01 missing-starter-spell preflight and primary02 viewport-coordinate failure stay unqualified. Primary03 passes its clicks but fails full restoration: exiting Berserker removes an extra learned passive7381 and loses10% weapon damage. Its initial damage is not restored; the failed run and change remain explicit. Primary04 starts from the resulting baseline and restores weapon damage exactly; its guard permits only1e-6 relative/.002 absolute float rounding and still rejects primary03. Other classes, combat, nonzero-rage retention and reconnect persistence remain open.

- [442_interactions_20261004_51.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_51.tar.gz.dvc), member `evidence/client_interactions_20261004_ui51/primary_stance_04/episode.json`, SHA-256 `558e3874497a8541384ed5b596f6b627c443481dafe94bb4bd00cfff029135f8`.
- [442_interactions_20261004_51.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_51.tar.gz.dvc), member `evidence/client_interactions_20261004_ui51/stance_visual_review.json`, SHA-256 `6a9f27147ff44d8939fef866db24c9f524a10e4c4f9cca569db08705261d3269`.
- [442_interactions_20261004_51.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_51.tar.gz.dvc), member `evidence/client_interactions_20261004_ui51/stance_first_cycle_damage_change.json`, SHA-256 `9e53c91ccaf4fc5b4d72ff74ba936f937e207f434eeeb317548b62d0ba90898d`.

### stock_extra_actionbar_native_toggle

Complete primary/scout UI53 trials enable the stock Action Bar2 checkbox through ordinary observed input, forward native one-byte toggles01 and00, verify native player mask1 then0, settled checked/unchecked paint, the rendered12-slot empty grid after closing Settings and unchanged main slots/saved actions. Both restore all17 observed settings, empty search/category, hidden extra bar and native inventory/money/saved spells/actions. Twelve exact frames receive visual review.

Remaining limits: Only one initially disabled empty extra bar on two idle human warriors. Other bars, populated extra slots, bindings, combat and reconnect persistence remain open. UI52 failures remain unqualified. Early generic005_after frames show the prior paint; only the settled passive value frames qualify the changed checkbox.

- [442_interactions_20261004_53.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_53.tar.gz.dvc), member `evidence/client_interactions_20261004_ui53/primary_extra_01/episode.json`, SHA-256 `11b0348211da8b7fc5612121697e5bfa962f8ffcf726650bffc69e604d4a4795`.
- [442_interactions_20261004_53.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_53.tar.gz.dvc), member `evidence/client_interactions_20261004_ui53/scout_extra_01/episode.json`, SHA-256 `8cca970d7b58ab2e2d9cf2f222e63a205d04dc77984146dc6cd639280faf8066`.
- [442_interactions_20261004_53.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_53.tar.gz.dvc), member `evidence/client_interactions_20261004_ui53/extra_bar_visual_review.json`, SHA-256 `28adf6b20d7c665b7762461269284c951d95a61bf58f48846d863a269d8d7f7f`.
- [442_interactions_20261004_53.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_53.tar.gz.dvc), member `evidence/client_interactions_20261004_ui53/build_validation.json`, SHA-256 `5554d610d1c48b9763ed1ac41d8dde02350cb2be6409ee14f46593b38dfab6ce`.

### stock_lab_realm_reconnect

After a controlled owned bridge disconnect, both existing clients dismiss the separately reviewed Okay modal, activate Reconnect, select the single stock Client442 Lab realm row, confirm it and re-enter their default characters. Exact lobby/world frames are reviewed. Native worldserver and both client lifetimes remain unchanged on HDMI-1; both retain original native inventory/money/saved spell/action state against closed pre-disconnect evidence. UI108 adds fresh same-client primary proof after a bridge replacement: all9 native restoration checks and exact original resources/stats/spells/actions/pose/AFK/position continuity pass. The scout stays at its original offline selection. This supplements the existing scoped qualification and adds no operation count.

Remaining limits: Single lab realm and one default character per client, idle fixtures, controlled bridge disconnect. Default character world entry does not qualify selecting among characters. The first two Reconnect inputs per actor are blocked by the modal and do not advance; their input-only completion flags do not qualify world reentry. Successful reentry follows the distinct modal-dismissal path. Primary passive7381 can reapply an extra damage boost on login; damage-stat persistence is unqualified. Other realms, credentials, character creation/deletion, combat and other disconnect causes remain open. UI108 does not qualify another reconnect operation or other login routes. Its original softTargetInteract0 remains unrestored at1 and custom scripts stay blocked.

- [442_interactions_20261004_53.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_53.tar.gz.dvc), member `evidence/client_interactions_20261004_ui53/deployment/deployment.json`, SHA-256 `fc5db92e668b71749b4daea86803d6207381b19f854c34c5d3f79e2e8ca83513`.
- [442_interactions_20261004_53.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_53.tar.gz.dvc), member `evidence/client_interactions_20261004_ui53/deployment/after_dismiss_settled.json`, SHA-256 `7f11c8662497b04814e1f13834a02290bd40797c306fcbf7bbdd3e171fbe7c54`.
- [442_interactions_20261004_53.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_53.tar.gz.dvc), member `evidence/client_interactions_20261004_ui53/deployment/reconnect_after_dismiss_settled.json`, SHA-256 `cad7c8cbc84ab444ebc3e1b92fb2f32159847186e4abd2070bedeb698be0fcf1`.
- [442_interactions_20261004_53.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_53.tar.gz.dvc), member `evidence/client_interactions_20261004_ui53/deployment/character_selection_settled.json`, SHA-256 `76dd5c44a1b4dfc698550e93ceb22c2deda9b6a84c844fb7faed82250f930a6f`.
- [442_interactions_20261004_53.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_53.tar.gz.dvc), member `evidence/client_interactions_20261004_ui53/reconnect_native_review.json`, SHA-256 `34d48890ceaa4099e528a1fb501715591528691017ad04e0b87beb6b97b264f9`.
- [442_interactions_20261006_108.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_108.tar.gz.dvc), member `evidence/client_interactions_20261006_ui108/bridge_ignore_deployment/deployment.json`, SHA-256 `a6d0bdea425ad7e125ce2c1274d1fd82bac71b48659ffa6da902361f9f962223`.
- [442_interactions_20261006_108.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_108.tar.gz.dvc), member `evidence/client_interactions_20261006_ui108/bridge_ignore_deployment/primary_before/episode.json`, SHA-256 `25d863bf7afa621abe2b7bcb6a85e14b06eb170b9f603c9e81848cfdfa45fa89`.
- [442_interactions_20261006_108.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_108.tar.gz.dvc), member `evidence/client_interactions_20261006_ui108/bridge_ignore_deployment/primary_after/episode.json`, SHA-256 `7ecfa432019132dd04aae432e47a78ec25c6abe13ad43e6853f179f801d22f70`.
- [442_interactions_20261006_108.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_108.tar.gz.dvc), member `evidence/client_interactions_20261006_ui108/bridge_ignore_deployment/primary_after/review.json`, SHA-256 `2cbdcb18e102345e88df3ee70f0208cf48ca8698ea5192ea375437284d680e70`.
- [442_interactions_20261006_108.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_108.tar.gz.dvc), member `evidence/client_interactions_20261006_ui108/bridge_ignore_deployment/disconnect_review.json`, SHA-256 `834d28b77fb9dfbe52559c46a2910759c6ac7f453d43b0685b650dd0747aec31`.
- [442_interactions_20261006_108.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_108.tar.gz.dvc), member `evidence/client_interactions_20261006_ui108/bridge_ignore_deployment/primary_disconnect_dismiss_key/review.json`, SHA-256 `4a2e4c5bac97d68a60d749c928a37a664fb0460b51dcc56c9ba7d656993059b8`.
- [442_interactions_20261006_108.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_108.tar.gz.dvc), member `evidence/client_interactions_20261006_ui108/bridge_ignore_deployment/primary_login_after_dismiss/review.json`, SHA-256 `b74723856e42aa7175b6f7a29e7902f79e40fd7228591cbbe44015a71051d408`.
- [442_interactions_20261006_108.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_108.tar.gz.dvc), member `evidence/client_interactions_20261006_ui108/bridge_ignore_deployment/primary_realm/review.json`, SHA-256 `eb08e8933cfc89cfb3ed78a875f1d953b2cb193c7deab51f8531daea51a73c68`.
- [442_interactions_20261006_108.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_108.tar.gz.dvc), member `evidence/client_interactions_20261006_ui108/bridge_ignore_deployment/scout_parked_after/episode.json`, SHA-256 `d52c943d5b9177d3ffa21f98d2d2ed9188936dfa099d833ed689639852558c27`.
- [442_interactions_20261006_108.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_108.tar.gz.dvc), member `evidence/client_interactions_20261006_ui108/runtime_closure.json`, SHA-256 `00e4550298437b2c2176d6d7865a7dbf81f3629d74f26ed402e78e05c43eafc3`.

### stock_sit_stand_native_pose

Both complete UI54 pose04 trials use observed X binding to stand0 and sit1. Native requests00000000/01000000, replies00/01 and player stand fields agree. Eight exact settled frames show standing, seated and restored poses. Twelve-second passive waits replay no input. Both restore original AFK seated pose, sheath0, main bar, observed public position, health/power/stats, inventory/money and saved spell/action rows.

Remaining limits: Two idle human warriors, levels85 and1, original AFK seated pose, installed observer74. Natural AFK packets and cleanup are not binding passes. Pose01 sparse-zero and pose02 initial-seated preflight failures remain unqualified. Pose03 passes native checks but its early stand frames still show seated paint, so it has no visual qualification. Other races, combat, chairs, emotes, movement and persistence remain open.

- [442_interactions_20261004_54.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_54.tar.gz.dvc), member `evidence/client_interactions_20261004_ui54/primary_pose_04/episode.json`, SHA-256 `2bcb88718d4b070adf43141b44fc02842c11dd8c34c5c672564cde21356cf3b5`.
- [442_interactions_20261004_54.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_54.tar.gz.dvc), member `evidence/client_interactions_20261004_ui54/scout_pose_04/episode.json`, SHA-256 `8a651249ceb06a85527d1603a634d5d0ad0468421fb98cdefe5a8553c262b969`.
- [442_interactions_20261004_54.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_54.tar.gz.dvc), member `evidence/client_interactions_20261004_ui54/sit_stand_visual_review.json`, SHA-256 `c457211b55891b37ad2dd7d9557273636d467da1c0be536fd340541ba127debb`.
- [442_interactions_20261004_54.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_54.tar.gz.dvc), member `evidence/client_interactions_20261004_ui54/stand_state_contract.json`, SHA-256 `cea1e28555cb0ce94168c2cda1cd0500e80306a35fdae51a9bed4f00738b8fc0`.
- [442_interactions_20261004_54.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_54.tar.gz.dvc), member `evidence/client_interactions_20261004_ui54/automatic_afk_precondition_review.json`, SHA-256 `b032d879663a238c6ff36c56c62653eb185d81dbd6ba3ac01e29bba81670e564`.

### stock_ground_bindings_native_peer

Complete UI55 ground05 executes six observed bindings per owned human warrior: W/S/Q/E/A/D. All12 cases agree with native accepted XY/facing, byte-matched native start/stop requests, public owner/party-target coordinates and peer movement packets. Key release stops native and peer flags to0 and public speed to0 in all12 cases. Twelve exact scene frames and two original-world restoration frames receive review. Temporary party, native positions/orientations/map, pose/AFK, target absence, main bar, inventory/money/stats and saved spells/actions restore.

Remaining limits: Idle levels85/1 human warriors on open Northshire ground in a temporary owned party. Solo target UnitPosition returns no coordinates. Already-qualified strafe-right receives a second fixture variant without another operation count. Stop means release of the held translation/turn bindings; autorun/follow stop remains open. Public height/instance values are not reinterpreted. Camera easing and partly occluded body pixels are not pixel-coordinate or animation proof. Speed parity, other races/terrain, combat, walk/jump and other movement remain open. Ground01-04 and first cleanup failure remain unqualified; separate second Leave Party cleanup passes. Earlier six input-test fixture failures remain recorded; corrected23 tests pass.

- [442_interactions_20261004_55.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_55.tar.gz.dvc), member `evidence/client_interactions_20261004_ui55/ground_movement_05/primary/episode.json`, SHA-256 `18a6f340c60709a09bbdc055f0a03b0b1c87ee4ef395e776a7ebb91677d27656`.
- [442_interactions_20261004_55.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_55.tar.gz.dvc), member `evidence/client_interactions_20261004_ui55/ground_movement_05/scout/episode.json`, SHA-256 `368d2d37a0ee3f31b844c92d748179724fec7144efba29e7a59822cdd783f513`.
- [442_interactions_20261004_55.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_55.tar.gz.dvc), member `evidence/client_interactions_20261004_ui55/ground_movement_05/cohort.json`, SHA-256 `a2827adde0a168c4d017af8c169aecbe8db441ceb1c5eb665f759d13421e4770`.
- [442_interactions_20261004_55.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_55.tar.gz.dvc), member `evidence/client_interactions_20261004_ui55/ground_movement_05/nearby_restoration.json`, SHA-256 `f6851033ec4bc17d7066b69f66ded33daef08a4d2bb0578f6a81e862e51e0033`.
- [442_interactions_20261004_55.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_55.tar.gz.dvc), member `evidence/client_interactions_20261004_ui55/ground_acceptance_review.json`, SHA-256 `a200a6fd9ff852218b8876c9014df915c8d9d77f64561d542cb00c530c4e54d3`.
- [442_interactions_20261004_55.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_55.tar.gz.dvc), member `evidence/client_interactions_20261004_ui55/primary_ground_visual_review.json`, SHA-256 `1d8500b23cab713b5b8f46dbfd1ff1cd5b074b35178bb71a9507efb5a595d3fa`.
- [442_interactions_20261004_55.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_55.tar.gz.dvc), member `evidence/client_interactions_20261004_ui55/scout_ground_visual_review.json`, SHA-256 `0334c8ff49781909bb8c1f980f204dd4cd13b62308da6f39c14278bbbd974165`.
- [442_interactions_20261004_55.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_55.tar.gz.dvc), member `evidence/client_interactions_20261004_ui55/ground_failure_review.json`, SHA-256 `b8b5f5ca1e1d93b638cbb84eb8a9e319247ac3b9b3984e3db0f482f9f9eecee3`.
- [442_interactions_20261004_55.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_55.tar.gz.dvc), member `evidence/client_interactions_20261004_ui55/input_regression_review.json`, SHA-256 `581d5abfaf672e3e218e197321ad8cb7639af57f1623f0c240175c133186c401`.

### stock_walk_run_autorun

UI58 ground_modes03 toggles the observed NUMPADDIVIDE binding through walk and run on both owned human warriors. Native accepted flags, exact modern/native requests, peer broadcasts and public final positions agree. W movement matches native2.5yd/s walking and7yd/s running on both actors. Two NUMLOCK presses start and stop each actor within13yd; native/peer stop flags0, public speed0 and private NumLock state restore. Eight reviewed world/restoration frames retain normal action bars. All20 character checks, native position/orientation/map, temporary party and four teleport rows restore.

Remaining limits: Idle level85/1 human warriors on open Northshire ground with each owned presenter partly visible on HDMI-1 and at least10 rendered FPS. Ordinary installed bindings only; other terrain, combat, follow, swim/fly and persistence variants remain open. Static frames do not measure cadence. Failed ground_modes01 at~1FPS and ground_modes02 with a delayed probe stop remain unqualified and preserved. Window layout repair changes no speed fields or game CVars and preserves host input focus.

- [442_interactions_20261004_58.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_58.tar.gz.dvc), member `evidence/client_interactions_20261004_ui58/ground_modes03/primary/episode.json`, SHA-256 `8e5a104f5bf5d6c9b4d6b0e84bc6993370af4d45c2d0990df723673028eb3660`.
- [442_interactions_20261004_58.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_58.tar.gz.dvc), member `evidence/client_interactions_20261004_ui58/ground_modes03/scout/episode.json`, SHA-256 `4ea1e0b8600cb0843f81082084012de3e60505cbc3043a19eac01d5325e193fd`.
- [442_interactions_20261004_58.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_58.tar.gz.dvc), member `evidence/client_interactions_20261004_ui58/ground_modes03/cohort.json`, SHA-256 `1cb2694eab6a3bfd919ed238294e279a6c125163843537828d7f3f88f69472a7`.
- [442_interactions_20261004_58.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_58.tar.gz.dvc), member `evidence/client_interactions_20261004_ui58/ground_modes03/nearby_restoration.json`, SHA-256 `41071135b2720713125018ffa0125b3d4921c8411b56333cf65e2cd9404721c7`.
- [442_interactions_20261004_58.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_58.tar.gz.dvc), member `evidence/client_interactions_20261004_ui58/ground_modes_visual_review.json`, SHA-256 `86804a404b6f4ecb6455aeafdc058fa74824d6753d8a493c228a3cebbeaf3b6e`.
- [442_interactions_20261004_58.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_58.tar.gz.dvc), member `evidence/client_interactions_20261004_ui58/ground_modes_acceptance_review.json`, SHA-256 `5d63a9b9c9dd8826bc262efc5cfd13367ca8e08e0954c059a4898a646d6bb7ed`.
- [442_interactions_20261004_58.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_58.tar.gz.dvc), member `evidence/client_interactions_20261004_ui58/ground_modes_failure_review.json`, SHA-256 `8f5aebf77b78119a8f1e02661c1387b0fede40bb7b1818257e7352496571000c`.
- [442_interactions_20261004_58.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_58.tar.gz.dvc), member `evidence/client_interactions_20261004_ui58/window_layout01/layout.json`, SHA-256 `21f5e676d5597c36b46d13e2e29815ff4db8469e3852aaaf6daa969fde506a40`.
- [442_interactions_20261004_58.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_58.tar.gz.dvc), member `evidence/client_interactions_20261004_ui58/resource_review.json`, SHA-256 `40d4a32877902395f496fb3d898399835e2b7d4f8039d33c9621abb9f6b05ead`.

### standing_scout_weapon_cycle

Standing level1 scout cycles native melee1 and unarmed0 through the installed Z binding. Native/modern requests, authoritative sheath states and owner/peer sword-in-hand versus back rendering agree. The primary also completes native1/2/0;55 cycle checks and20 full character restoration checks pass. Temporary party, both original native positions/map/orientations, pose/AFK, main bar, resources, stats, spells/actions and four teleport rows restore.

Remaining limits: Exact heavy-primary/ranged weapon rendering remains unclaimed. Both presenters render~15FPS and stay on HDMI-1. Earlier1FPS owner-rendering and seated/AFK standalone failures remain unqualified. Other races, weapons, combat and persistence remain open.

- [442_interactions_20261004_59.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_59.tar.gz.dvc), member `evidence/client_interactions_20261004_ui59/sheath_peer02/primary/episode.json`, SHA-256 `7f75cff6514899d46330efb96dfc9492321e29f2c94e75010d1300927c4ae3e8`.
- [442_interactions_20261004_59.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_59.tar.gz.dvc), member `evidence/client_interactions_20261004_ui59/sheath_peer02/scout/episode.json`, SHA-256 `c900d9dae809fed3117629fa5c81c808baaed951212a1b08add9d8c0e1732378`.
- [442_interactions_20261004_59.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_59.tar.gz.dvc), member `evidence/client_interactions_20261004_ui59/sheath_peer02/cohort.json`, SHA-256 `67d5f435ba4a76f7417144fbd07af93143741b91ce91dd6fb10d8542ff89e3ce`.
- [442_interactions_20261004_59.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_59.tar.gz.dvc), member `evidence/client_interactions_20261004_ui59/sheath_peer02/nearby_restoration.json`, SHA-256 `41071135b2720713125018ffa0125b3d4921c8411b56333cf65e2cd9404721c7`.
- [442_interactions_20261004_59.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_59.tar.gz.dvc), member `evidence/client_interactions_20261004_ui59/sheath_visual_acceptance_review.json`, SHA-256 `9bef562a74eafc739e36abd5d9cf81259159085a3b08c9d7f20e150b98285e74`.
- [442_interactions_20261004_59.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_59.tar.gz.dvc), member `evidence/client_interactions_20261004_ui59/sheath_failure_review.json`, SHA-256 `925e5723aa7b42dc4f43531038e2ac2bf5a0a74b1ac3b82e17d12217ec0775a1`.
- [442_interactions_20261004_59.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_59.tar.gz.dvc), member `evidence/client_interactions_20261004_ui59/resource_review.json`, SHA-256 `d95fde7e28e42f6b4f58799c6fcf7a3c873585ed0d2607a395a83dac3ddbae24`.

### flat_ground_jump_landing

Both owned standing idle human warriors jump once through the installed SPACE binding. Native byte-matched jump/landing requests, peer airborne height gain and final flags0 agree with visibly airborne owner/peer frames and grounded landing frames. All26 jump checks and20 full character restoration checks pass. Both positions/map/orientations, party, pose/AFK, main bar, native resources/stats/spells/actions and temporary teleport rows restore.

Remaining limits: Only flat Northshire ground at levels85/1. Moving jumps, terrain, height falls, damage, water, mounts/transports, combat and persistence remain open. Jump01 failed the checker positive-speed assumption despite accepted native jump/landing; it remains unqualified. Captured negative-speed/observed-height regressions pass15 after correcting3 test-fixture tuple errors.

- [442_interactions_20261004_59.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_59.tar.gz.dvc), member `evidence/client_interactions_20261004_ui59/ground_jump02/primary/episode.json`, SHA-256 `0f11257d69f08adca2f4df7e8876e456b53b6b125ff5c2eb418ed3dea7746148`.
- [442_interactions_20261004_59.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_59.tar.gz.dvc), member `evidence/client_interactions_20261004_ui59/ground_jump02/scout/episode.json`, SHA-256 `87f5ce53adba8c9a0fe165945c73cbebe969721c9c13b83208c690cda4026756`.
- [442_interactions_20261004_59.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_59.tar.gz.dvc), member `evidence/client_interactions_20261004_ui59/ground_jump02/cohort.json`, SHA-256 `0a0d16aeea90560b3cb8ece9a27445ebd6c1d01c5fbbd5dfc440a35d9a5692d3`.
- [442_interactions_20261004_59.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_59.tar.gz.dvc), member `evidence/client_interactions_20261004_ui59/ground_jump02/nearby_restoration.json`, SHA-256 `41071135b2720713125018ffa0125b3d4921c8411b56333cf65e2cd9404721c7`.
- [442_interactions_20261004_59.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_59.tar.gz.dvc), member `evidence/client_interactions_20261004_ui59/jump_visual_acceptance_review.json`, SHA-256 `995b9ff9b25fd0f447a5993404bb7755eadc9ac5a95b93a1734fac858d028477`.
- [442_interactions_20261004_59.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_59.tar.gz.dvc), member `evidence/client_interactions_20261004_ui59/sheath_failure_review.json`, SHA-256 `925e5723aa7b42dc4f43531038e2ac2bf5a0a74b1ac3b82e17d12217ec0775a1`.
- [442_interactions_20261004_59.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_59.tar.gz.dvc), member `evidence/client_interactions_20261004_ui59/resource_review.json`, SHA-256 `d95fde7e28e42f6b4f58799c6fcf7a3c873585ed0d2607a395a83dac3ddbae24`.

### owned_party_targeting_focus

Both owned idle human warriors use stock F1/F2 bindings, party-frame click, clear/last-target slash commands and local focus commands. Native selection GUID fields and exact requests prove five target changes per actor; public GUIDs and rendered frames agree. Focus frames visibly appear and clear while native selection stays unchanged. All 94 qualifying checks, 20 complete character restoration checks, party/position/map/orientation restoration and four temporary teleport-row removals pass.

Remaining limits: Owned party at levels 85/1 only. Focus qualifies client-local UI only. Observer pixels partly cover upper target names; exact identity uses public/native GUIDs. Combat, enemy/raid target categories and remaining targeting controls remain open. Original preflight, observer overflow, hover03 and fresh-entry hover05 failures are preserved and unqualified.

- [442_interactions_20261004_60.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_60.tar.gz.dvc), member `evidence/client_interactions_20261004_ui60/owned_targeting_core04/primary/episode.json`, SHA-256 `0e4780212177260c4a14f84ab06c8c98bbd23b1366223acf34bd66afe1de1484`.
- [442_interactions_20261004_60.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_60.tar.gz.dvc), member `evidence/client_interactions_20261004_ui60/owned_targeting_core04/scout/episode.json`, SHA-256 `a6ecf8b610867b572e0f4ec8b880e67eae4a7a45e19052c32a78b97a99e7ea26`.
- [442_interactions_20261004_60.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_60.tar.gz.dvc), member `evidence/client_interactions_20261004_ui60/owned_targeting_core04/cohort.json`, SHA-256 `ddf39caad06f9bb70966b0aebb65b223c21375329092b726b8fc50f3964cba01`.
- [442_interactions_20261004_60.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_60.tar.gz.dvc), member `evidence/client_interactions_20261004_ui60/owned_targeting_core04/nearby_restoration.json`, SHA-256 `41071135b2720713125018ffa0125b3d4921c8411b56333cf65e2cd9404721c7`.
- [442_interactions_20261004_60.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_60.tar.gz.dvc), member `evidence/client_interactions_20261004_ui60/core_visual_acceptance_review.json`, SHA-256 `0de2dc4e23587cae7f21111938de00f6f29b49c89b2258e9a29e403e29f705d3`.
- [442_interactions_20261004_60.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_60.tar.gz.dvc), member `evidence/client_interactions_20261004_ui60/hover05_failure_review.json`, SHA-256 `2e230ab26b2948689554d888223fe43e9de93312b4de4b4053e4935eb1659cc1`.
- [442_interactions_20261004_60.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_60.tar.gz.dvc), member `evidence/client_interactions_20261004_ui60/observer_overflow_review.json`, SHA-256 `285205af5858b4b9e3745e27c54b03475938c738662f43e0303cba4eb85c3e2f`.
- [442_interactions_20261004_60.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_60.tar.gz.dvc), member `evidence/client_interactions_20261004_ui60/recovery_visual_review.json`, SHA-256 `1fc6c9f48929c67748b3eec985de9d5eeffbe5cb33d9ce5356b3e4959b9a5fbe`.
- [442_interactions_20261004_60.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_60.tar.gz.dvc), member `evidence/client_interactions_20261004_ui60/resource_review.json`, SHA-256 `9fc9541a406e7d88de197f8f931841c020459b3b5eb0b76762711509b2232d35`.

### owned_party_assist_target_target

Both owned idle human warriors use the observed stock F assist binding and ordinary targettarget command after exact native/public peer-target attribution. All 28 qualifying selection checks, six attribution checks and 20 full character restoration checks pass. Rendered owner-level target frames/selection circles agree with exact native requests and public GUIDs. Positions/map/orientation, party and four temporary teleport rows restore.

Remaining limits: Owned party levels 85/1 only. Combat, enemy/raid variants and a separate rendered target-of-target frame remain open. Original missing-translation, autocomplete and redundant-selection failures remain unqualified.

- [442_interactions_20261004_61.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_61.tar.gz.dvc), member `evidence/client_interactions_20261004_ui61/owned_assist04/primary/episode.json`, SHA-256 `93efa68f8ac6688709d1df90321bfa86f6868f48253c98fcf698dad7a4f56a6a`.
- [442_interactions_20261004_61.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_61.tar.gz.dvc), member `evidence/client_interactions_20261004_ui61/owned_assist04/scout/episode.json`, SHA-256 `5fc45cb3b01d794faf7f0f7f4f3c677295632c8e47cb0e9e9eabfcb74bd0675a`.
- [442_interactions_20261004_61.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_61.tar.gz.dvc), member `evidence/client_interactions_20261004_ui61/owned_assist04/cohort.json`, SHA-256 `a1bba61b3ca72750e87674cdf91c3b8fd775462c7e70fbe02256ba940e414f3c`.
- [442_interactions_20261004_61.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_61.tar.gz.dvc), member `evidence/client_interactions_20261004_ui61/owned_assist04/nearby_restoration.json`, SHA-256 `41071135b2720713125018ffa0125b3d4921c8411b56333cf65e2cd9404721c7`.
- [442_interactions_20261004_61.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_61.tar.gz.dvc), member `evidence/client_interactions_20261004_ui61/assist_visual_acceptance_review.json`, SHA-256 `af9ee8fdbd905b04ef55f457021345f020619fb03c92828d754927fbc31b50a5`.
- [442_interactions_20261004_61.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_61.tar.gz.dvc), member `evidence/client_interactions_20261004_ui61/assist_failure_review.json`, SHA-256 `f885b603f17bffda16379e549e9751fcad3511361f4b266d2893b850dcb1f27b`.
- [442_interactions_20261004_61.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_61.tar.gz.dvc), member `evidence/client_interactions_20261004_ui61/invite_autocomplete_review.json`, SHA-256 `e5263a5dabb95c68537b87d4d7f772aeb49459a6e8d8aa4a061592957042504a`.
- [442_interactions_20261004_61.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_61.tar.gz.dvc), member `evidence/client_interactions_20261004_ui61/redundant_selection_failure_review.json`, SHA-256 `942e07beab24a25f13f2132f5b733a22e6764af943576069ec7bb6f0283866a9`.
- [442_interactions_20261004_61.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_61.tar.gz.dvc), member `evidence/client_interactions_20261004_ui61/deployment_visual_review.json`, SHA-256 `6ca6ea74294b2ff560140fd0d51dd3af23374e86f4a7158dec24d90e46771eff`.
- [442_interactions_20261004_61.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_61.tar.gz.dvc), member `evidence/client_interactions_20261004_ui61/resource_review.json`, SHA-256 `4b483f625de6ecfc9fb84f45f0b78eb6453a75c27abf46c0ece4ee4231e7e25f`.

### owned_world_player_hover

Both actors hover the visually reviewed nearby owned world player at a point bound to that exact scene hash. Exact public mouseover GUID and rendered stock tooltip name, native level, human race and warrior class agree. All 14 hover checks and 20 full character restoration checks pass. Native selection and positions stay unchanged; the temporary party and four teleport rows restore.

Remaining limits: Standing idle nearby owned party players at levels 85/1 only. Earlier party-frame hover failures remain unqualified with cause unproven. NPC/enemy/combat/raid frame and cross-realm variants remain open.

- [442_interactions_20261004_61.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_61.tar.gz.dvc), member `evidence/client_interactions_20261004_ui61/world_hover01/primary/episode.json`, SHA-256 `a9bc586d1a9ec7917d72951aaac66784ae2360f7a0df451759285eb4613bd407`.
- [442_interactions_20261004_61.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_61.tar.gz.dvc), member `evidence/client_interactions_20261004_ui61/world_hover01/scout/episode.json`, SHA-256 `33ddfa52b1b4814c17045e197107640eb04de3cc8a9ad4ae6c9f286f5a39927d`.
- [442_interactions_20261004_61.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_61.tar.gz.dvc), member `evidence/client_interactions_20261004_ui61/world_hover01/cohort.json`, SHA-256 `0f7cfe8cbaa7ec0f974ace8a4e30161bb9aa165946d2c29604c6fcb453626b09`.
- [442_interactions_20261004_61.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_61.tar.gz.dvc), member `evidence/client_interactions_20261004_ui61/world_hover01/nearby_restoration.json`, SHA-256 `41071135b2720713125018ffa0125b3d4921c8411b56333cf65e2cd9404721c7`.
- [442_interactions_20261004_61.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_61.tar.gz.dvc), member `evidence/client_interactions_20261004_ui61/world_hover_visual_acceptance_review.json`, SHA-256 `1b8584e9ee923b3cb5f71cbbaebde5ffbef664e8301f71d91a1fb1710db6a3ba`.
- [442_interactions_20261004_61.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_61.tar.gz.dvc), member `evidence/client_interactions_20261004_ui61/assist_failure_review.json`, SHA-256 `f885b603f17bffda16379e549e9751fcad3511361f4b266d2893b850dcb1f27b`.
- [442_interactions_20261004_61.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_61.tar.gz.dvc), member `evidence/client_interactions_20261004_ui61/invite_autocomplete_review.json`, SHA-256 `e5263a5dabb95c68537b87d4d7f772aeb49459a6e8d8aa4a061592957042504a`.
- [442_interactions_20261004_61.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_61.tar.gz.dvc), member `evidence/client_interactions_20261004_ui61/redundant_selection_failure_review.json`, SHA-256 `942e07beab24a25f13f2132f5b733a22e6764af943576069ec7bb6f0283866a9`.
- [442_interactions_20261004_61.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_61.tar.gz.dvc), member `evidence/client_interactions_20261004_ui61/deployment_visual_review.json`, SHA-256 `6ca6ea74294b2ff560140fd0d51dd3af23374e86f4a7158dec24d90e46771eff`.
- [442_interactions_20261004_61.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_61.tar.gz.dvc), member `evidence/client_interactions_20261004_ui61/resource_review.json`, SHA-256 `4b483f625de6ecfc9fb84f45f0b78eb6453a75c27abf46c0ece4ee4231e7e25f`.

### owned_keybinding_native_roundtrip

Primary owned idle level85 client opens Options and the stock Keybindings category, assigns unused Ctrl+Shift+F12 to the second TOGGLEFPS slot, saves by Close, reloads and visibly toggles the counter. Original bindings, full settings and all ten native/public restoration checks pass; original seated pose is visibly restored.

Remaining limits: Build60895 routes menu.keybindings through Options then Keybindings. One account binding set and harmless unused chord only. Initial pose failure remains unqualified with separate exact recovery. Conflicts, explicit clear-binding case, defaults, per-character and combat variants remain open.

- [442_interactions_20261004_62.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_62.tar.gz.dvc), member `evidence/client_interactions_20261004_ui62/primary_bindings02/episode.json`, SHA-256 `2d550cca66d250619d97842cd5739c76cdd9565910ff68e057e2cf5ea4b50364`.
- [442_interactions_20261004_62.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_62.tar.gz.dvc), member `evidence/client_interactions_20261004_ui62/binding_visual_acceptance_review.json`, SHA-256 `9f0700f2eee878f5b4912ffda531bee0d83d3d5dcf73599c27b323c2759eefd3`.
- [442_interactions_20261004_62.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_62.tar.gz.dvc), member `evidence/client_interactions_20261004_ui62/primary_bindings01/episode.json`, SHA-256 `356b99d81563d8c53bf8d15686c04e2cc1ade24ae2fab0aaa45a2fa87de24d5a`.
- [442_interactions_20261004_62.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_62.tar.gz.dvc), member `evidence/client_interactions_20261004_ui62/binding_pose_recovery01/episode.json`, SHA-256 `81d5cca516f32d6f0910c57b84d4519e8a6790d848b964d0aeddbb49f63a978f`.
- [442_interactions_20261004_62.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_62.tar.gz.dvc), member `evidence/client_interactions_20261004_ui62/binding_pose_failure_review.json`, SHA-256 `d6cea42e8f9b3b8c065ef7aa395d2316546442ee6dac8e48126ea52b19c4ca2c`.
- [442_interactions_20261004_62.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_62.tar.gz.dvc), member `evidence/client_interactions_20261004_ui62/resource_review.json`, SHA-256 `728c1cfcaaffbd33e56930c2bc99d8e4a2553634dcb8fe7bc25b68a83c1a1d5e`.

### owned_binding_cancel_clear

Primary idle level85 account set1 cancels the observed second-slot listener with Escape, retaining original Ctrl+R and unbound chord. A later explicitly assigned Ctrl+Shift+F12 is visibly cleared by right-click, and Close/reload persist removal. All ten native/public and full original settings restoration checks pass.

Remaining limits: Listener cancellation and one disposable second-slot binding only. The clear case acts on a freshly assigned chord before saving its removal. Whole-window unsaved cancel, conflicts, defaults, per-character and other keys remain open.

- [442_interactions_20261004_63.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_63.tar.gz.dvc), member `evidence/client_interactions_20261004_ui63/primary_binding_controls01/episode.json`, SHA-256 `89f1d963944302796e48e9b261bc3fd03b59ba91083203999b864dfb31e025b6`.
- [442_interactions_20261004_63.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_63.tar.gz.dvc), member `evidence/client_interactions_20261004_ui63/binding_controls_visual_review.json`, SHA-256 `5e8551534c2299d4a63f93537d9649b5b0ff6341a988228f0f600350f5984a38`.
- [442_interactions_20261004_63.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_63.tar.gz.dvc), member `evidence/client_interactions_20261004_ui63/resource_review.json`, SHA-256 `89488d63a171587198c84236f2ccaae4eb521aa53965eef38682ae562e4bc36c`.

### owned_macro_menu_route

Ordinary Game Menu Macros click visibly opens the stock editor. Escape closes it with original zero account/character macro counts preserved. Original settings and all ten native/public restoration checks pass.

Remaining limits: Owned primary idle level85 panel route only. Macro content mutations and other variants require their separate evidence.

- [442_interactions_20261004_63.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_63.tar.gz.dvc), member `evidence/client_interactions_20261004_ui63/menu_macros01/episode.json`, SHA-256 `c4a6683b0ea9310afb3399e48f92328a5a8582bc022eb044dac1059d983a622d`.
- [442_interactions_20261004_63.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_63.tar.gz.dvc), member `evidence/client_interactions_20261004_ui63/menu_macros_visual_review.json`, SHA-256 `e10ef196ee8faf4314a97140914d441fee10f442d740083c571f00f7e382c27c`.
- [442_interactions_20261004_63.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_63.tar.gz.dvc), member `evidence/client_interactions_20261004_ui63/resource_review.json`, SHA-256 `89488d63a171587198c84236f2ccaae4eb521aa53965eef38682ae562e4bc36c`.

### owned_addon_menu_route

Fresh whole AddOns02 opens and closes the stock AddonList root and named controls with both owned addon rows visibly checked. Observer78 sees the previously omitted root. Full original settings and all ten native/public checks restore, including the visibly seated original pose.

Remaining limits: Owned primary idle level85 panel route only. No enable/disable, out-of-date, per-character loading or settings-addon mutation qualification. Initial AddOns/root observation failure, scout preflight and reentry guard/reader failures remain failed; separate exact recovery verifies original fixture.

- [442_interactions_20261004_63.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_63.tar.gz.dvc), member `evidence/client_interactions_20261004_ui63/menu_addons02/episode.json`, SHA-256 `e9358fbfdd0904b5601beecd2a5e2f5ddf57fc44ea26314d684b557500da5b81`.
- [442_interactions_20261004_63.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_63.tar.gz.dvc), member `evidence/client_interactions_20261004_ui63/menu_addons_visual_review.json`, SHA-256 `a478c312741b7c76507d2a38f81d315f48a9d75da8653923ae2c31222200108e`.
- [442_interactions_20261004_63.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_63.tar.gz.dvc), member `evidence/client_interactions_20261004_ui63/addon_observer_failure_review.json`, SHA-256 `3b30372dfebcff3a83562f7c54205cb37a865fee6dddc5abdb23071c13b45b79`.
- [442_interactions_20261004_63.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_63.tar.gz.dvc), member `evidence/client_interactions_20261004_ui63/addon_fixture_recovered01/episode.json`, SHA-256 `c34a9364b67143631330d70d55175ceee1029a8c7f600321c90d9ca98f2e733e`.
- [442_interactions_20261004_63.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_63.tar.gz.dvc), member `evidence/client_interactions_20261004_ui63/resource_review.json`, SHA-256 `89488d63a171587198c84236f2ccaae4eb521aa53965eef38682ae562e4bc36c`.

### owned_menu_logout_reused

Review of immutable UI34 owned primary evidence: ordinary GameMenuButtonLogout clicks produce two rendered countdowns with native request/response. The first cancels with native acknowledgement; the second completes and reenters the same character with all five original session persistence checks passing. Three archive frames were separately reviewed again.

Remaining limits: Historical primary idle level85 fixture and its recorded runtime/controller identities. This review launches no new logout and infers no expanded pose or native baseline claim. Other actors, resting/combat and other variants remain open.

- [442_interactions_20261003_35.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_35.tar.gz.dvc), member `evidence/client_interactions_20261003_ui34/session_logout_01/episode.json`, SHA-256 `4d6492077afc10016b24148087f651589674a6c79729bc0e712006e8b2909a7d`.
- [442_interactions_20261003_35.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_35.tar.gz.dvc), member `evidence/client_interactions_20261003_ui34/session_reenter_01/episode.json`, SHA-256 `0492b5dc32c503c8219ee9aa986d1a1b56167a646d4b910c6acf5a476584ea4e`.
- [442_interactions_20261003_35.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_35.tar.gz.dvc), member `evidence/client_interactions_20261003_ui34/session_persistence_review.json`, SHA-256 `67f497647a642d79688375b521527f1f5757d64fc5e2373466577b79d0721e13`.
- [442_interactions_20261004_63.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_63.tar.gz.dvc), member `evidence/client_interactions_20261004_ui63/menu_logout_reuse_review.json`, SHA-256 `38f318b508514c52861f70bd9647abb61bf2680084eaec97d163bb2efa67f09c`.

### owned_defaults_cancel

Stock Controls and Keybindings Defaults confirmation cancellation in the owned primary. Both modal Cancel buttons return to the original settings. All275 installed binding rows, original settings and all10 native/public restoration checks are unchanged; five rendered frames reviewed.

Remaining limits: Cancellation only. Defaults Apply, graphics/audio defaults and other actors remain open.

- [442_interactions_20261004_64.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_64.tar.gz.dvc), member `evidence/client_interactions_20261004_ui64/primary_defaults_cancel01/episode.json`, SHA-256 `ae9040e065557515ea8cdcbeb06369deb8486e8dea809855890d30a1fb79e2d8`.
- [442_interactions_20261004_64.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_64.tar.gz.dvc), member `evidence/client_interactions_20261004_ui64/defaults_cancel_visual_review.json`, SHA-256 `f0b5aeae8ce99e74a2dc507ce30e03a745d0f4036a0309df5f40a3a4ec5f5970`.

### owned_support_shell_navigation

Game Menu Support opens the stock Customer Support shell, and its observed close button closes it. Three rendered frames reviewed; original settings and all10 native/public restoration checks pass.

Remaining limits: Shell navigation only. The observed spinner establishes neither functioning service content nor an unsupported service. Tickets, categories, reports and surveys remain open. Earlier Escape-close failure retained.

- [442_interactions_20261004_64.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_64.tar.gz.dvc), member `evidence/client_interactions_20261004_ui64/menu_help02/episode.json`, SHA-256 `b05e56b02dc504297421a6f21553645b0eb4f816a80664dc11e0bdbc7984c007`.
- [442_interactions_20261004_64.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_64.tar.gz.dvc), member `evidence/client_interactions_20261004_ui64/support_shell_visual_review.json`, SHA-256 `36046af11eaa29669fc3dc55190d07c277c23a6bda1bc776f7109772c5b4aa5b`.

### owned_party_chat

Fresh whole-pass owned_party_chat06 sends one exact owned marker from the leader and one from the member. Both ordinary requests, native deliveries and both public peer events pass. Six actual rendered send/receive/restoration frames reviewed; all20 restoration checks, original positions and removal of four temporary teleports pass. Native Party Leader51 translates to modern49; ordinary Party2 stays2.

Remaining limits: Owned primary85/scout1 local two-player party on map0; observer80 retains the latest exact probe. Earlier guard, import, observation-capacity and cleanup/recovery failures remain failures in the archive. Other chat contexts and variants remain open.

- [442_interactions_20261004_64.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_64.tar.gz.dvc), member `evidence/client_interactions_20261004_ui64/owned_party_chat06/cohort.json`, SHA-256 `a73a2b0b23b4ba69bcc881e96aad394de03fcd8a31589a757aba2b9922a07a4b`.
- [442_interactions_20261004_64.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_64.tar.gz.dvc), member `evidence/client_interactions_20261004_ui64/owned_party_chat06/primary/episode.json`, SHA-256 `eaae3bd8977243ecda25b369abef42c6b4eec33bdc5023bc24971767a07f7b70`.
- [442_interactions_20261004_64.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_64.tar.gz.dvc), member `evidence/client_interactions_20261004_ui64/owned_party_chat06/scout/episode.json`, SHA-256 `5064aa61ae6eed79a24f05eea427a138fc87056af06cc68f44a8a487498b6cf2`.
- [442_interactions_20261004_64.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_64.tar.gz.dvc), member `evidence/client_interactions_20261004_ui64/owned_party_chat06/nearby_restoration.json`, SHA-256 `41071135b2720713125018ffa0125b3d4921c8411b56333cf65e2cd9404721c7`.
- [442_interactions_20261004_64.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261004_64.tar.gz.dvc), member `evidence/client_interactions_20261004_ui64/party_chat_visual_review.json`, SHA-256 `2031dad99865d4eca1a2ac25aee697356dd61f0c796a5786e5f603661836a631`.

### owned_character_binding_set_roundtrip

Owned primary account binding set1 switches to character set2 through the stock checkbox, saves and survives reload, then returns to account1 through the stock warning and survives reload again. Four actual frames reviewed. Original account bindings file bytes, FPS binding, unused test chord, original settings and all10 native/public restoration checks remain unchanged. No original character-specific bindings file existed; the generated file is absent afterward.

Remaining limits: Disposable primary with no original character-specific bindings file. Existing custom character bindings, warning cancellation, conflicting assignments and other actors remain open. Earlier failed trial and batch-initialization recovery remain explicit.

- [442_interactions_20261005_65.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_65.tar.gz.dvc), member `evidence/client_interactions_20261005_ui65/primary_binding_set02/episode.json`, SHA-256 `8dd99254d76b7a616097a0344b4309339b4da581c366384f9deb44acded4118b`.
- [442_interactions_20261005_65.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_65.tar.gz.dvc), member `evidence/client_interactions_20261005_ui65/binding_set_visual_review.json`, SHA-256 `141daa2c961942a2d2b4b0a0526a1722fe1edc6a9f2ccd0be1acba27d42c83fc`.
- [442_interactions_20261005_65.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_65.tar.gz.dvc), member `evidence/client_interactions_20261005_ui65/binding_set_failure_review.json`, SHA-256 `a7fac846c52e0ba29d55868834acbe06f6776783dd627c7d096743b6fd79cede`.
- [442_interactions_20261005_65.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_65.tar.gz.dvc), member `evidence/client_interactions_20261005_ui65/batch.json`, SHA-256 `6ca724a1d723363a840cf7d8d45068f5f8a532c59b15cc5a6706b52a4b879bf4`.

### owned_macro_editor_controls

Fresh whole-pass macro_controls02 creates two account macros and one character macro, switches stock banks, saves a changed name and observed icon, cancels deletion, verifies reload persistence and restores zero macros. Actual rendered frames reviewed. The installed empty-bank detail bug is repaired by a UI-only compatibility hook; the empty body field is hidden and deletion disabled before creation restores the normal editor. All10 native/public restoration checks pass.

Remaining limits: Owned primary with originally empty macro banks and empty action probe. Bodies remain empty and no macro executes. Other actors, account capacity, existing custom macros and other dialogs remain open. Failed trials and exact fixture recovery remain explicit.

- [442_interactions_20261005_66.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_66.tar.gz.dvc), member `evidence/client_interactions_20261005_ui66/macro_controls02/episode.json`, SHA-256 `eb97ef54a83bbb9dc5a24995fadfd5488e29ad516ae58739fa664140f88631ac`.
- [442_interactions_20261005_66.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_66.tar.gz.dvc), member `evidence/client_interactions_20261005_ui66/macro_editor_visual_review.json`, SHA-256 `c68b26b6972bef639817ddf7b3dd2cbc1ef314b51eae3bbb10b7cead4ed4230e`.
- [442_interactions_20261005_66.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_66.tar.gz.dvc), member `evidence/client_interactions_20261005_ui66/macro_failure_recovery_review.json`, SHA-256 `d82661fcdc9cca89d4f2f7d21d89b4537f1dc9e4286c98709c47a3de93665820`.
- [442_interactions_20261005_66.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_66.tar.gz.dvc), member `evidence/client_interactions_20261005_ui66/macro_guard_deploy01/deployment.json`, SHA-256 `bf3a78a567df8f951e6375896ac40d5442eebbee3c7c5a3b1b12025b9eaf1ade`.

### owned_macro_selection_after_reload

The fresh whole-pass macro_controls02 physically selects TC442Renamed after reload, changing the public selected name from TC442B and actual index1 to2. Both actual before/after frames reviewed; counts remain2/1, then both banks restore to0/0 and all10 native/public restoration checks pass.

Remaining limits: Two owned account macros, empty bodies. The earlier macros.select click on an already-selected A is excluded from this proof. Other selection contexts remain open. Future harness selections require both name and index changes.

- [442_interactions_20261005_66.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_66.tar.gz.dvc), member `evidence/client_interactions_20261005_ui66/macro_controls02/episode.json`, SHA-256 `eb97ef54a83bbb9dc5a24995fadfd5488e29ad516ae58739fa664140f88631ac`.
- [442_interactions_20261005_66.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_66.tar.gz.dvc), member `evidence/client_interactions_20261005_ui66/macro_selection_review.json`, SHA-256 `05a3079eb10370dfa4d23d28ec1f907b7ff612b8369686eeafacda3866b7b44f`.
- [442_interactions_20261005_66.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_66.tar.gz.dvc), member `evidence/client_interactions_20261005_ui66/macro_editor_visual_review.json`, SHA-256 `c68b26b6972bef639817ddf7b3dd2cbc1ef314b51eae3bbb10b7cead4ed4230e`.

### owned_macro_confirmation_controls

Fresh whole-pass macro_controls02 opens the stock delete confirmation, cancels it with the selected macro and counts unchanged, then accepts stock Okay during owned cleanup and removes exactly one disposable macro. Actual dialog, cancellation and accepted outcome frames reviewed. Original zero macro banks and all10 native/public checks restore.

Remaining limits: Stock macro deletion confirmation on the owned primary only. Other confirmation families and contexts remain open.

- [442_interactions_20261005_66.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_66.tar.gz.dvc), member `evidence/client_interactions_20261005_ui66/macro_controls02/episode.json`, SHA-256 `eb97ef54a83bbb9dc5a24995fadfd5488e29ad516ae58739fa664140f88631ac`.
- [442_interactions_20261005_66.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_66.tar.gz.dvc), member `evidence/client_interactions_20261005_ui66/macro_editor_visual_review.json`, SHA-256 `c68b26b6972bef639817ddf7b3dd2cbc1ef314b51eae3bbb10b7cead4ed4230e`.

### owned_character_macro_limit

Fresh whole-pass character_macro_limit01 reaches the installed character bank cap30 through stock creation, physically clicks disabled New with no extra macro or popup, deletes one fixture to29 and observes New enabled, recreates30 and repeats the disabled boundary. Rendered capacity, scrolling and final restoration frames reviewed. All30 owned empty-body fixtures are removed, zero banks survive reload and all10 native/public checks pass.

Remaining limits: Owned primary with originally empty banks, installed60895 character cap30 only. Account cap120, other actors/builds, existing macros and nonempty bodies remain open. No macro executes or enters an action bar.

- [442_interactions_20261005_67.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_67.tar.gz.dvc), member `evidence/client_interactions_20261005_ui67/character_macro_limit01/episode.json`, SHA-256 `1b42349b7726f1d50e766fd8287c4aa47b086e5951b5391d0755e400638c5477`.
- [442_interactions_20261005_67.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_67.tar.gz.dvc), member `evidence/client_interactions_20261005_ui67/character_macro_limit_visual_review.json`, SHA-256 `7e39e3297d7d8cee3781ebded4b4be6fdc2393d2e0ebc89587bc38685460d6eb`.
- [442_interactions_20261005_67.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_67.tar.gz.dvc), member `evidence/client_interactions_20261005_ui67/capacity_budget_sample01.json`, SHA-256 `aff144c449b263c39ea0136eae798226e7daea177c82df530d275900251cd5ad`.

### owned_pending_backpack_item_link

Whole-pass bag_link01 physically Shift-clicks the exact owned Worn Greatsword49778 backpack slot10 into a blank pending Say edit box. Actual rendered label and public item hyperlink reviewed. No message is submitted; the exact native item and all10 native/public checks remain unchanged.

Remaining limits: Owned plain backpack sword only. Delivery, clicking sent links, other item classes/slots and generic chat-link behavior remain open.

- [442_interactions_20261005_68.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_68.tar.gz.dvc), member `evidence/client_interactions_20261005_ui68/bag_link01/episode.json`, SHA-256 `f91db0ccb26d1cff1c914c86cd0cfe830529809336e9ffa88c37ba4aa92e5b50`.
- [442_interactions_20261005_68.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_68.tar.gz.dvc), member `evidence/client_interactions_20261005_ui68/pending_chat_links_visual_review.json`, SHA-256 `26e467b4426f30b42b02c38a6c8c452367092b42c4708bf1b896c76a0e79ca94`.

### owned_pending_known_spell_link

Fresh whole-pass spell_link04 physically Shift-clicks native-known Battle Shout6673 into pending Say chat, with zero cast requests and owned native cast completions. Actual blue link reviewed. Corrected secure stock dispatch also passes ordinary right-click native cast/public buff/cooldown and normal cancellation. Original spellbook layout and all10 native/public checks restore.

Remaining limits: Owned warrior Battle Shout on installed60895 only. Other spells/classes/actors, delivery and clicking sent links remain open. Failed fixture, shifted-cast and insecure-wrapper trials plus source-bound recovery remain explicit; no subcase from a failed episode qualifies this operation.

- [442_interactions_20261005_68.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_68.tar.gz.dvc), member `evidence/client_interactions_20261005_ui68/spell_link04/episode.json`, SHA-256 `e6f03227c658fba39ffe08aea1fb21d598c1b67a8c5ec7c59e0841cc1dd5a15c`.
- [442_interactions_20261005_68.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_68.tar.gz.dvc), member `evidence/client_interactions_20261005_ui68/pending_chat_links_visual_review.json`, SHA-256 `26e467b4426f30b42b02c38a6c8c452367092b42c4708bf1b896c76a0e79ca94`.
- [442_interactions_20261005_68.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_68.tar.gz.dvc), member `evidence/client_interactions_20261005_ui68/chat_link_failure_review.json`, SHA-256 `bcff1728c361274a17bbedbab4a6660fc262dd8a1fcfa3f858b129f1f26cdf84`.
- [442_interactions_20261005_68.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_68.tar.gz.dvc), member `evidence/client_interactions_20261005_ui68/secure_spell_recovery01/episode.json`, SHA-256 `4783712983458aa6e05c4e6014d32e69480bba01040c2dd5f0709e8f462222c3`.
- [442_interactions_20261005_68.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_68.tar.gz.dvc), member `evidence/client_interactions_20261005_ui68/secure_spell_dispatch_deploy01/deployment.json`, SHA-256 `7a1e4db38e188b8393ef4133a29da424efcf7ea3b5a9e56ddd4a63a9a51779f3`.

### owned_backpack_tooltip_and_comparison

Fresh whole-pass bag_tooltips02 normally hovers stored sword49778, then holds private Shift to compare it with equipped sword78478. Actual Worn Greatsword, Currently Equipped Gurthalak and comparison disappearance on Shift release reviewed. Native catalog names/IDs, unchanged inventory and all10 native/public checks pass.

Remaining limits: Exact owned two-hand sword fixture only. Other slots/items, dual wield and numerical tooltip parity remain open. Failed pinned-mode diagnostic01 is retained and excluded.

- [442_interactions_20261005_68.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_68.tar.gz.dvc), member `evidence/client_interactions_20261005_ui68/bag_tooltips02/episode.json`, SHA-256 `59d202320f2b02ea7feabaa490470c2ef60d5fc56ba0902caafc85e1541a0b30`.
- [442_interactions_20261005_68.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_68.tar.gz.dvc), member `evidence/client_interactions_20261005_ui68/bag_tooltip_visual_review.json`, SHA-256 `b665eb1d49d5e7d80a5cb4c9006be69aaf00b8be50c61d4ce3844d3df96f5cf9`.
- [442_interactions_20261005_68.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_68.tar.gz.dvc), member `evidence/client_interactions_20261005_ui68/bag_tooltip_failure_review.json`, SHA-256 `565ec35e66c97bb5cfba8ce740bdb4940c82458220b5e7aaa95bc7182bc5a797`.

### owned_pending_achievement_link

Whole-pass achievement_link01 physically Shift-clicks native-catalog achievement2536 Mountain o' Mounts into pending Say chat. Actual journal row and gold link reviewed. No message or cast is submitted. Original layout/tracking, native earned/progress state and all10 native/public checks restore.

Remaining limits: Owned achievement2536 only. Other achievements/actors, delivery, clicking sent links and generic chat-link acceptance remain open.

- [442_interactions_20261005_68.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_68.tar.gz.dvc), member `evidence/client_interactions_20261005_ui68/achievement_link01/episode.json`, SHA-256 `aa926e1a864bb215ab1a68d92ac9f80f0c40e0a12303e1e152d18130c661e4d8`.
- [442_interactions_20261005_68.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_68.tar.gz.dvc), member `evidence/client_interactions_20261005_ui68/achievement_link_visual_review.json`, SHA-256 `b3cd65fb5eb87878be135f2d984e0090f524155e19f48f47856f958c0941f0d0`.

### owned_exact_whisper_reply

Fresh whole-pass reply_chat04 receives the exact owned scout seed whisper, uses the observed stock Chat Reply binding, verifies focus and the full Harnesstwo-Client442Lab target, waits for the complete exact marker and submits one reply. Actual pending/outgoing/incoming frames reviewed. Native incoming sender GUIDs2/1 and recipient confirmation GUIDs1/2, native/public deliveries and ordinary requests all pass. Both actors restore all10 native/public checks.

Remaining limits: Two owned solo actors on the private realm only. Other senders/realms/permissions, re-whisper, links and other chat families remain open. Failed bare-name, GUID-role and immediate-text-read trials remain excluded with both actors restored; no input or submission replay during settling.

- [442_interactions_20261005_69.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_69.tar.gz.dvc), member `evidence/client_interactions_20261005_ui69/reply_chat04/cohort.json`, SHA-256 `3c4286e9b6bf94ebcefa6a11be04f946f3ede0050dc4baf797a4e18440e863b9`.
- [442_interactions_20261005_69.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_69.tar.gz.dvc), member `evidence/client_interactions_20261005_ui69/reply_chat04/primary/episode.json`, SHA-256 `f6a23e19af9dda9ef480ec6d92ef23d4cfd66b9e465fb092d8cca5a65a9b7d91`.
- [442_interactions_20261005_69.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_69.tar.gz.dvc), member `evidence/client_interactions_20261005_ui69/reply_chat04/scout/episode.json`, SHA-256 `e0b682ddc3840432a5e1e84b5ec1d478210bae2fde0fa8870291b82fc73c42dc`.
- [442_interactions_20261005_69.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_69.tar.gz.dvc), member `evidence/client_interactions_20261005_ui69/reply_visual_review.json`, SHA-256 `071e4bca98ab9534cab6fd84cf212b00a34f07a3e9c24e32367d7fa06143b6e4`.
- [442_interactions_20261005_69.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_69.tar.gz.dvc), member `evidence/client_interactions_20261005_ui69/reply_target_failure_review.json`, SHA-256 `45bfe33c969b63b8d74ef90bced45b0c54bb232338098afa903e7e60cb5b8550`.
- [442_interactions_20261005_69.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_69.tar.gz.dvc), member `evidence/client_interactions_20261005_ui69/reply_guid_oracle_failure_review.json`, SHA-256 `77fda9dad620f50a4ebdc809eea0e4509110ab3db4314f7b21fce93e48e71492`.
- [442_interactions_20261005_69.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_69.tar.gz.dvc), member `evidence/client_interactions_20261005_ui69/reply_text_settling_failure_review.json`, SHA-256 `d976330bcfca1fddff8ac0059de224bbf1a5d48ed93f529559b0a5f57bcf05c0`.

### owned_stock_chat_window_lifecycle

Fresh whole-pass chat_window_controls03 creates disposable stock slot4 TC442Chat, renames it TC442Renamed through the exact stock dialog, uses observed 16 pt and 14 pt submenu buttons, and closes the owned tab. Public full name/font getters agree; reviewed actual frames show creation, exact rename dialog,16 pt checkmark and tab closure. Existing General, Combat Log and Voice settings and original selection restore. All 10 native/public checks pass. Observer87 includes unparented submenu proxies.

Remaining limits: Exact disposable character slot4 only, idle private owned warrior. Stock closing retains hidden unused-slot metadata; no byte-identical chat-cache claim. Account-wide/window-cap/dock/layout/other font choices and chat filters remain open. Two failed whole trials are excluded even though their cleanup passes. Full renamed string comes from the public getter because its docked caption truncates/fades.

- [442_interactions_20261005_70.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_70.tar.gz.dvc), member `evidence/client_interactions_20261005_ui70/chat_window_controls03/episode.json`, SHA-256 `e55684c58634d1947c153b63bc904ac2c7f557569a3078ad5b173cc04fd11d17`.
- [442_interactions_20261005_70.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_70.tar.gz.dvc), member `evidence/client_interactions_20261005_ui70/chat_window_visual_review.json`, SHA-256 `b60dc5bb3260bca3f36525ce174899f5bfb07b2bd41abca3169f67dda91dc94b`.
- [442_interactions_20261005_70.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_70.tar.gz.dvc), member `evidence/client_interactions_20261005_ui70/chat_menu_failure_review.json`, SHA-256 `3fc48e6e778c7985c59b76c0a3d97541d198def8c0bb73dc34be219a4ec1e2dd`.
- [442_interactions_20261005_70.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_70.tar.gz.dvc), member `evidence/client_interactions_20261005_ui70/chat_menu_unparented_failure_review.json`, SHA-256 `d6177f6459b60a1a8819451893446885a3b4f6b45473bb2d592bb7bcce107720`.
- [442_interactions_20261005_70.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_70.tar.gz.dvc), member `evidence/client_interactions_20261005_ui70/font_submenu_recon02/episode.json`, SHA-256 `98e5c97d7b26eb0338c42a9a8773f016f96e72e5a9ac13d9d651b04621b4dec7`.

### stock_general_say_filter_roundtrip

Fresh whole-pass stock General Config toggles the observed Say checkbox off, verifies exactly SAY removed from the public message-group list, closes and reopens the panel, restores Say and closes it. Actual off/on frames reviewed. All original window settings/selection/message groups and all 10 native/public checks restore.

Remaining limits: General Say filter only, persisted across panel reopening. Other filters, class colors, defaults, channel controls, account chat disable and reconnect persistence remain open.

- [442_interactions_20261005_71.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_71.tar.gz.dvc), member `evidence/client_interactions_20261005_ui71/chat_settings_filter01/episode.json`, SHA-256 `fbe46ef935ae6c7942ab0d692a624607a23fbcadb663386e4e09a459739a5740`.
- [442_interactions_20261005_71.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_71.tar.gz.dvc), member `evidence/client_interactions_20261005_ui71/chat_settings_history_visual_review.json`, SHA-256 `0f532f3fb6a1ceafb60d29e5018b91d64a55dfd225b4472f2c4c0c6183ef8dd4`.

### owned_native_chat_history_scroll

Fresh whole-pass chat_history01 seeds 13 exact owned SAY markers, each verified by ordinary request, native sender GUID1 and public event. Observed stock up/down buttons change General offset0 to 3 and back to0 with 14 messages unchanged during both steps. Actual earlier/later message frames reviewed. Original settings, geometry, selection and offset plus all 10 native/public checks restore.

Remaining limits: Observed General window geometry, stock up/down buttons and exact own messages only. Fixture messages and normal AFK system text remain in history; no ClearMessages setter or byte-identical history rollback. Wheel, alternate layouts, copy, links and large-buffer limits remain open.

- [442_interactions_20261005_71.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_71.tar.gz.dvc), member `evidence/client_interactions_20261005_ui71/chat_history01/episode.json`, SHA-256 `c4a3c183818bc376546fd68fa2bb25d734ce1cfd4dfbced6b9521f717e55017d`.
- [442_interactions_20261005_71.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_71.tar.gz.dvc), member `evidence/client_interactions_20261005_ui71/chat_settings_history_visual_review.json`, SHA-256 `0f532f3fb6a1ceafb60d29e5018b91d64a55dfd225b4472f2c4c0c6183ef8dd4`.

### owned_native_stock_combat_log_timestamps

Fresh whole-pass owned_native_combat_log03 copies stock My actions to TC442Log, enables the Spell Casting group and its Success child, and checks Show Timestamp through observed stock controls. Native-owned Battle Shout6673 counter5 completes, matching filtered and unfiltered own SPELL_CAST_SUCCESS events. Actual stock log shows new05:39:19 timestamped Harnessone casts Battle Shout line, different from prior05:31:03. Original combat preference fingerprint, filter metadata/current selection, chat settings, spellbook layout and all10 native/public checks restore after deleting only the disposable copy.

Remaining limits: Exact private idle warrior and copied combat-log filter only. Other spells/combat payloads, General-chat timestamps, log history limits and reconnect persistence remain open. Stock refilter rebuilds history, so message_count1 is not a monotonic event oracle. Numeric child state2 is unchecked enabled; only booleantrue enables Success. Failed whole trials remain excluded.

- [442_interactions_20261005_72.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_72.tar.gz.dvc), member `evidence/client_interactions_20261005_ui72/owned_native_combat_log03/episode.json`, SHA-256 `77d3e13fd908f8c7dad4e277e9157f32c008cb01ae574550233ccf7b872f1853`.
- [442_interactions_20261005_72.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_72.tar.gz.dvc), member `evidence/client_interactions_20261005_ui72/native_combat_log_visual_review.json`, SHA-256 `2a25edfb2109299b96f7d1f747a0ed24b04cff88b3a868723132cfc387d308bc`.
- [442_interactions_20261005_72.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_72.tar.gz.dvc), member `evidence/client_interactions_20261005_ui72/native_combat_log_failure_review.json`, SHA-256 `f0855c149a7f68c7fc95669eff36079d782a86670162a0157df27748d0f17b46`.
- [442_interactions_20261005_72.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_72.tar.gz.dvc), member `evidence/client_interactions_20261005_ui72/owned_combat_filter_failure_review.json`, SHA-256 `b590134a37abad2f4c74f39bdfa4dc30a08df91d11f75a70920f3395a1118ea2`.

### owned_item_link_native_say_delivery

Fresh whole-pass item_chat_delivery03 Shift-clicks native-owned Worn Greatsword49778 bag0slot10 into focused Common Say, then submits exactly the stock-generated hyperlink. Both request directions, native response senderGUID1 and translated response match the full link. Actual General chat renders Harnessone says: [Worn Greatsword]. Item identity/slot, chat settings/geometry and all10 native/public checks restore. Exact fixture-only capture rejects surrounding text, foreign links/senders and malformed boundaries; native Say may retain owned receiverGUID1.

Remaining limits: Own Common Say delivery of exact item49778 only. The message remains in ordinary history. Peer delivery, clicking sent links and other link types/items remain open. Failed01/02 trials remain excluded. One earlier full-suite stale-clock test fails before repair; final full1029 checks pass before the receiver amendment and all63 relevant checks pass afterward.

- [442_interactions_20261005_72.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_72.tar.gz.dvc), member `evidence/client_interactions_20261005_ui72/item_chat_delivery03/episode.json`, SHA-256 `5d403643d47cbf462fb8f398ccf3ebfa8287e86bae323eed0f31f930700b75ee`.
- [442_interactions_20261005_72.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_72.tar.gz.dvc), member `evidence/client_interactions_20261005_ui72/item_chat_delivery_visual_review.json`, SHA-256 `ff896ed6d1f77f25b572bbb50bde8f02cbed35cc270f4d2b2660aabfb03bcad1`.
- [442_interactions_20261005_72.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_72.tar.gz.dvc), member `evidence/client_interactions_20261005_ui72/item_chat_delivery_failure_review.json`, SHA-256 `e365d5750ac502329f11fc438b56117c66bab08f36091c5c9e87fa8a12bb76bb`.
- [442_interactions_20261005_72.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_72.tar.gz.dvc), member `evidence/client_interactions_20261005_ui72/item_chat_delivery_receiver_failure_review.json`, SHA-256 `0f516cda684d67da6d59ceb48bdab31b61bae5a02edbb95bc3dd27af03b82d4e`.
- [442_interactions_20261005_72.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_72.tar.gz.dvc), member `evidence/client_interactions_20261005_ui72/chat_probe_bridge_validation.json`, SHA-256 `5578a456c02d0408e6b97302ed52fe782a7163ed5e7023fce0932c571ee82e33`.
- [442_interactions_20261005_72.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_72.tar.gz.dvc), member `evidence/client_interactions_20261005_ui72/chat_probe_receiver_validation.json`, SHA-256 `8ec1e0b32f2b6e8cd95a9e532a996456f6d8207204dcc20c01243b6d4bdd62d1`.
- [442_interactions_20261005_72.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_72.tar.gz.dvc), member `evidence/client_interactions_20261005_ui72/chat_probe_bridge_deploy01/deployment.json`, SHA-256 `1c0fb463773203b928ab1bcc8382986d1837928e4f73f5aa34a573488b69f5f4`.
- [442_interactions_20261005_72.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_72.tar.gz.dvc), member `evidence/client_interactions_20261005_ui72/chat_probe_bridge_deploy02/deployment.json`, SHA-256 `6f0c3e38c1d39bfbee198a9aa3b7341de8d9d6617d6bbc990c9ba58b3e2f0ee7`.

### owned_native_stock_channel_membership

Fresh whole-pass channel_join_probe02 uses ordinary stock slash join and leave for one uniquely named primary-owned TC442UIChannel. Public membership becomes enabled. Captured modern/native requests and native/modern acknowledgements agree. Independent decoding proves native leave type3, channelID0, suspendedfalse and exact modern leave name. Reviewed General chat shows Changed Channel, owned moderator privileges and Left Channel. Original channel membership, chat settings and all ten native/public checks restore.

Remaining limits: One primary-owned disposable channel, no password. Channel lists, owner query/reassignment, passwords, peer membership and persistence remain open. Initial unmapped join/leave and first absent-entry cleanup guard remain failed and excluded; source-bound absence verification after normal reentry passes. Initial test collection import error is corrected; 71 focused and 1044 full bridge tests pass.

- [442_interactions_20261005_73.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_73.tar.gz.dvc), member `evidence/client_interactions_20261005_ui73/channel_join_probe02/episode.json`, SHA-256 `a800d473817a0d843de7df41ab5426cb1153af716371556a95548fedee0af461`.
  Checked cases: `chat.channel_join` (owned_channel_join_pass), `fixture.leave_owned_channel` (owned_channel_left).
- [442_interactions_20261005_73.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_73.tar.gz.dvc), member `evidence/client_interactions_20261005_ui73/channel_roundtrip_review.json`, SHA-256 `a3e24449cc75ef67ee61ab07b262fe44c20c978ddff68d2cde40f536c3446270`.
- [442_interactions_20261005_73.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_73.tar.gz.dvc), member `evidence/client_interactions_20261005_ui73/channel_validation.json`, SHA-256 `71c378bf2c5627a8a29e052db1b479532aea116e8706cfaa7173876c06d002a3`.
- [442_interactions_20261005_73.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_73.tar.gz.dvc), member `evidence/client_interactions_20261005_ui73/channel_join_failure_review.json`, SHA-256 `8993cc8ea8f2e41fc9b28672e89145ef099864cc32a18248a19e63b92c0e4a8c`.
- [442_interactions_20261005_73.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_73.tar.gz.dvc), member `evidence/client_interactions_20261005_ui73/failed_channel_cleanup02/episode.json`, SHA-256 `867ed1b0b005628e3dbbf238c3d62c683d7956604ebc0f49777bf958384e7413`.
- [442_interactions_20261005_73.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_73.tar.gz.dvc), member `evidence/client_interactions_20261005_ui73/channel_bridge_deploy01/deployment.json`, SHA-256 `368d73d91503467a1bd7a9116eafbb1d50e4571b19ca2b901e9c65193e157be2`.
- [442_interactions_20261005_73.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_73.tar.gz.dvc), member `evidence/client_interactions_20261005_ui73/observer93_deployment01/deployment.json`, SHA-256 `85e73a83e7d8d671feca93f226f5fd87e616568d8c19e2bb5c6b978723399436`.

### owned_native_stock_channel_owner_query

Fresh whole-pass channel_owner02 queries one uniquely named primary-owned disposable channel through stock /owner input. All four packet directions are captured. Native notification type11 contains exactly the channel and Harnessone; independent modern decoding preserves both strings. Reviewed General chat says Channel owner is Harnessone. Ordinary leave removes the owned channel; original channel membership, chat settings and all ten native/public checks restore.

Remaining limits: Ownership query only. Reassignment, passwords, peer membership and persistence remain open. Initial owner01 is unmapped and excluded. All three list trials remain failed and unqualified despite native/modern packet delivery; realm routing repair does not restore list text/events. Full1047 tests pass before route correction and focused74 pass after; observer95 unit checks pass but deployment follows in next batch.

- [442_interactions_20261005_74.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_74.tar.gz.dvc), member `evidence/client_interactions_20261005_ui74/channel_owner02/episode.json`, SHA-256 `c095ad7bfa71c2d8d02ae4b58ad58bf9079fe2b5e270ed0b3e51626d6d0b4516`.
  Checked cases: `chat.channel_owner` (owned_channel_owner_query_pass).
- [442_interactions_20261005_74.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_74.tar.gz.dvc), member `evidence/client_interactions_20261005_ui74/channel_owner_visual_review.json`, SHA-256 `4de6863803111d6c3d8c5893494e682c64c5a05c60252e74204c87c3b06bdacf`.
- [442_interactions_20261005_74.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_74.tar.gz.dvc), member `evidence/client_interactions_20261005_ui74/channel_validation.json`, SHA-256 `c0d3b560df462be793728d1264d2fc520cc209a6c90e183e3004ae62096e597a`.
- [442_interactions_20261005_74.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_74.tar.gz.dvc), member `evidence/client_interactions_20261005_ui74/channel_list_owner_failure_review.json`, SHA-256 `206ba3901cd3d6b769a5f98b73aad0e7996ce2db7b8b56120ff426d59a344802`.
- [442_interactions_20261005_74.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_74.tar.gz.dvc), member `evidence/client_interactions_20261005_ui74/channel_list_connection_failure_review.json`, SHA-256 `d85803ffb1098b41847221581f4500a0d8ce7efa9a6701ccb1ba2f2ab919cc0c`.
- [442_interactions_20261005_74.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_74.tar.gz.dvc), member `evidence/client_interactions_20261005_ui74/channel_list_realm_failure_review.json`, SHA-256 `8f2ac5b5f3450c9ff4fd1d00021af44fae04381547664fddcf85e0907bdd50b0`.
- [442_interactions_20261005_74.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_74.tar.gz.dvc), member `evidence/client_interactions_20261005_ui74/channel_bridge_deploy01/deployment.json`, SHA-256 `d5b96abe7f7745caca4939b3b4c51867b8cb7db7292af0196883f57910de287d`.
- [442_interactions_20261005_74.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_74.tar.gz.dvc), member `evidence/client_interactions_20261005_ui74/channel_bridge_deploy02/deployment.json`, SHA-256 `39a9813c70f575c6768d3ede480937e072dd2fff0fc3b8552d5a302411b87c9a`.

### owned_native_stock_channel_ui_roster

Fresh whole-pass channel_ui_roster01 uses ordinary stock ChatFrameChannelButton and selects the exact owned disposable channel row. Native and modern list replies, a fresh stock roster request/event, public Harnessone player identity and the reviewed rendered channel title/member row agree. Exact ordinary leave restores original channels/chat settings and all ten native/public checks. Both existing HDMI-1 clients remain owned and observer96 deployments complete. UI76 whole-pass channel_peer02 keeps the roster selected while the owned scout joins and leaves. Reviewed two-member then one-member scenes, exact public player GUIDs, native member counts2/1, modern channelID0, and independently decoded full native/modern rosters agree. Both actors restore original channels/chat and all ten native checks. The bridge reads complete native membership after updates to the stock-selected channel.

Remaining limits: Owned custom channels only; stock UI initial and live two-actor rosters. UI74 slash chatlist01/02/03 remain failed and excluded. UI76 peer01 fails its cached roster despite correct wire fields and is excluded; fresh whole peer02 passes after native roster-read repair. Passwords, ownership reassignment, larger cohorts, built-in-channel variants and persistence remain open. Final30 focused and1061 full checks pass; existing unrelated mail.cpp warning remains.

- [442_interactions_20261005_75.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_75.tar.gz.dvc), member `evidence/client_interactions_20261005_ui75/channel_ui_roster01/episode.json`, SHA-256 `09907d8b6a0c0140fe902e478943ad73516aecec33ec97c1be820ac2a4b0ca85`.
  Checked cases: `chat.channel_list` (owned_stock_channel_roster_pass).
- [442_interactions_20261005_75.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_75.tar.gz.dvc), member `evidence/client_interactions_20261005_ui75/channel_roster_visual_review.json`, SHA-256 `bf587c4df1fe94924e8e70630362e348d6c5840d4b3f9837429741b64f8c532f`.
- [442_interactions_20261005_75.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_75.tar.gz.dvc), member `evidence/client_interactions_20261005_ui75/channel_roster_restoration_review.json`, SHA-256 `8ff46c325609237ccc8af1ad9c58eab65e162c96f0e152f6093cf4ba2ef36cb1`.
- [442_interactions_20261005_75.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_75.tar.gz.dvc), member `evidence/client_interactions_20261005_ui75/observer95_deployment01/deployment.json`, SHA-256 `157cfc19038093eb1041506d71e714cac70b7451bea311daa3bf45050a0c76c3`.
- [442_interactions_20261005_75.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_75.tar.gz.dvc), member `evidence/client_interactions_20261005_ui75/observer96_deployment01/deployment.json`, SHA-256 `aef9fd722b4ee086712f10c31079676e518a44da15401d6244e4e7b835cfd021`.
- [442_interactions_20261005_76.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_76.tar.gz.dvc), member `evidence/client_interactions_20261005_ui76/channel_peer02/primary/episode.json`, SHA-256 `4bea707dfcffb09a3d343dd5230591ba5442bce011b006523a1e163906b9dec6`.
  Checked cases: `chat.channel_list` (owned_stock_channel_roster_pass).
- [442_interactions_20261005_76.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_76.tar.gz.dvc), member `evidence/client_interactions_20261005_ui76/channel_peer02/scout/episode.json`, SHA-256 `751c3c02976434324beca58850a3d20b80a48d736f16d1941677e7899d8fabb1`.
- [442_interactions_20261005_76.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_76.tar.gz.dvc), member `evidence/client_interactions_20261005_ui76/channel_peer02/cohort.json`, SHA-256 `6b2680d13328f9810294a837ff8601dba04d7b70e5b19449b3602b5709bbc54e`.
- [442_interactions_20261005_76.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_76.tar.gz.dvc), member `evidence/client_interactions_20261005_ui76/channel_peer_visual_wire_review.json`, SHA-256 `c9dff388aac53d7b1aa2a60692c20cc6c74346a9db58130f58959daec4993d98`.
- [442_interactions_20261005_76.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_76.tar.gz.dvc), member `evidence/client_interactions_20261005_ui76/channel_peer_failure_review.json`, SHA-256 `47a635fb42f9e1a0b7e51faf48d898b7184989462872f17da2defe9c979954fa`.
- [442_interactions_20261005_76.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_76.tar.gz.dvc), member `evidence/client_interactions_20261005_ui76/channel_validation.json`, SHA-256 `482fd20f3120c93033f2f47f807ace83cd94828ac2e81dd829ec2413bc2c422d`.
- [442_interactions_20261005_76.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_76.tar.gz.dvc), member `evidence/client_interactions_20261005_ui76/channel_bridge_deploy01/deployment.json`, SHA-256 `04a58d2ae0cdd5fe6a668aadb59919a2a641a42224aaf6e62ee5b817c9a26a7b`.
- [442_interactions_20261005_76.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_76.tar.gz.dvc), member `evidence/client_interactions_20261005_ui76/channel_bridge_deploy02/deployment.json`, SHA-256 `e445f79fe9bd525b4c30ae7e69edbb7f88b5ead9a6d55c9738b8393c0a2dd776`.

### owned_native_channel_password_gate

Fresh whole-pass UI79/password01 sets and clears the exact owned disposable channel password through ordinary slash input. Exact modern7/7 and native8/7 setter fields, native/modern password-changed notices, public membership and reviewed General lines agree. The owned scout is rejected without a password; the exact stock prompt is reviewed and its observed Cancel restores focus before absent enabled membership is checked. Fixed-password join and password-free rejoin after clear pass with independently decoded modern7/7/native8/8 join requests, native responses and reviewed two-player rosters. Exact leaves restore both original channel/chat settings and all ten native checks on each actor.

Remaining limits: Two owned actors and the fixed public disposable fixture only. Other password strings, wrong nonempty passwords, stock Settings password controls, ownership reassignment, larger cohorts, built-in channels and persistence remain open. UI77/password01/02/03/04 and UI78/password01 remain whole failures and excluded. Diagnostic guards pass27 focused and1087 full checks; all current trials use code, with no decision model.

- [442_interactions_20261005_79.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_79.tar.gz.dvc), member `evidence/client_interactions_20261005_ui79/channel_password01/primary/episode.json`, SHA-256 `a37bc6943efd4f3e080ee2a7e756ebbbed5dd36b3addcdc82967121e4930878b`.
  Checked cases: `chat.channel_password` (owned_native_password_changed).
- [442_interactions_20261005_79.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_79.tar.gz.dvc), member `evidence/client_interactions_20261005_ui79/channel_password01/scout/episode.json`, SHA-256 `427870b107f302b37ef1ece8a09f54319e56ab9a2ae23a86c956e55f6733b5d5`.
- [442_interactions_20261005_79.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_79.tar.gz.dvc), member `evidence/client_interactions_20261005_ui79/channel_password01/cohort.json`, SHA-256 `99c3b5f725a3ff0832fec934740224c5bd6db4191ccabd4f200c25a1260d92c9`.
- [442_interactions_20261005_79.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_79.tar.gz.dvc), member `evidence/client_interactions_20261005_ui79/channel_password_whole_review.json`, SHA-256 `01552358096f43f7e5aac5826705e266ae8ba9f0fdbea00ac8967834603083b8`.
- [442_interactions_20261005_79.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_79.tar.gz.dvc), member `evidence/client_interactions_20261005_ui79/password_validation.json`, SHA-256 `742a09f0942bcc265bb619c168f781d1309ae4da9a9c09857fecc42414fe9b4c`.

### owned_native_racial_stock_language

Fresh whole-pass UI83/natural_language02 uses the owned native dwarf warrior and ordinary stock Language menu/submenu/radio clicks. Public Dwarvish6 and Common7 choices and selections agree. Exact Say markers and senderGUID3 match independently decoded modern request, native request, native reply and modern reply; reviewed General chat renders both messages. Exact language/chat/channel/spell/skill cleanup and all ten native checks pass. Normal logout, reviewed original-character selection and entry restore Harnesstwo with all21 checks against the immutable preparation baseline. Native race capability data repairs the character-list unlock gate without restarting the native worldserver or either game.

Remaining limits: Only the owned native dwarf Dwarvish/Common Say variant. Other racial languages, peer comprehension, default language selection, creation UI, unsupported race/class combinations and arbitrary language teaching remain open. UI80/81/82 hypotheses and rejected entries, plus UI83/natural_language01 exact-text guard failure, remain excluded. The parsed Say guard requires exact marker text, focused edit and public SAY mode; observer101 and1137 full tests pass. No decision model or extra game client.

- [442_interactions_20261005_83.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_83.tar.gz.dvc), member `evidence/client_interactions_20261005_ui83/natural_language02/episode.json`, SHA-256 `4385b8df6f7b10b5bc50cbaa6798c19be3e04e93dacfcc830a1e5cc8c9245e3b`.
  Checked cases: `chat.language_switch` (owned_stock_language_pass).
- [442_interactions_20261005_83.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_83.tar.gz.dvc), member `evidence/client_interactions_20261005_ui83/natural_language_whole_review.json`, SHA-256 `eb7a2a44bc9d4a77a2837563734c07c4aa1d8d42e08c495209f233143e497345`.
- [442_interactions_20261005_83.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_83.tar.gz.dvc), member `evidence/client_interactions_20261005_ui83/natural_language_visual_review.json`, SHA-256 `e4e3b9afab632d09f4523529f5356fc9bab9ba37d810afff7f039316ce26402d`.
- [442_interactions_20261005_83.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_83.tar.gz.dvc), member `evidence/client_interactions_20261005_ui83/natural_fixture_origin_enter01/episode.json`, SHA-256 `5d7be8b2134e598816e9f34189bbeb4ce7f9bed9a35b80ed7398c0bd88ad0c75`.
- [442_interactions_20261005_83.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_83.tar.gz.dvc), member `evidence/client_interactions_20261005_ui83/say_guard_failure_review.json`, SHA-256 `27576e1ea55e6bdb3d6ed4643cdd56f7d2497b3fb0eee09f0a2ff87bbb2e7a92`.
- [442_interactions_20261005_83.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_83.tar.gz.dvc), member `evidence/client_interactions_20261005_ui83/live_race_unlock_review.json`, SHA-256 `dd0b3cc7e8547bd3f11308069606400dfe454d163e236a9c5796e997478840e0`.

### owned_stock_local_voice_self_mute

Whole-pass UI84/voice_mute01 finds the installed TOGGLE_VOICE_SELF_MUTE action in ordinary Keybindings search. Both initial slots are unbound and the owned CTRL-SHIFT-F12 chord is unused. Stock listener/assignment and reviewed row/tooltip bind the chord. Ordinary key inputs change public IsMuted false->true->false with every other voice field unchanged, including offline voice login. The stock right-click removes only that temporary binding; both reviewed slots return to Not Bound and the chord is clear. Public voice, saved settings and all ten native checks restore against the source baseline recovered from the earlier failed search.

Remaining limits: Local self-mute through this installed binding only. Connected voice audio, channel activation, microphone transmission, voice services, peer mute/deafen and online microphone indicators remain open. The voice search cleanup failure and first caption-guard recovery failure remain excluded. Exact source recovery restores12 checks before the whole trial. Four initial test-mock KeyError failures are retained; corrected13 focused checks and1149 full tests pass. No decision model, extra game client, native world restart or voice API setter is invoked by the observer.

- [442_interactions_20261005_84.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_84.tar.gz.dvc), member `evidence/client_interactions_20261005_ui84/voice_mute01/episode.json`, SHA-256 `b551f832d8a846f73eaf1796635fb8ae9b52dc75f2aa6b2fdc1da506581c325d`.
  Checked cases: `chat.mute_voice` (owned_local_voice_mute_pass).
- [442_interactions_20261005_84.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_84.tar.gz.dvc), member `evidence/client_interactions_20261005_ui84/voice_whole_review.json`, SHA-256 `8bfb75c4543909d240c71ceef3fcb5db2b5f0111679b6f645c0c36d7da06f18a`.
- [442_interactions_20261005_84.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_84.tar.gz.dvc), member `evidence/client_interactions_20261005_ui84/voice_search_failure_review.json`, SHA-256 `9e89f28b9daa5090b1d26475d6f03d7ee9c311eb514d1a2de136f9ae9fa53676`.
- [442_interactions_20261005_84.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_84.tar.gz.dvc), member `evidence/client_interactions_20261005_ui84/voice_search_recovery02/episode.json`, SHA-256 `d81c13d5eee5b724fc89251b51054d6d85613612b0fcc45d4e30d3dd4a182418`.

### owned_player_chat_link_name_copy

Whole-pass UI85/player_name_copy08 seeds one exact whisper from owned native GUID2/Harnesstwo to GUID1/Harnessone. Reviewed rendered sender text and actual ChatFrame1 OnHyperlinkEnter player data gate the ordinary right-click. Stock Copy Character Name replaces a uniquely served private nested-display clipboard marker with exactly Harnesstwo, independently read as UTF8 with a new selection owner. The stock menu may stay open after Copy; separate UI cleanup closes it. Both actors restore all ten native checks. The generic ui_misc.copy_name entry maps to this same exact stock action and owned-name fixture; no additional live Copy is claimed.

Remaining limits: Owned sender name on primary nested display2 only. No host clipboard read and no claim that prior private clipboard bytes were restored; the copied owned name is retained. Arbitrary names, item/quest links and other clipboard forms remain open. Earlier failed Copy01-07, source recon and cleanup-only work are excluded, including Copy03 incorrect menu-closure oracle and Copy04 provider atom error. New trials use code only. Full1215 tests pass.

- [442_interactions_20261005_85.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_85.tar.gz.dvc), member `evidence/client_interactions_20261005_ui85/player_name_copy08/primary/episode.json`, SHA-256 `d052895f619924931d0a6339ea1810d935741c9cb3a87fd430686e2c2a1731cb`.
  Checked cases: `chat.copy_if_available` (owned_player_name_copy_pass).
- [442_interactions_20261005_85.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_85.tar.gz.dvc), member `evidence/client_interactions_20261005_ui85/player_name_copy08/scout/episode.json`, SHA-256 `aa88c135341c5cc8af6d9cc026788ccf068b4fe4caf408d67972a0d34f012d79`.
- [442_interactions_20261005_85.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_85.tar.gz.dvc), member `evidence/client_interactions_20261005_ui85/player_copy_visual_review.json`, SHA-256 `0d8e658d91590ee0488a11587533604c33f8b0734d8d38e38e3c8b77ca07587f`.
- [442_interactions_20261005_85.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_85.tar.gz.dvc), member `evidence/client_interactions_20261005_ui85/player_menu_whole_review.json`, SHA-256 `df3a3b0cac8f82fd84e143a50143b87a10756d9cd11984afa0ed030dc5f34d55`.
- [442_interactions_20261005_85.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_85.tar.gz.dvc), member `evidence/client_interactions_20261005_ui85/player_link_failed_run_review.json`, SHA-256 `3c95d76bb2767842bbc9a59d5963773f9b103a0b117731c4b205cee95aae15da`.
- [442_interactions_20261005_95.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_95.tar.gz.dvc), member `evidence/client_interactions_20261005_ui95/copy_name_mapping_review.json`, SHA-256 `39fa5beb20594ea7d390c112b07b63143d31808b2e429a52d2c5b2e18a4e8c18`.

### owned_player_chat_link_report_cancel

Whole-pass UI85/player_report_cancel03 uses the same exact owned native GUID2 whisper, reviewed sender and actual owned hyperlink-enter gate. Ordinary Report Player opens the stock Report Harnesstwo form after bounded observation settling, without replaying input. Exact form name, one Close, one disabled Report button and the attributable native/public chat source pass. This chat-link form exposes no public GUID; a present foreign or empty GUID is rejected. Only the observed Close button is clicked. Reviewed form/closed frames and both actors ten native restoration checks pass.

Remaining limits: Opening and cancelling this owned-player form only. No reason, comment or Report submission input; submitted reports, moderation outcomes, arbitrary targets and other report forms remain open. Report01 early-snapshot failure and Report02 unavailable-public-GUID guard failure remain excluded, with both fixtures restored. Negative tests require exact native seed, owned hyperlink and one matching public whisper for a missing form GUID. Full1215 tests pass.

- [442_interactions_20261005_85.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_85.tar.gz.dvc), member `evidence/client_interactions_20261005_ui85/player_report_cancel03/primary/episode.json`, SHA-256 `996c18196b15e08b1691b2eba7039bdb17a9c9318f6663e8d178688fd6bfa5b0`.
  Checked cases: `chat.report_ui_cancel` (owned_report_ui_cancel_pass).
- [442_interactions_20261005_85.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_85.tar.gz.dvc), member `evidence/client_interactions_20261005_ui85/player_report_cancel03/scout/episode.json`, SHA-256 `b2d7889f6b0b2e634e4d9356b84352ee52521ca4db3d637c1a59959d9fe37ef2`.
- [442_interactions_20261005_85.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_85.tar.gz.dvc), member `evidence/client_interactions_20261005_ui85/player_report_visual_review.json`, SHA-256 `553dfc9432ff4c3766b4cf8c6837dcd88bba36c346b96a4caf9791666e36c47b`.
- [442_interactions_20261005_85.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_85.tar.gz.dvc), member `evidence/client_interactions_20261005_ui85/player_menu_whole_review.json`, SHA-256 `df3a3b0cac8f82fd84e143a50143b87a10756d9cd11984afa0ed030dc5f34d55`.
- [442_interactions_20261005_85.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_85.tar.gz.dvc), member `evidence/client_interactions_20261005_ui85/player_link_failed_run_review.json`, SHA-256 `3c95d76bb2767842bbc9a59d5963773f9b103a0b117731c4b205cee95aae15da`.

### owned_alchemy_makeable_filter

Stock Have Materials checkbox on idle owned Alchemy at 525/525 with zero materials changes the catalog from 318 to zero entries and back to 318. Ordinary unfiltered thumb drag and exact row 126 selection restore Deepholm, the search placeholder, checkbox and top viewport. Original spellbook and all ten native checks pass.

Remaining limits: Other profession, rank, populated makeable-list, subclass, slot, permission, combat and persistence variants remain open.

- [442_interactions_20261005_86.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_86.tar.gz.dvc), member `evidence/client_interactions_20261005_ui86/alchemy_variants02/episode.json`, SHA-256 `d070a4709430c0b5a29ee99780dc26ce58ed4dc06c0b10a67fadde16f3c169fc`.
  Checked cases: `professions.recipe_filter.makeable_on` (recipe_filter_pass), `professions.recipe_filter.makeable_off` (recipe_filter_pass).
- [442_interactions_20261005_86.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_86.tar.gz.dvc), member `evidence/client_interactions_20261005_ui86/recipe_whole_review.json`, SHA-256 `6e7f162f1717a78c953ae7d2628834dc1a8bbf91db683f4b496bd157f2ca5362`.

### owned_alchemy_recipe_result_tooltip

Ordinary hover of TradeSkillSkillIcon for native-known Potion of Deepholm, spell 80725, displays the stock item 58487 tooltip with the exact native catalog name, rendered title and owner. Recipe and native resources stay unchanged; whole layout and native restoration pass.

Remaining limits: This qualifies only the selected Deepholm result-item icon tooltip. Other recipe links, rows, items, classes, ranks, comparisons, combat and locale variants remain open.

- [442_interactions_20261005_86.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_86.tar.gz.dvc), member `evidence/client_interactions_20261005_ui86/alchemy_variants02/episode.json`, SHA-256 `d070a4709430c0b5a29ee99780dc26ce58ed4dc06c0b10a67fadde16f3c169fc`.
  Checked cases: `professions.recipe_tooltip` (recipe_item_tooltip_pass).
- [442_interactions_20261005_86.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_86.tar.gz.dvc), member `evidence/client_interactions_20261005_ui86/recipe_whole_review.json`, SHA-256 `6e7f162f1717a78c953ae7d2628834dc1a8bbf91db683f4b496bd157f2ca5362`.

### owned_alchemy_recipe_reagent_tooltips

Ordinary hovers of TradeSkillReagent1 and TradeSkillReagent2 display native item 52986, Heartblossom, and item 3371, Crystal Vial, with exact names, rendered titles and owners. The selected native recipe requires five and one respectively and has zero of both. Whole recipe, spellbook and ten native restoration checks pass.

Remaining limits: Other reagents, recipes, inventories, crafting, classes, ranks, links, comparisons, combat and locale variants remain open.

- [442_interactions_20261005_86.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_86.tar.gz.dvc), member `evidence/client_interactions_20261005_ui86/alchemy_variants02/episode.json`, SHA-256 `d070a4709430c0b5a29ee99780dc26ce58ed4dc06c0b10a67fadde16f3c169fc`.
  Checked cases: `professions.reagent_tooltip.52986` (recipe_item_tooltip_pass), `professions.reagent_tooltip.3371` (recipe_item_tooltip_pass).
- [442_interactions_20261005_86.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_86.tar.gz.dvc), member `evidence/client_interactions_20261005_ui86/recipe_whole_review.json`, SHA-256 `6e7f162f1717a78c953ae7d2628834dc1a8bbf91db683f4b496bd157f2ca5362`.

### owned_master_volume_stepper_roundtrip

Owned primary muted-audio fixture: one stock Master Volume decrement from 100 to95 percent and increment back to100. Rendered percentage, public CVar and Settings value agree; original search/category, other observed settings and all ten native fixture checks restore.

Remaining limits: Master Volume arrows at the saved upper endpoint only. Other audio controls and ranges, slider dragging, audible output, keybindings and reconnect persistence remain open. Failed exercise01 and source-bound cleanup recovery01 remain excluded; numeric formatting 1.0 versus 1 is reviewed as equivalent only for this CVar.

- [442_interactions_20261005_87.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_87.tar.gz.dvc), member `evidence/client_interactions_20261005_ui87/master_volume_exercise02/episode.json`, SHA-256 `576b22c8c1bcab84fa6d6603dfffc89bba844c69bec2ef712d1c60f2bf8e7564`.
  Checked cases: `settings.sound_volume.decrease` (stock_numeric_setting_pass), `settings.sound_volume.restore.1` (stock_numeric_setting_pass).
- [442_interactions_20261005_87.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_87.tar.gz.dvc), member `evidence/client_interactions_20261005_ui87/volume_whole_review.json`, SHA-256 `31934ab868034fcdc3304c69b89e45b75346a69aaed6fd65e6229bd73a41f54f`.

### owned_ui_colorblind_checkbox_roundtrip

Owned primary observer107: stock Enable UI Colorblind Mode checkbox0->1->0. Public CVar, Settings boolean and settled rendered checkbox agree; original observed settings/layout and ten native checks restore.

Remaining limits: UI checkbox only. Colorblind filter staysNone. Other accessibility controls, preview rendering/layout, filter variants and persistence remain open. The long Enable UI Colorblind Mode search visually overlaps Item Quality with a following Controls header; no preview-layout acceptance is claimed.

- [442_interactions_20261005_88.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_88.tar.gz.dvc), member `evidence/client_interactions_20261005_ui88/colorblind_mouse_enable01/episode.json`, SHA-256 `dbee4252760a17396e1602d4190505801287615e133d7c267b90b1af5e05d2c7`.
  Checked cases: `settings.accessibility.change` (stock_boolean_setting_pass), `settings.accessibility.restore` (stock_boolean_setting_pass).
- [442_interactions_20261005_88.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_88.tar.gz.dvc), member `evidence/client_interactions_20261005_ui88/checkboxes_whole_review.json`, SHA-256 `fb10c0bb316aef69e1e1b324a8fb1c4b76a402c2dfa8d81cd8f1386ca936a6e5`.

### owned_mouse_sensitivity_enable_roundtrip

Owned primary observer107: stock Enable Mouse Sensitivity checkbox0->1->0. Public CVar, Settings boolean and settled rendered checkbox agree; original observed settings/layout and ten native checks restore.

Remaining limits: Enable flag only. Numeric mouseSpeed stays0.0 while the stock display reads-4. Numeric mapping/adjustment, effective pointer cadence, Mouse Look Speed, other ranges and persistence remain open.

- [442_interactions_20261005_88.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_88.tar.gz.dvc), member `evidence/client_interactions_20261005_ui88/colorblind_mouse_enable01/episode.json`, SHA-256 `dbee4252760a17396e1602d4190505801287615e133d7c267b90b1af5e05d2c7`.
  Checked cases: `settings.mouse_sensitivity.change` (stock_boolean_setting_pass), `settings.mouse_sensitivity.restore` (stock_boolean_setting_pass).
- [442_interactions_20261005_88.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_88.tar.gz.dvc), member `evidence/client_interactions_20261005_ui88/checkboxes_whole_review.json`, SHA-256 `fb10c0bb316aef69e1e1b324a8fb1c4b76a402c2dfa8d81cd8f1386ca936a6e5`.

### owned_move_pad_enable_roundtrip

Owned primary observer110: stock Show Move Pad checkbox0-to1-to0. Public CVar/Settings and rendered checkbox agree; eight enabled Move Pad controls are present only when on. Five observed layout, two control and ten native fixture checks restore.

Remaining limits: Enable/visibility only. Pad movement, dragging/position, lock, other interface controls and persistence remain open. Failed01 and capture-failed03 are excluded.

- [442_interactions_20261005_89.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_89.tar.gz.dvc), member `evidence/client_interactions_20261005_ui89/move_pad_interact04/episode.json`, SHA-256 `c3adf13b11206b1d176cdc76230d3bead2cb9568e5e284690ba732ed00179170`.
  Checked cases: `settings.interface.change` (stock_control_setting_pass), `settings.interface.restore` (stock_control_setting_pass).
- [442_interactions_20261005_89.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_89.tar.gz.dvc), member `evidence/client_interactions_20261005_ui89/stock_controls_whole_review.json`, SHA-256 `23665dbf1452410bf9822b7a93477265141b575c7fcbc62f8d618b0e01bee8ea`.
- [442_interactions_20261005_89.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_89.tar.gz.dvc), member `evidence/client_interactions_20261005_ui89/custom_script_boundary.json`, SHA-256 `253571aa007d39691fae06c1c5acb9c87a793fb46e886eebb9c11ec272674d90`.

### owned_interact_key_enable_roundtrip

Owned primary observer110: stock Enable Interact Key checkbox roundtrips canonical softTargetInteract1-to3-to1. Public proxy and rendered checkbox agree, both Interact Target bindings stay unassigned, and all observed layout/control/native checks restore the exact starting1.

Remaining limits: Checkbox only. Original historical0 remains unrestored at1 by explicit user choice; custom scripts stay blocked. Original0-start trial02 and scripted recoveries remain excluded. Actual NPC/object interaction, key assignment, other flags and persistence remain open.

- [442_interactions_20261005_89.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_89.tar.gz.dvc), member `evidence/client_interactions_20261005_ui89/move_pad_interact04/episode.json`, SHA-256 `c3adf13b11206b1d176cdc76230d3bead2cb9568e5e284690ba732ed00179170`.
  Checked cases: `settings.keyboard_controls.change` (stock_control_setting_pass), `settings.keyboard_controls.restore` (stock_control_setting_pass).
- [442_interactions_20261005_89.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_89.tar.gz.dvc), member `evidence/client_interactions_20261005_ui89/stock_controls_whole_review.json`, SHA-256 `23665dbf1452410bf9822b7a93477265141b575c7fcbc62f8d618b0e01bee8ea`.
- [442_interactions_20261005_89.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_89.tar.gz.dvc), member `evidence/client_interactions_20261005_ui89/custom_script_boundary.json`, SHA-256 `253571aa007d39691fae06c1c5acb9c87a793fb46e886eebb9c11ec272674d90`.

### owned_addons_version_check_roundtrip

Owned primary observer114: stock Load out of date AddOns checkbox false-to-true-to-false, with public version-check flag true-to-false-to-true. Both owned addon enable rows stay loaded/all-character enabled. Four layout, seven settings and ten native fixture checks restore; ordinary Cancel closes the restored panel.

Remaining limits: Version-check checkbox only. Effective out-of-date addon loading, reload/apply, addon enabling/disabling, character selection and preference persistence remain open. UI90 three failures and UI91 short-click disable failure remain whole failed/excluded; the stock DisableAddOn call leaves the requested row checked. Custom scripts stay blocked and historical softTargetInteract0 remains unrestored at1.

- [442_interactions_20261005_91.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_91.tar.gz.dvc), member `evidence/client_interactions_20261005_ui91/addons_version_check01/episode.json`, SHA-256 `3ce52a00eb1ff587b8c91f3ecba72aac9f5b39b06e0f34100489e70735f520eb`.
  Checked cases: `settings.addons.pending_version_check_change` (addons_version_check_pass), `settings.addons.pending_version_check_restore` (addons_version_check_pass).
- [442_interactions_20261005_91.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_91.tar.gz.dvc), member `evidence/client_interactions_20261005_ui91/addons_version_check_whole_review.json`, SHA-256 `96d7c393d743d7d33451512b20fbcce5fe0bb080b579d8d1cb81a9eee98a75b2`.

### owned_stationary_mouse_turn_roundtrip

Both owned primary and scout each make one 80-pixel ordinary right-button horizontal drag in each direction. Native accepted facing, rendered player facing and owned peer movement-broadcast facing agree; peer public coordinates agree, actor position stays bounded and released input is idle. Both native positions/headings, resources, stats, saved spells/actions, pose/AFK, target and solo groups restore.

Remaining limits: Stationary horizontal turning only. Camera orbit/pitch, movement while turning, sensitivity and other contexts remain open. UI92 absolute-motion trial stays whole failed/excluded; relative motion passes without relaxing acceptance bounds. Scripts stay blocked and historical softTargetInteract0 stays unrestored at1.

- [442_interactions_20261005_92.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_92.tar.gz.dvc), member `evidence/client_interactions_20261005_ui92/mouse_turn02/cohort.json`, SHA-256 `62a0577a6d2039fa8c2725f7a60a1f02f1486f5d5d729d6fdf4cd6ce3314cb4a`.
- [442_interactions_20261005_92.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_92.tar.gz.dvc), member `evidence/client_interactions_20261005_ui92/mouse_turn02/primary/episode.json`, SHA-256 `98f2a974fb76b985578f741c8ebe82f880e50b76503cb1231df528d7c9ec48bc`.
  Checked cases: `movement.mouse_turn.right` (native_mouse_turn_pass), `movement.mouse_turn.left` (native_mouse_turn_pass).
- [442_interactions_20261005_92.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_92.tar.gz.dvc), member `evidence/client_interactions_20261005_ui92/mouse_turn02/scout/episode.json`, SHA-256 `f1a357929c082fc608d89b9c4c569c1e88c3ba18fc2524d50c4b56b67277f45d`.
  Checked cases: `movement.mouse_turn.right` (native_mouse_turn_pass), `movement.mouse_turn.left` (native_mouse_turn_pass).
- [442_interactions_20261005_92.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_92.tar.gz.dvc), member `evidence/client_interactions_20261005_ui92/mouse_turn_whole_review.json`, SHA-256 `d121f3494682629dd15eb1ba201c826cc7cccce11819dd8b2d940ea25b7c4b3f`.

### owned_render_scale_apply_roundtrip

Owned primary observer115: one stock render-scale decrement1 to0.98333334922791 stays pending with actual CVar1, ordinary Apply activates the lower value, inverse step and Apply restore1. Visible render label100-to98-to100percent, public CVar/proxy and unapplied flag agree. Resolution1280x720, display/monitor and all other observed settings/CVars stay fixed. Five graphics, five layout and ten native checks restore.

Remaining limits: One render-scale variant only. Quality presets, resolution/window/monitor changes, performance and persistence remain open. No allocation above the original100percent is requested. Scripts stay blocked; historical softTargetInteract0 remains unrestored at1.

- [442_interactions_20261005_93.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_93.tar.gz.dvc), member `evidence/client_interactions_20261005_ui93/render_scale01/episode.json`, SHA-256 `0f433abd2687eda5b6fdbc8f8267c337320e52a1df419c4c9106ca227bac240d`.
  Checked cases: `settings.render_scale.lower_pending` (stock_render_scale_pending_pass), `settings.apply.render_scale_lower` (stock_render_scale_apply_pass), `settings.render_scale.original_pending` (stock_render_scale_pending_pass), `settings.apply.render_scale_original` (stock_render_scale_apply_pass).
- [442_interactions_20261005_93.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_93.tar.gz.dvc), member `evidence/client_interactions_20261005_ui93/render_scale_whole_review.json`, SHA-256 `a3b65e781ff63530aedefbc511d5a899f1672a16582a0aee03982f8bdfe129f5`.

### owned_settings_exit_cancel_discard

Owned primary observer117: one lower pending render-scale step leaves actual CVar1; the exact stock GAME_SETTINGS_CONFIRM_DISCARD Cancel closes only its dialog and preserves the pending edit. A second ordinary Close and Exit discard the edit, restoring CVar/proxy1 and clearing unapplied state without Apply. Cleanup reopens Settings and restores five graphics, five layout and ten native checks.

Remaining limits: Pending render-change exit Cancel and discard variant only. Other dialogs/settings, defaults and persistence remain open. Whole settings_discard01/02 failures remain excluded; their later source-bound cleanup passes add no qualification. Caption correction for settings_discard_whole_review.json visual_review[3]: reopened capture shows the original Controls category; encoded public probe confirms applied and pending RenderScale1 at1280x720. It does not visibly show the render-scale slider. Scripts stay blocked and historical softTargetInteract0 remains unrestored at1.

- [442_interactions_20261005_93.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_93.tar.gz.dvc), member `evidence/client_interactions_20261005_ui93/settings_discard03/episode.json`, SHA-256 `b52ed722eb62b0ddb3d1b6d866935af881fe06dacc7bf9a7c1b51cdae05ea867`.
  Checked cases: `settings.cancel.render_scale_pending` (stock_render_scale_pending_pass), `settings.cancel.keep_pending` (stock_settings_exit_choice_pass), `settings.cancel.discard_pending` (stock_settings_exit_choice_pass).
- [442_interactions_20261005_93.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_93.tar.gz.dvc), member `evidence/client_interactions_20261005_ui93/settings_discard_whole_review.json`, SHA-256 `ba21bfdc0f909ebfd56e92c3b241596c1f5ab2e251cd00baff689d215f47e6ea`.

### owned_render_scale_ui_reload_persistence

Owned primary observer117: apply one lower stock RenderScale step1 to0.98333334922791, close Settings and submit the verified ordinary /reload, then reopen Settings with active/pending scale unchanged and no unapplied edit. Reset observer sequence3187-to11, owned GUID and unchanged native session8657730f prove a new UI generation. Inverse step and Apply restore1, which survives another verified reload with sequence199-to11. Five graphics, five layout and ten native checks restore. Reviewed post-first-reload search shows98percent render label at1280x720; reopened post-reload panels show original Controls category and their encoded probes establish exact values.

Remaining limits: Applied render-scale persistence through ordinary UI reload only. Full client restart, storage-level/account/character and other-setting persistence remain open. Earlier launch constructor TypeError sent no input and is retained/excluded. All109 final focused checks pass; earlier1418 full protocol checks passed before the launcher argument repair. Scripts stay blocked; historical original softTargetInteract0 remains unrestored at stock-disabled1.

- [442_interactions_20261005_94.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_94.tar.gz.dvc), member `evidence/client_interactions_20261005_ui94/settings_persistence01/episode.json`, SHA-256 `84f4e32b7dae594a0b83e1206f4df25e33e69dc1d742ca6c7a6098f1ac3d793d`.
- [442_interactions_20261005_94.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_94.tar.gz.dvc), member `evidence/client_interactions_20261005_ui94/settings_persistence_whole_review.json`, SHA-256 `641f93151e90b6573e0d91371f6d7d954c57fb531ac2751d55fdd76ff7be4ccb`.

### owned_pending_graphics_quality_discard

Owned primary observer118: exact Base quality Back widget selects pending index1-to0, visible level2-to1. All10 child proxies agree with the installed read-only GetGraphicsCVarValueForQualityLevel map, including minimum particle density1, while all active CVars stay byte-identical. Ordinary Close and the exact Exit choice discard the pending preset without Apply. Reopened Settings verifies original quality index1 and all child proxies; five quality, five layout and ten native checks restore. Reviewed images show initial level2, pending level1 with Apply visible, exact exit confirmation, restored Controls category and final seated world HUD.

Remaining limits: Pending lower base-quality selection/discard only. Applied presets, other levels, allocation/performance and restart persistence remain open. Reopened restoration image shows Controls; encoded settings probe proves original quality values and does not visibly show the slider. All138 focused and1448 full tests pass. Scripts stay blocked; original softTargetInteract0 remains unrestored at stock-disabled1.

- [442_interactions_20261005_95.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_95.tar.gz.dvc), member `evidence/client_interactions_20261005_ui95/quality_pending01/episode.json`, SHA-256 `fb3e2b87845d9c436ede30f209122bdbc0187b063665833fe806f94368fbf76b`.
- [442_interactions_20261005_95.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_95.tar.gz.dvc), member `evidence/client_interactions_20261005_ui95/quality_whole_review.json`, SHA-256 `eda9892d2411bc56ae0cd7915658d713e887f515bf9b8bc6c79472cda36fa92b`.
- [442_interactions_20261005_95.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_95.tar.gz.dvc), member `evidence/client_interactions_20261005_ui95/quality_source_review.json`, SHA-256 `2aca2930757f08ecef9b853f7387efb5fa23410caa43063b65d1ece7ca21e5bc`.

### owned_pending_display_selection_discard

Owned primary observer119: one stock stepper per pending display setting selects Resolution1280x720-to1152x720, Windowed-toWindowed(Fullscreen), and private nested Monitor0-to1(Generic Non-PnP Monitor). Each ordinary Close and exact Exit discards before Apply. All observed active CVars and actual C_VideoOptions window1280x720 remain fixed, logical screen metrics remain unchanged, all other proxies preserve the baseline, and owned physical geometry stays onHDMI-1. Each pending case passes7 checks, each discard restoration passes6, and final display4/layout5/native10 checks restore. Six reviewed images include the three selectors, exit confirmation, reopened Controls category and closed world HUD.

Remaining limits: Pending selections and stock discard only. Applying display changes, other options, full client restart/persistence, allocation/performance and physical-monitor switching remain open. Private Primary/Monitor labels do not identify the physical host monitor. Reopened restoration capture shows Controls; its encoded probe proves original display values. All174 focused and1484 full protocol tests pass. Scripts stay blocked; original softTargetInteract0 remains unrestored at stock-disabled1.

- [442_interactions_20261005_96.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_96.tar.gz.dvc), member `evidence/client_interactions_20261005_ui96/display_pending01/episode.json`, SHA-256 `f0fb8be8f978f49ad12de41de7953a736056445a2d510840f39fa386b0913ef2`.
  Checked cases: `settings.resolution.pending` (stock_pending_display_selection_pass), `settings.window_mode.pending` (stock_pending_display_selection_pass), `settings.monitor_selection.pending` (stock_pending_display_selection_pass).
- [442_interactions_20261005_96.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_96.tar.gz.dvc), member `evidence/client_interactions_20261005_ui96/display_whole_review.json`, SHA-256 `faa50bdb7d01947f9b20851723e1251ede230b224a9b291f482025210fc1ec4a`.
- [442_interactions_20261005_96.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_96.tar.gz.dvc), member `evidence/client_interactions_20261005_ui96/display_source_review.json`, SHA-256 `85452412f9340a4adb19132a180a6becdb01516d99ecad81b2c46d52492fa212`.

### owned_colorblind_current_category_defaults

Owned primary observer120: enable UI Colorblind Mode through the stock checkbox, then exact Defaults confirmation button3 These Settings(CURRENT_SETTINGS) applies the current-category default immediately, restoring public CVar0 and Setting false. Exact object ownership proves the category contains only mode, simulator and weakness. Simulator0 and weakness0.5 already equal their typed defaults and stay unchanged. All other observed CVars/settings and actual display remain fixed. Ten action checks, five value-restoration, five layout and ten native checks pass. Four reviewed images show checked mode, exact three-choice dialog, unchecked restored mode with None/50percent and final closed world HUD.

Remaining limits: One Colorblind Mode current-category default only. All Settings, other categories, keybinding/graphics defaults, pending graphics Apply and persistence remain open. No allocation increase, native build, new client/server or model job. All168 focused and1526 full protocol checks pass. Scripts stay blocked; historical softTargetInteract0 remains unrestored at stock-disabled1.

- [442_interactions_20261005_97.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_97.tar.gz.dvc), member `evidence/client_interactions_20261005_ui97/defaults_apply01/episode.json`, SHA-256 `65ab574f83e64d8154a7d670f7e4950efa7c9fbb315b53b7d32a2a202ed4d73d`.
  Checked cases: `settings.defaults_apply.current_colorblind` (stock_current_category_defaults_pass).
- [442_interactions_20261005_97.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_97.tar.gz.dvc), member `evidence/client_interactions_20261005_ui97/defaults_whole_review.json`, SHA-256 `150a38aaaedc440aee5bd3e041aadf07fd62c367898a95f0459496a7c05462f0`.
- [442_interactions_20261005_97.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_97.tar.gz.dvc), member `evidence/client_interactions_20261005_ui97/defaults_source_review.json`, SHA-256 `9e013e9889cf2f64f24ce7d36cf71adc7dc5a13a88d68a4339ba6a2b644bc8be`.

### owned_existing_quest_link_cancel

Owned primary observer121: stock Shift-left-click on the attributed existing quest28825 A Personal Summons row at zero offset inserts its exact public green quest28825:80 link into blank focused Say chat. Escape cancels without submission; all nine action checks, six pending-link checks and the complete owned packet window show no chat message or cast. Quest rows, collapsed Stormwind header, watch0, original selection0, observed settings and all native fixture fields restore through separately reviewed ordinary same-character logout/reentry. Ten layout, ten native and fourteen quest/settings restoration checks pass. Actual pending-link and final HUD images are reviewed and the archive is remotely verified.

Remaining limits: One existing owned completed-unrewarded quest and one blank-chat insertion/cancellation only. Delivery, hyperlinks, other quests, nonzero offsets and other chat contexts remain open. Calibrations01 and02 remain failed and excluded: ordinary reload retained selection2, and a passive settings page was missed. Exact cleanup recovered selection0; fresh calibration03 and quest_link01 whole final phases pass. Fixed observer settings diagnostics are read-only and unqualified; AFK restores afterward. All86 focused and1613 final protocol tests pass. No new client/server/model or native build. Scripts stay blocked; historical softTargetInteract0 remains unrestored at stock-disabled1.

- [442_interactions_20261006_98.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_98.tar.gz.dvc), member `evidence/client_interactions_20261006_ui98/quest_link01_begin/episode.json`, SHA-256 `0a2156ae51784c935c031fdcc8347805cf3eebb6ea4d2d50aa146b5a2d5af135`.
  Checked cases: `ui_misc.quest_link` (stock_chat_link_pass).
- [442_interactions_20261006_98.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_98.tar.gz.dvc), member `evidence/client_interactions_20261006_ui98/quest_link01_finish/episode.json`, SHA-256 `8276726dec85683ee75ec837f6f0477eeb1a54113422a182976b75d6511b9bf6`.
- [442_interactions_20261006_98.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_98.tar.gz.dvc), member `evidence/client_interactions_20261006_ui98/quest_link_whole_review.json`, SHA-256 `8d23a52b10feeec2b6aabddae103e081208008a96feb7c1207a9c89ef8b10653`.
- [442_interactions_20261006_98.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_98.tar.gz.dvc), member `evidence/client_interactions_20261006_ui98/layout_calibration03_whole_review.json`, SHA-256 `37ab95f6f03d7d979d6f73732a94ba9ab8664cad1b0d24d8fd6b6fee5dfb6b37`.
- [442_interactions_20261006_98.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_98.tar.gz.dvc), member `evidence/client_interactions_20261006_ui98/source_qa.json`, SHA-256 `01bb255cd164fe42b721ad1353824a792c94959ec0ccdd2b6769a9bc49618d25`.

### owned_bridge_restart_disconnect_notification

Historical UI81 controlled owned bridge restart: both owned build60895 clients display the stock server-disconnected modal with WOW51900319. Actual images, monitor/game PID identities, closed deployment and completed same-actor native restoration prove this notification variant. Both actual screens show the modal text and visible Okay/Reconnect controls. Original UI81 archive (785,300,746 bytes), SHA-256 619b0ff5338bcab025a41759b43704cf9729a8bc05c2d0cfb17526760adabac7 and MD5 6b41917f4bb79f44797151ffb4669c00 were streamed and verified without restoring an archive/cache copy. Both actor reentry episodes are whole completed with all nine native checks passing.

Remaining limits: Captured notification after one controlled bridge restart only. Other disconnect causes, timers, network loss, transport variants, error codes, reconnect-button behavior and current bridge-build fault testing remain open. This is evidence reconciliation, with no new game input or client/server restart. Historical controllers remain code with model None. No new disconnect or reentry input was sent. Scripts stay blocked; historical softTargetInteract=0 remains unrestored at stock-disabled 1.

- [442_interactions_20261005_81.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_81.tar.gz.dvc), member `evidence/client_interactions_20261005_ui81/skill_bridge_deploy02/deployment.json`, SHA-256 `8a3b8044956cfe0423cf4b90dec22712b11c77347a08b6134cd3e716d2e8ecf4`.
- [442_interactions_20261005_81.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_81.tar.gz.dvc), member `evidence/client_interactions_20261005_ui81/deployment_visual_review.json`, SHA-256 `34af57cab33ec3d220fcf95310f7ec6ae3dccda4f715aa4444f78d03534c7a6e`.
- [442_interactions_20261005_81.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_81.tar.gz.dvc), member `evidence/client_interactions_20261005_ui81/skill_bridge_deploy02/primary_after/episode.json`, SHA-256 `933f1d5c659d3b42551ccf4d7d0db5a993b13c22b79a4856e8e8fc2d5724dc88`.
- [442_interactions_20261005_81.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261005_81.tar.gz.dvc), member `evidence/client_interactions_20261005_ui81/skill_bridge_deploy02/scout_after/episode.json`, SHA-256 `2e0b17bfc4d1a94c3e771c8bc886cdfa607e0c3c0fc24b75efdcfced488474a8`.
- [442_network_notification_review_20261006_01.tar.gz.dvc](../../artifacts/client_harness/442_network_notification_review_20261006_01.tar.gz.dvc), member `evidence/network_notification_review_20261006/notification_reconciliation.json`, SHA-256 `5bfc5b02dfb095171b53eb257cb154257bca9caaad573d01d679006fe2126edf`.

### owned_native_letter_text

UI99 item_text01 whole completed pass on owned Harnessone/build60895: ordinary bag Right Click to Read opens native item910 An Undelivered Letter; stock Next and Previous show the exact native pages18/19 and return to page1; stock Close removes the panel. Native owned GUID/position, READ_ITEM_OK, both PAGE_TEXT replies and the exact modern vector chain match the passive public title/page/text and actual rendered pages. All nine native and nine readable restoration checks pass, both narrow fixture permission grants are revoked, and the disposable letter is absent. Same primary session, native worldserver and both client lifetimes are preserved. Controller code, model None.

Remaining limits: One owned native letter910 with default material and two public static pages only. Dynamic item text, other materials, long chains, denied reads and error UX remain open. Bag preparation is not an extra qualification. One failed offline deployment precheck and its source-bound ordinary reentry remain separate and excluded; the completed bridge deployment leaves the scout parked at character selection. Scripts stay blocked; historical original softTargetInteract=0 remains unrestored at stock-disabled1.

- [442_interactions_20261006_99.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_99.tar.gz.dvc), member `evidence/client_interactions_20261006_ui99/item_text01/episode.json`, SHA-256 `96ec8be21e10cc88131e0cc93e383e7ee5143ff728c6a160adf5ccbed5bd13b3`.
  Checked cases: `ui_misc.item_text_open` (stock_item_text_pass), `ui_misc.item_text_page.next` (stock_item_text_page_pass), `ui_misc.item_text_page.previous` (stock_item_text_page_pass), `ui_misc.item_text_close` (stock_item_text_close_pass).
- [442_interactions_20261006_99.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_99.tar.gz.dvc), member `evidence/client_interactions_20261006_ui99/whole_trial_review.json`, SHA-256 `0520e90d7988abea49acf454c83b4a9c493648b7226e23782c08542f83dc6dd7`.
- [442_interactions_20261006_99.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_99.tar.gz.dvc), member `evidence/client_interactions_20261006_ui99/bridge_item_text_deployment02/deployment.json`, SHA-256 `45d0fd934eef257861be365a1715c4b08f2661ff7b0c5c36a90ba9bcd8175319`.
- [442_interactions_20261006_99.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_99.tar.gz.dvc), member `evidence/client_interactions_20261006_ui99/verification.json`, SHA-256 `17442668486162213345becf04e258e00a27fd2034c02eff818091ae02a0a57e`.
- [442_interactions_20261006_99.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_99.tar.gz.dvc), member `evidence/client_interactions_20261006_ui99/runtime_closure.json`, SHA-256 `faa6ca5c791805ed23151a4efb50b1d7187f77e1a49754f0adb1224d0b0f836e`.

### owned_offline_friend_removal_errors

UI100 friends04 whole completed pass on owned Harnessone/build60895: ordinary stock Add Friend confirmation revalidates previously counted addition of the owned offline Harnessdwarf GUID3. Duplicate, self and verified missing-name requests produce exact native results8/9/4, unchanged native/public lists and their rendered stock messages. Right-click on the exact dwarf row and observed Remove Friend menu produce native result5 and remove only that row; no removal chat line is claimed. Every main case passes12 wire/native/public/UI checks, and all9 native plus12 friend restoration checks pass. Original Harnesstwo, both social rows, actor inventories/money, quest layout, session, group, seated pose and AFK restore. Code controller, model None.

Remaining limits: Four newly counted operations; friend addition was already qualified. Only the owned offline dwarf and exact duplicate/self/nonexistent errors. Online presence, note editing/persistence, limits, ignore and other social variants remain open. Four whole failed runs retain their failed verdicts and are excluded, including bare-name autocomplete refusal and the no-packet fully qualified removal route. Source-bound menu cleanup passes separately. No additional clients, native build or server/bridge restart. Scripts stay blocked; historical original softTargetInteract=0 remains unrestored at stock-disabled1.

- [442_interactions_20261006_100.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_100.tar.gz.dvc), member `evidence/client_interactions_20261006_ui100/friends04/episode.json`, SHA-256 `2df3892277444f4938652bbc0d8c5cd58e565465c458ea97df54c09f596d7d93`.
  Checked cases: `friends.add_friend` (friend_status_pass), `friends.remove_friend` (friend_status_pass), `friends.duplicate_friend_error` (friend_status_pass), `friends.self_friend_error` (friend_status_pass), `friends.nonexistent_friend_error` (friend_status_pass).
- [442_interactions_20261006_100.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_100.tar.gz.dvc), member `evidence/client_interactions_20261006_ui100/whole_friend_review.json`, SHA-256 `c2f449baa2bbc70bf8ce5ffa1581391391737886e1f5b9e6d06e3adff1a695a8`.
- [442_interactions_20261006_100.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_100.tar.gz.dvc), member `evidence/client_interactions_20261006_ui100/source_cleanup_review.json`, SHA-256 `685bb6214fa97c5b6a274d35045b5901809ad9d77ebf9f51b8dd4472c1446556`.
- [442_interactions_20261006_100.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_100.tar.gz.dvc), member `evidence/client_interactions_20261006_ui100/verification.json`, SHA-256 `76d83fab110981858c3e5b417d35cfc078a2b492476a52cf893d0cf052411584`.
- [442_interactions_20261006_100.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_100.tar.gz.dvc), member `evidence/client_interactions_20261006_ui100/runtime_closure.json`, SHA-256 `6136bb76aa5e1fcd9946e73a7454554af84c6691eb2929723a4fadbd6acda0d7`.

### owned_offline_friend_note

UI101 note_edit01 whole completed pass on owned Harnessone/build60895. Exact Harnesstwo row menu Set Note opens the source-reviewed Set Notes for Harnesstwo dialog. Ordinary edit and Accept save the short ASCII marker Owned offline scout note UI101. One exact modern/native CMSG_SET_CONTACT_NOTES request agrees with the native SQL note and passive public friends; the actual stock hover tooltip displays the saved note. The same stock dialog restores the original empty note, and the reviewed tooltip loses note text/icon. Both note actions pass10 checks, all9 native and12 friend restoration checks pass, and both actors inventories/money, original social rows, quest layout, session, group, pose and AFK restore. Code controller, model None.

Remaining limits: One short ASCII note on the original owned offline scout friend, then empty-note restoration. Reload/reentry persistence, longer and Unicode notes, online presence and other social variants remain open. Native note handler has no acknowledgement; qualification uses exact requests, SQL/public agreement and rendered tooltip. The completed dialog probe is setup only. All17 focused and1714 full protocol tests pass; no failures, native build, restart or extra client. Scripts stay blocked; historical original softTargetInteract=0 remains unrestored at stock-disabled1.

- [442_interactions_20261006_101.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_101.tar.gz.dvc), member `evidence/client_interactions_20261006_ui101/note_edit01/episode.json`, SHA-256 `a4fdc2a4a3fa6949bc7738b7e33050834f554928aa517db54d097bffd83bdb93`.
  Checked cases: `friends.note_edit` (friend_note_edit_pass), `fixture.friend_note.restore` (friend_note_edit_pass).
- [442_interactions_20261006_101.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_101.tar.gz.dvc), member `evidence/client_interactions_20261006_ui101/whole_note_review.json`, SHA-256 `5c463200f995d83737ef6f42bc1cdf2ed34c79669816c681883ee9262504d02f`.
- [442_interactions_20261006_101.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_101.tar.gz.dvc), member `evidence/client_interactions_20261006_ui101/note_probe_review.json`, SHA-256 `d3d7fbdd9780bcbadfe54bc79b75bb7f831e25e3ddfc0b4ec3105c18c50df132`.
- [442_interactions_20261006_101.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_101.tar.gz.dvc), member `evidence/client_interactions_20261006_ui101/verification.json`, SHA-256 `ac9b48b60a7dd0e30a628c32faffe5ffd8ac081e67833fbbb4bcd7be3fcb9a11`.
- [442_interactions_20261006_101.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_101.tar.gz.dvc), member `evidence/client_interactions_20261006_ui101/runtime_closure.json`, SHA-256 `f4c21d158f9bb6509e105aeccf0fdf93e359bc6ae88405c2625353ea49e1ea44`.

### owned_offline_dwarf_ignore

UI102 ignore01 whole completed pass on owned Harnessone/build60895. Observed stock Ignore Player name dialog accepts only owned offline Harnessdwarf GUID3. Exact modern/native add requests and result15 agree with the native ignored flag2 and sole rendered/public-control Harnessdwarf row. Ordinary selection of that exact row and stock Remove Player produce exact result16 and an empty Ignore list with removal disabled. Both main cases pass12 wire/native/public/UI checks; all9 native,12 friend and2 Ignore restoration checks pass. Original social rows, friend list, both actors inventories/money, offline dwarf, quest layout, session, group, pose and AFK restore. Code controller, model None.

Remaining limits: Owned offline dwarf addition/removal only. Ignored chat, online presence, persistence, limits and other social variants remain open. Addition system message is rendered; no removal system message is claimed. Probe is setup only. Initial review caption was corrected before archive creation/acceptance, with interrupted packaging recorded separately. All19 focused and1733 full tests pass; no live failures, native build, restart or extra client. Scripts stay blocked; historical original softTargetInteract=0 remains unrestored at stock-disabled1.

- [442_interactions_20261006_102.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_102.tar.gz.dvc), member `evidence/client_interactions_20261006_ui102/ignore01/episode.json`, SHA-256 `c2944ca1ff35c8ca00b83f1a494520484a7206023160e07f4e99812c15a03085`.
  Checked cases: `friends.add_ignore` (ignore_status_pass), `friends.remove_ignore` (ignore_status_pass).
- [442_interactions_20261006_102.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_102.tar.gz.dvc), member `evidence/client_interactions_20261006_ui102/whole_ignore_review.json`, SHA-256 `b480f23c1304c0c98d6efba9b3334e0165b1546e76a76e60a68ee7806727402a`.
- [442_interactions_20261006_102.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_102.tar.gz.dvc), member `evidence/client_interactions_20261006_ui102/ignore_probe_review.json`, SHA-256 `59286ec1751d3150b696f635ba9dffb6d7892dc8bbfa9aa682f778c640a06b70`.
- [442_interactions_20261006_102.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_102.tar.gz.dvc), member `evidence/client_interactions_20261006_ui102/verification.json`, SHA-256 `8f5b1d58f8484b5ce968fac6c7851738219ad6191e32606f88da6a3cd3a64f57`.
- [442_interactions_20261006_102.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_102.tar.gz.dvc), member `evidence/client_interactions_20261006_ui102/runtime_closure.json`, SHA-256 `a7cc6064ae8ae23255f55ee382cf57e3f9f0769a929081c1f9add6e55e397ff7`.

### owned_current_offline_friend_and_who_open

UI103 friend_reads01 whole completed pass on owned Harnessone/build60895. Current original Harnesstwo GUID2/account2 is the sole native friend and stock named row; passive public friend count/name/empty note agree with SQL. Native character online0 agrees with public connected false and offline level0. Actual images show the grey Harnesstwo row, Unknown beneath it and name-only hover tooltip. Ordinary bottom Who tab opens the stock Who List with search field, enabled Refresh and disabled Add Friend/Group Invite. The three cases pass9/10/8 checks, and all9 native plus12 friend restoration checks pass. Original social, inventories/money, quest layout, session, group, pose and AFK restore. Code controller, model None.

Remaining limits: One current owned offline game-character entry and list display only. No online/offline transition, BNet/account presence, server-refresh acceptance, long lists or other presence variants. Who pane opening only: no query was sent and the pre-search 0 People Found display does not qualify results. New read-only adapter syntax/diff checks pass; prior UI102 foundation suite1733 passed, with no redundant full-suite rerun. No live/test failures, build, restart or extra client. Scripts stay blocked; historical original softTargetInteract=0 remains unrestored at stock-disabled1.

- [442_interactions_20261006_103.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_103.tar.gz.dvc), member `evidence/client_interactions_20261006_ui103/friend_reads01/episode.json`, SHA-256 `ceb5ae4479b57ec65727277c088e52d6820ad0aa97bffe4e36946b9691c79de8`.
  Checked cases: `friends.list` (owned_offline_friend_read_pass), `friends.offline_presence` (owned_offline_friend_read_pass), `friends.who_open` (stock_who_open_pass).
- [442_interactions_20261006_103.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_103.tar.gz.dvc), member `evidence/client_interactions_20261006_ui103/whole_friend_read_review.json`, SHA-256 `bf612456f68a7837287a496d7ab222d1dee76b35b67d1a4499c24d246b316353`.
- [442_interactions_20261006_103.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_103.tar.gz.dvc), member `evidence/client_interactions_20261006_ui103/verification.json`, SHA-256 `5f4a7c5c7bb5c0b1dd36723fe437c79e482d20165eae95d9ab8ce5cd48c324c7`.
- [442_interactions_20261006_103.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_103.tar.gz.dvc), member `evidence/client_interactions_20261006_ui103/runtime_closure.json`, SHA-256 `261414bf060c6c30d987c308c75b28c87e146ae4cd3308c8ce4db056c1b6812f`.

### owned_native_who_name_search

UI104 who_search01 whole completed pass on owned Harnessone/build60895. One ordinary n-Harnessone stock query and Refresh click produce exactly one modern request, translated native request, native Who response and correlated modern response. RequestID1 is echoed; GUID1, name, level85, class1, race1, native gender0, empty guild and Badlands area3 agree. Passive public Who getters and actual stock columns show Harnessone, Badlands,85,Warrior and 1 Person Found. The case passes21 wire/public/UI checks; all8 pre-repair fixture,9 native and12 friend restoration checks pass. Original query field is empty and panels/chat close. Code controller, model None.

Remaining limits: One owned-primary name query only. No filtered-race, cross-realm/enemy/arena/addon queries, non-ASCII exact-name folding, sorting, selection, invitation, whisper, missing-name results or long lists acceptance. Transient Who cache changes0 to1 and remains as the read response; no extra cleanup query was sent. Whole failed unmapped who_probe01 is retained and excluded. Two failed C++ builds,46 fixture failures and4 independent-reader failures were corrected and retained;46 focused and1786 full tests pass. Historical priming regression fails once at2500 retained records; streaming fix peaks at<=2 and full memory foundation1740 passes. Native worldserver/client lifetimes unchanged; bridge alone restarted with one build job and scout parked offline. Scripts stay blocked; original softTargetInteract0 remains unrestored at stock-disabled1.

- [442_interactions_20261006_104.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_104.tar.gz.dvc), member `evidence/client_interactions_20261006_ui104/who_search01/episode.json`, SHA-256 `1e9f853cbb674e4d5b784975cbf0454155a8d0790d8993e0feb9af3544410600`.
  Checked cases: `friends.who_search` (owned_who_search_pass).
- [442_interactions_20261006_104.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_104.tar.gz.dvc), member `evidence/client_interactions_20261006_ui104/whole_who_review.json`, SHA-256 `86a58f451fc4ae8d6430a264d9e7ad52ea5519408f2dd6ea23d8268abce19853`.
- [442_interactions_20261006_104.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_104.tar.gz.dvc), member `evidence/client_interactions_20261006_ui104/verification.json`, SHA-256 `3dc816b6337fe4dbdb36758054946dd5f5bfb3a1d143058433ddd72c18717072`.
- [442_interactions_20261006_104.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_104.tar.gz.dvc), member `evidence/client_interactions_20261006_ui104/memory_verification.json`, SHA-256 `c8391556390dff047a1927c12e4756254e87a8420ddb3a4c1a6bc693a16f85ba`.
- [442_interactions_20261006_104.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_104.tar.gz.dvc), member `evidence/client_interactions_20261006_ui104/runtime_closure.json`, SHA-256 `67d4b5c9b501099ff2060b8175aa8d379f1a58da70e1c33888c2c1d6da24635a`.

### owned_offline_friend_note_persistence

UI105 closed whole note_prepare02 plus note_finish02 pass on owned Harnessone/build60895. One short ASCII note on the original offline Harnesstwo friend survives ordinary same-character logout/reentry. All5 logout,5 reentry and10 persistence checks pass. Native and modern reloaded contact lists and public Friends agree on GUID2 and the marker, with no note rewrite after login; the actual stock tooltip shows the note. Exact empty-note restoration passes10 checks; all9 native and12 friend restoration checks pass against the original pre-logout fixture. Code controller, model None.

Remaining limits: Only normal character logout/reentry for one owned offline friend and short ASCII note. Full-client restart, account-service persistence, online notes and other social variants remain open. Whole failed note_prepare01 is retained and excluded; diagnosis and fully restored note_recovery01 are cleanup-only. Existing reader assumed one race-unlock row, rejecting the live12-row trailer; it now consumes the declared count. The adapter now expects packed local address0x01010001. New regression first fails3/passes1; a later test placement error causes12 NameErrors, corrected before input; final focused69 pass. One source lobby caption incorrectly claimed a rendered equipment model; the unchanged input-bound review has a separate caption correction, and gear proof comes from the packet. No native C++ change, build, restart or added client. Scripts stay blocked; original softTargetInteract0 remains unrestored at stock-disabled1.

- [442_interactions_20261006_105.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_105.tar.gz.dvc), member `evidence/client_interactions_20261006_ui105/note_finish02/episode.json`, SHA-256 `f37aa8c6b821016642f570ed45304ba717a99f1e56283888eb6c23f1e33b598b`.
  Checked cases: `friends.note_persist` (friend_note_persistence_pass).
- [442_interactions_20261006_105.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_105.tar.gz.dvc), member `evidence/client_interactions_20261006_ui105/note_prepare02/episode.json`, SHA-256 `cb6f89b82b654aca6913f11e2746d679b4aba4ff19674d415a17e9778dc28013`.
- [442_interactions_20261006_105.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_105.tar.gz.dvc), member `evidence/client_interactions_20261006_ui105/whole_note_persistence_review.json`, SHA-256 `20eb50b0bbd8e327c8adc3b1f8e83a0adf6ee0de738b78fa600caeca9945c57b`.
- [442_interactions_20261006_105.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_105.tar.gz.dvc), member `evidence/client_interactions_20261006_ui105/decoder_verification.json`, SHA-256 `6e2dab116854dea514c38d3b61033cf3716b1031849319fe02a3a132fae1e9f4`.
- [442_interactions_20261006_105.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_105.tar.gz.dvc), member `evidence/client_interactions_20261006_ui105/failed_prepare_recovery_review.json`, SHA-256 `3c6fac3b49fd5011b34cb0c4bd0c54d14d83729f68642cc0105c27b639a6859a`.
- [442_interactions_20261006_105.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_105.tar.gz.dvc), member `evidence/client_interactions_20261006_ui105/selection_caption_correction02.json`, SHA-256 `0dfacbbe99c74150027965f5577ebffc392db12cc327d0bb99c9e77e26158d2f`.
- [442_interactions_20261006_105.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_105.tar.gz.dvc), member `evidence/client_interactions_20261006_ui105/runtime_closure.json`, SHA-256 `edd367f59797707d1770d49df8756e5a22f386f15cdae24c2ac0724d77545538`.

### owned_friend_presence_whisper

UI106 closed whole friend_presence02 plus cache_prepare02/cache_finish02 pass on the two owned same-realm actors. Exact native/modern status2 and public/stock Friends show Harnesstwo online at level1; stock Send Message opens the exact owned WHISPER recipient and one guarded Return delivers the short marker to Harnesstwo. Native requests, sender echo, peer GUID and modern/public/actual chat agree. Normal scout logout gives exact status3 and19 parked persistent checks. The installed client retains last-known level1 offline, so qualification also requires source-bound ordinary primary logout/reentry to restore the original level0 cache. All5 logout,5 reentry,3 cache,9 native,12 friend and1 chat-settings checks pass against10 carried original fields. Code controller, model None.

Remaining limits: One owned same-realm friend presence cycle and one short stock Send Message whisper. Ignored-chat, other social variants and learned autonomy remain open. Historical whole friend_presence01 remains failed/excluded: the old bare-name row predicate misses the online level/class label, and offline retains cached level1; no whisper was sent. Cleanup01 restores original0 and provides no qualification. Initial test collection SyntaxError is corrected before input; final focused76 pass. A review helper first used the main Pixi environment without PIL; archive scan was interrupted before creating its archive/pointer, then review and checkpoint were rerun correctly. The source scout parked image still shows the last logout countdown; later runtime closure verifies actual character selection. Native server, bridge and both clients retain their lifetimes, no C++ changes/builds/client additions. Scripts stay blocked; original softTargetInteract0 remains unrestored at stock-disabled1.

- [442_interactions_20261006_106.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_106.tar.gz.dvc), member `evidence/client_interactions_20261006_ui106/friend_presence02/primary/episode.json`, SHA-256 `66683849b99cee18e9716a7362328145967254ac5c8c738866231824c0d117de`.
  Checked cases: `friends.online_presence` (owned_friend_presence_pass), `friends.whisper` (owned_friend_whisper_pass).
- [442_interactions_20261006_106.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_106.tar.gz.dvc), member `evidence/client_interactions_20261006_ui106/friend_presence02/cohort.json`, SHA-256 `5215bdc9dc8f057cf8389880adfe5fff42559841a47f20e1dafd28b2c8b80d36`.
- [442_interactions_20261006_106.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_106.tar.gz.dvc), member `evidence/client_interactions_20261006_ui106/friend_presence02/scout/episode.json`, SHA-256 `d6bc42a192c4c9c36956ea287fc4fe26b70d1d0adcc0b519a0cbf33013091ace`.
- [442_interactions_20261006_106.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_106.tar.gz.dvc), member `evidence/client_interactions_20261006_ui106/cache_prepare02/episode.json`, SHA-256 `a03305f5f0b06c33f19041297cdfafad525fd1732666a8f9b7571f7f8d0e7414`.
- [442_interactions_20261006_106.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_106.tar.gz.dvc), member `evidence/client_interactions_20261006_ui106/cache_finish02/episode.json`, SHA-256 `2ae4eee7fb2cae1304f8c1d0fa88d5e654194b89aa03ab8c8f8ab6216208c8d8`.
- [442_interactions_20261006_106.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_106.tar.gz.dvc), member `evidence/client_interactions_20261006_ui106/whole_presence_whisper_review.json`, SHA-256 `89217b5972bf40b97d8b8d14291fa96d87684189799c968ced5a5ff8c4adf88b`.
- [442_interactions_20261006_106.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_106.tar.gz.dvc), member `evidence/client_interactions_20261006_ui106/failed_presence_review01.json`, SHA-256 `b6b4117ec1007569435f64210bc1580f662b564fd667d2a846ef18004d7d0191`.
- [442_interactions_20261006_106.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_106.tar.gz.dvc), member `evidence/client_interactions_20261006_ui106/cache_recovery_review01.json`, SHA-256 `ca3e94d006cfb753a97e5bbc13d686daa73151163440b4f392b13e0cb1387a27`.
- [442_interactions_20261006_106.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_106.tar.gz.dvc), member `evidence/client_interactions_20261006_ui106/verification.json`, SHA-256 `591660fb86b36b6a370c80648c73f5db5ec4b7a72b86e244d2a2f3e9440cb5e8`.
- [442_interactions_20261006_106.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_106.tar.gz.dvc), member `evidence/client_interactions_20261006_ui106/row_cache_verification02.json`, SHA-256 `2c5fecc74488237fca81ed3967ce773f459f3459f4d44dda8f1bf33a846a5af1`.
- [442_interactions_20261006_106.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_106.tar.gz.dvc), member `evidence/client_interactions_20261006_ui106/archive_preparation_diagnostic.json`, SHA-256 `0586ca0f712653baf31fb50c44c32faf551e230a2d24eb3ccb341b8ab56acc89`.
- [442_interactions_20261006_106.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_106.tar.gz.dvc), member `evidence/client_interactions_20261006_ui106/runtime_closure.json`, SHA-256 `361628875c87938bc42ef3a3cb862929f4663964077a31cba23b4e0f45693c82`.

### owned_friend_ignored_chat

UI108 whole ignored_chat02 delivers one short owned same-realm whisper before Ignore, suppresses the middle whisper and delivers another after removal. Stock Ignore changes only the saved Ignore bit while friendship and notes remain original. Exact modern feedback 01a002040800 maps to native 000403; native and modern ignored notices reach the scout, whose stock chat shows Harnessone-Client442Lab is ignoring you. Three primary samples retain the previous token and General stays6->6. All before/ignored/after outcomes pass. Normal scout parking passes19 checks; primary normal logout/reentry restores original offline level0 cache with5 logout,5 entry,3 cache,9 native,12 friend and1 chat checks against10 carried baselines. Code controller, model None.

Remaining limits: Only this owned same-realm friend, short ASCII markers and default Reason0. Other senders/reasons, live GM notices, persistence and limit behavior remain open. UI107 and UI108 ignored_chat01 stay whole failed/excluded. UI10801 refuses Return because the observation contains a shorter prefix despite a complete rendered token; it sends no whisper and changes no Ignore flag. Its original cache is restored separately. Read-only settling later observes the exact token without retyping and the fresh whole trial passes. The original softTargetInteract0 remains unrestored at1 by user choice; scripts remain blocked. Whole-review wording about original state refers to its checked character/social/chat baselines and does not claim CVar restoration.

- [442_interactions_20261006_108.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_108.tar.gz.dvc), member `evidence/client_interactions_20261006_ui108/ignored_chat02/primary/episode.json`, SHA-256 `2dc496357b69926bf344196a010e9e44476e0c760a6f8ba3cb32a1d635eb0baa`.
  Checked cases: `friends.ignored_chat` (owned_ignored_chat_pass).
- [442_interactions_20261006_108.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_108.tar.gz.dvc), member `evidence/client_interactions_20261006_ui108/ignored_chat02/scout/episode.json`, SHA-256 `f4f466ed6ed8d23af26ea1a7a9ed36220b48ae00e872ca2f4a8818b84005d199`.
- [442_interactions_20261006_108.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_108.tar.gz.dvc), member `evidence/client_interactions_20261006_ui108/ignored_chat02/cohort.json`, SHA-256 `c8b3f0b2555a3f83f97f2af1672cec158bb5567149ca3de204a5b51b0c7fe1a2`.
- [442_interactions_20261006_108.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_108.tar.gz.dvc), member `evidence/client_interactions_20261006_ui108/prepared_ignored_chat_review02.json`, SHA-256 `b8d6a6d30a4da0a9d043ba39c392f85a86ba9c2f12d297682918ae9240c57010`.
- [442_interactions_20261006_108.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_108.tar.gz.dvc), member `evidence/client_interactions_20261006_ui108/cache_prepare02/episode.json`, SHA-256 `7c0d4a83ee6a11bb7995e33f992ce1a532e3caf5deb3e24a2245a399be9d23ed`.
- [442_interactions_20261006_108.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_108.tar.gz.dvc), member `evidence/client_interactions_20261006_ui108/cache_finish02/episode.json`, SHA-256 `42fe879d2097b2d68172426c1ac80cfd29bf2118aac40672fefaa4751675fc74`.
- [442_interactions_20261006_108.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_108.tar.gz.dvc), member `evidence/client_interactions_20261006_ui108/whole_ignored_chat_review.json`, SHA-256 `2cdcf882eeb241b2e399adf8e5612c10f897118ecdb93836dc4872dce635471d`.
- [442_interactions_20261006_108.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_108.tar.gz.dvc), member `evidence/client_interactions_20261006_ui108/failed_whisper_guard_review01.json`, SHA-256 `621687256eb960ade3ef57432ede26975b06324427917ec7ed8a2fde37fb9f9f`.
- [442_interactions_20261006_108.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_108.tar.gz.dvc), member `evidence/client_interactions_20261006_ui108/failed_whisper_cleanup_review01.json`, SHA-256 `2978cde6f0b0b6e1502ca370c8d8ad40a2ac6d0311955b7f84d7f6c9e1dc66b2`.
- [442_interactions_20261006_108.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_108.tar.gz.dvc), member `evidence/client_interactions_20261006_ui108/verification.json`, SHA-256 `6661d5fc15c1bc12444b4752500dab9b8c22bbf9baeeb5782943182d86ecbb44`.
- [442_interactions_20261006_108.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_108.tar.gz.dvc), member `evidence/client_interactions_20261006_ui108/runtime_closure.json`, SHA-256 `00e4550298437b2c2176d6d7865a7dbf81f3629d74f26ed402e78e05c43eafc3`.

### owned_imp_target_and_health

UI112 whole pet_target01 passes on retained human Warlock GUID4 level1. One stock exact-name target selects the current owned Imp entry416 number1: native GUID0xf14001a000000005, modern request/public Pet-0-1-0-0-416-0000000005, native request/player target and visible Volrot selection agree. Public and native selected health are254/254, with a full visible health bar. Nine target checks, five health checks and all nine restoration checks pass. Original empty target, resources, saved rows, position and closed panels restore; normal class parking and reviewed Harnesstwo finish pass all five closing checks. Code controller, model None.

Remaining limits: Only exact-name targeting and health when this owned Imp is selected. Pet tab, power, commands, combat, damaged/healed variants, other classes/levels and persistence remain open. Imp name queries and pet visibility were repaired in UI111; this does not qualify those other operations. No spell/aura grant, level change, native build, bridge restart or new client. Both existing windows remain on HDMI-1. One initial test expected initial140 rather than the later sparse254 and fails; corrected focused selection passes66. Scripts remain blocked; original softTargetInteract0 remains unrestored at1.

- [442_interactions_20261006_112.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_112.tar.gz.dvc), member `evidence/client_interactions_20261006_ui112/pet_target01/episode.json`, SHA-256 `9fde6acf018eeaccf8f96742763b9260035e2b7c382cbae92e62088c9db7c67c`.
  Checked cases: `pets.pet_target` (native_owned_pet_target_pass), `pets.pet_health` (native_owned_pet_health_pass).
- [442_interactions_20261006_112.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_112.tar.gz.dvc), member `evidence/client_interactions_20261006_ui112/class_prepare01/episode.json`, SHA-256 `abb45d48668294ffd27287b998d7194f11e2d24b5528d6299886a37eeed4440a`.
- [442_interactions_20261006_112.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_112.tar.gz.dvc), member `evidence/client_interactions_20261006_ui112/class_enter01/episode.json`, SHA-256 `84f4d91a7be85e089169b2692d050130ef419f9ff7614cd9a5c959660b43d407`.
- [442_interactions_20261006_112.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_112.tar.gz.dvc), member `evidence/client_interactions_20261006_ui112/pet_entry_recon01/episode.json`, SHA-256 `eb9463694a255803d52e9c9013e537cea428202973b9c0d8d75bea1e6ca6e017`.
- [442_interactions_20261006_112.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_112.tar.gz.dvc), member `evidence/client_interactions_20261006_ui112/class_park01/episode.json`, SHA-256 `5312238604f94a0de298d23f7f848dd2aba3ddac5b0ae0b24c2c9f73647d83d9`.
- [442_interactions_20261006_112.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_112.tar.gz.dvc), member `evidence/client_interactions_20261006_ui112/class_original_finish01/episode.json`, SHA-256 `38d946a1ebd303d2076d50edffb1dc8f0f77108391e06773b3a74abcd2a229f4`.
- [442_interactions_20261006_112.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_112.tar.gz.dvc), member `evidence/client_interactions_20261006_ui112/whole_pet_target_review.json`, SHA-256 `fff5b733d78ec481e4f6472e280ed9e4fec214fbccbffc3984066f17f4cdb6ee`.
- [442_interactions_20261006_112.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_112.tar.gz.dvc), member `evidence/client_interactions_20261006_ui112/runtime_closure.json`, SHA-256 `5d6cd80529bf515a5b58b01e8d6e2e5671fcfc560da8418c7bd0fce53ccb6445`.
- [442_interactions_20261006_112.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_112.tar.gz.dvc), member `evidence/client_interactions_20261006_ui112/verification.json`, SHA-256 `07c0c84b15dc7750621c39ae04724a87dace865a5edff0896bcbe50d594d2dde`.
- [442_interactions_20261006_112.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_112.tar.gz.dvc), member `evidence/client_interactions_20261006_ui112/control_prerequisite.json`, SHA-256 `e2a6a38c81d1c25e8f86952302d7aa69c74970717c9f2a01212eb4403bc636cb`.

### owned_imp_power

UI113 fresh whole pet_power02 passes on retained human Warlock GUID4 level1. Native and public selected owned Imp mana agree at155/155, both power types identify mana0, and reviewed target frame shows a full blue mana bar. Native owner/player-summon/selection and public GUID identify current pet0xf14001a000000006. All9 power and9 restoration checks pass; normal class logout and original Harnesstwo finish pass all5 closing checks. Code controller, model None.

Remaining limits: Only stationary selected owned Imp mana reading. Repeated target/health checks add no coverage. Other mana levels, pet tab, commands, training and class variants remain open. Whole pet_power01 is failed/excluded because a diagnostic page omits core target fields; all9 cleanup checks pass. A separate fresh core observation repairs the checker. Final focused98 tests and4 metadata checks pass; initial ledger regression fails1/passes3 and is retained. Primary found already offline is normally reentered with6+9 checks. No C++ changes, builds, additional clients or server/bridge restart. Both clients remain on HDMI-1. Scripts stay blocked; original softTargetInteract0 remains unrestored at1.

- [442_interactions_20261006_113.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_113.tar.gz.dvc), member `evidence/client_interactions_20261006_ui113/class_prepare01/episode.json`, SHA-256 `ae604d34b7e23a851aa8c31cab2f1edf56570ebc6183f3f075d677f48d7825a8`.
- [442_interactions_20261006_113.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_113.tar.gz.dvc), member `evidence/client_interactions_20261006_ui113/class_enter01/episode.json`, SHA-256 `18cf7a4aca18b5266de734c19f3cce06112409f52c0856bebbc75d75fd1277cf`.
- [442_interactions_20261006_113.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_113.tar.gz.dvc), member `evidence/client_interactions_20261006_ui113/pet_entry_recon01/episode.json`, SHA-256 `754c03ef99056bc8a66ce300600574c0c8c78e7a805a1e55bdbf24a3042077c2`.
- [442_interactions_20261006_113.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_113.tar.gz.dvc), member `evidence/client_interactions_20261006_ui113/pet_power02/episode.json`, SHA-256 `168c3d524fd5887c691ebe1c03f0c1c3d58b7ef8473fcec916f3eb0c71f79408`.
  Checked cases: `pets.pet_power` (native_owned_pet_power_pass).
- [442_interactions_20261006_113.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_113.tar.gz.dvc), member `evidence/client_interactions_20261006_ui113/class_park01/episode.json`, SHA-256 `92001eee079192d520ab370a07497cc1cd022dcbf120e28459a67d8392766d72`.
- [442_interactions_20261006_113.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_113.tar.gz.dvc), member `evidence/client_interactions_20261006_ui113/class_original_finish01/episode.json`, SHA-256 `6b056c3a83866969119d9268eec5c629791ebc102e1c81dae4f113bf2d5e3c7e`.
- [442_interactions_20261006_113.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_113.tar.gz.dvc), member `evidence/client_interactions_20261006_ui113/whole_pet_power_review.json`, SHA-256 `db35b6668260a917121bf8b9f8f594e2242c34bb4a3f7246325b66684c51d4fe`.
- [442_interactions_20261006_113.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_113.tar.gz.dvc), member `evidence/client_interactions_20261006_ui113/failed_pet_power_review01.json`, SHA-256 `b4da1639c2bf3d8af5ca39d4f85589abf10428cc99533efd6d9f08a85d881abb`.
- [442_interactions_20261006_113.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_113.tar.gz.dvc), member `evidence/client_interactions_20261006_ui113/runtime_closure.json`, SHA-256 `2a49ceb2375f7e1f14455e390c07b6b9671325a903e071a8714f203411d5bfb5`.
- [442_interactions_20261006_113.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_113.tar.gz.dvc), member `evidence/client_interactions_20261006_ui113/verification.json`, SHA-256 `581ad6aca2636de672dfcd15b2da9964554ea1fec549a4f123ff987caedd6a63`.

### owned_imp_persistence

UI113 pet_persist01 verifies the same saved Imp across ordinary logout and reviewed normal reentry. Full offline saved rows bind pet id1, entry416, owner4 and nameVolrot through the closed restoration chain. Native runtime GUID changes0xf14001a000000006 to0xf14001a000000007; current native ownership/player-summon pointer and public Pet-0-1-0-0-416-0000000007 agree. Volrot is rendered beside Harnesslock after reentry. All7 outcome and9 preservation checks pass; final original Harnesstwo finish passes all5 checks. Code controller, model None.

Remaining limits: Only one owned Imp identity/name across normal logout/reentry. Command/autocast/talent state, full client restart, combat, other pets/classes/levels and training remain open. No level/spell/aura grant, C++ change, build, client launch or native/bridge restart. The primary is recovered from a preexisting logout with6+9 checks, adding no coverage. Scripts stay blocked; original softTargetInteract0 remains unrestored at1.

- [442_interactions_20261006_113.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_113.tar.gz.dvc), member `evidence/client_interactions_20261006_ui113/pet_power02/episode.json`, SHA-256 `168c3d524fd5887c691ebe1c03f0c1c3d58b7ef8473fcec916f3eb0c71f79408`.
- [442_interactions_20261006_113.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_113.tar.gz.dvc), member `evidence/client_interactions_20261006_ui113/class_park01/episode.json`, SHA-256 `92001eee079192d520ab370a07497cc1cd022dcbf120e28459a67d8392766d72`.
- [442_interactions_20261006_113.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_113.tar.gz.dvc), member `evidence/client_interactions_20261006_ui113/class_original_finish01/episode.json`, SHA-256 `6b056c3a83866969119d9268eec5c629791ebc102e1c81dae4f113bf2d5e3c7e`.
- [442_interactions_20261006_113.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_113.tar.gz.dvc), member `evidence/client_interactions_20261006_ui113/class_prepare02/episode.json`, SHA-256 `da648832931057817f121ba5e4cd24ca287e0da75f152fafd195acd62743be08`.
- [442_interactions_20261006_113.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_113.tar.gz.dvc), member `evidence/client_interactions_20261006_ui113/class_enter02/episode.json`, SHA-256 `2c5cbbfe12559b28a5dac0f4868ebe81f77f803a17003d3d2bcf29f9433767e1`.
- [442_interactions_20261006_113.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_113.tar.gz.dvc), member `evidence/client_interactions_20261006_ui113/pet_entry_recon02/episode.json`, SHA-256 `8bfdb1c0562001e9159685e4c3768eab1d760716ac55b4e9de0d71fbd2ec460d`.
- [442_interactions_20261006_113.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_113.tar.gz.dvc), member `evidence/client_interactions_20261006_ui113/pet_persist01/episode.json`, SHA-256 `44f2c8a9012fd24e9df982d3f818dbe53aeae9f37c60786d9129ac6fe601dfa3`.
  Checked cases: `pets.persist` (native_owned_pet_persistence_pass).
- [442_interactions_20261006_113.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_113.tar.gz.dvc), member `evidence/client_interactions_20261006_ui113/class_park02/episode.json`, SHA-256 `32a4609968153467fc584f5a0546b5be96bed8260a0ae87ab19c0649346001f6`.
- [442_interactions_20261006_113.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_113.tar.gz.dvc), member `evidence/client_interactions_20261006_ui113/class_original_finish02/episode.json`, SHA-256 `4d4a4b95b4e6945688717df3705bd78fb9860e532c5909e44a62a28a852994e5`.
- [442_interactions_20261006_113.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_113.tar.gz.dvc), member `evidence/client_interactions_20261006_ui113/whole_pet_persistence_review.json`, SHA-256 `0b8096f861fb0970499e53be27b09e9fca8da4d677f1bbb33c11ebbc291a09ce`.
- [442_interactions_20261006_113.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_113.tar.gz.dvc), member `evidence/client_interactions_20261006_ui113/runtime_closure.json`, SHA-256 `2a49ceb2375f7e1f14455e390c07b6b9671325a903e071a8714f203411d5bfb5`.
- [442_interactions_20261006_113.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_113.tar.gz.dvc), member `evidence/client_interactions_20261006_ui113/verification.json`, SHA-256 `581ad6aca2636de672dfcd15b2da9964554ea1fec549a4f123ff987caedd6a63`.

### trained_imp_pet_spellbook_tab

UI120 pet_tab02 opens the stock Pet tab on normally trained level10 human warlock Harnessctrl/GUID5 with saved Imp2/Yaztog. Five exact native/public catalog checks, seven visible contents checks and ten restoration checks pass. All10 slots and three visible native spells agree; native-hidden91702 is correctly omitted. The whole review includes normal class parking, original scout restoration, nine primary native checks and fourteen final runtime checks. DVC120 remotely verifies all40 JSON receipts and118 attributed images. Code controller, model None.

Remaining limits: Only this normally trained Imp Pet-tab opening and contents variant. No executing commands/spells, Dismiss, actual summon from absence, other class/pet/combat variants or family completion. Failed pet_tab01, dismiss01 and UI119 whole training remain excluded; legitimate80388 purchase/9354 balance/Imp2 are retained. Native server and two clients unchanged on HDMI-1; scripts blocked, original softTargetInteract0 unrestored at1.

- [442_interactions_20261006_120.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_120.tar.gz.dvc), member `evidence/client_interactions_20261006_ui120/class_prepare01/episode.json`, SHA-256 `e3abf0f63180645d5b24bb6af59245f3b91e6f6eb6e1c23fc03fec56ed3e44ca`.
- [442_interactions_20261006_120.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_120.tar.gz.dvc), member `evidence/client_interactions_20261006_ui120/class_enter01/episode.json`, SHA-256 `188e38a4436e6c254ed1caf52e4ad2c0516d9f2d588e9bb660c509d1a0f6c98e`.
- [442_interactions_20261006_120.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_120.tar.gz.dvc), member `evidence/client_interactions_20261006_ui120/pet_entry_recon01/episode.json`, SHA-256 `e40b2857c46c8e28f931fc8f79fea04188d598bb8fbeccdeec8990fb9fadd4d2`.
- [442_interactions_20261006_120.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_120.tar.gz.dvc), member `evidence/client_interactions_20261006_ui120/pet_tab02/episode.json`, SHA-256 `27f325078a85de4cf342511a040cfc3197a6f67980df70ef93050dfdca1cba2d`.
  Checked cases: `spellbook.pet_tab` (pet_tab_selected_pass).
- [442_interactions_20261006_120.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_120.tar.gz.dvc), member `evidence/client_interactions_20261006_ui120/class_park01/episode.json`, SHA-256 `20d4477e8429c78062582f104383626e20b25870c9489c356bc78cee2e6b7717`.
- [442_interactions_20261006_120.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_120.tar.gz.dvc), member `evidence/client_interactions_20261006_ui120/origin_finish01/episode.json`, SHA-256 `56e648c8000f8ead5cd33c4865c26b01ccd4d944ed6005aec40afce326d64904`.
- [442_interactions_20261006_120.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_120.tar.gz.dvc), member `evidence/client_interactions_20261006_ui120/primary_native_close01/episode.json`, SHA-256 `0d179166e8154fab8aec17dcaa9a980dde8c4291706953f7a2b7fd42badf2fde`.
- [442_interactions_20261006_120.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_120.tar.gz.dvc), member `evidence/client_interactions_20261006_ui120/pet_tab_whole_review01.json`, SHA-256 `0d4d2a07dde2873614e708d0a3137af80a619a9e8ed3a8fa32303d74fb0a129a`.
- [442_interactions_20261006_120.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_120.tar.gz.dvc), member `evidence/client_interactions_20261006_ui120/verification.json`, SHA-256 `e009cc12c74f2d0d6305dda2b43d8b8b8c8bdd8aa51d4b109d27b5451d76151e`.

### owned_trained_imp_dismiss

UI121 dismiss02 executes one stock Dismiss on normally trained level10 human warlock Harnessctrl/GUID5 with saved Imp2/Yaztog. Nine exact native/public Dismiss checks, explicit passive public pet absence and all13 restoration checks pass. Actual submitted GUID17 produces one native command3 with no ABANDON opcode; normal recovery creates GUID18 with retained Imp2 identity. Whole review includes class parking, original scout5, primary9 plus idle reentry6+9 and final runtime14/protected6. DVC121 remotely verifies52 JSON receipts and164 attributed images. Code controller, model None.

Remaining limits: Only this normally trained summoned Imp Dismiss variant. Normal Summon Imp is recovery only; no pets.summon, other class/pet/command/combat or family completion. Failed dismiss01 stale observation and no-input primary idle preflight remain excluded, as do UI114/115/120 Dismiss and UI119 whole training. Legitimate80388 purchase/9354 balance/Imp2 retained; original level1 fixture protected. Native server/two clients unchanged on HDMI-1; scripts blocked, original softTargetInteract0 unrestored at1.

- [442_interactions_20261006_121.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_121.tar.gz.dvc), member `evidence/client_interactions_20261006_ui121/class_prepare02/episode.json`, SHA-256 `f6442f5ed6011b6a551bd2523d58fe377eebbea35ce95beacc0f79050f07411d`.
- [442_interactions_20261006_121.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_121.tar.gz.dvc), member `evidence/client_interactions_20261006_ui121/class_enter02/episode.json`, SHA-256 `f846cd56a0d37658ec58ccf5ecdb57a4da5f0fa6d83802da82c4f7601d5805cc`.
- [442_interactions_20261006_121.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_121.tar.gz.dvc), member `evidence/client_interactions_20261006_ui121/pet_entry_recon02/episode.json`, SHA-256 `f7e598e6837df4cb6cace93ceada0e64f215ac01ef7ac951877a92c32585a804`.
- [442_interactions_20261006_121.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_121.tar.gz.dvc), member `evidence/client_interactions_20261006_ui121/pet_menu02/episode.json`, SHA-256 `8cd5f58ad5fcfc2da6b01a7a54176f6d6c3930d37eaa145b4186125f8c34e13a`.
- [442_interactions_20261006_121.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_121.tar.gz.dvc), member `evidence/client_interactions_20261006_ui121/dismiss02/episode.json`, SHA-256 `daca1ba2ad3cbb44d6f222449f9de9023d0f19f59378dcba6d96079168016064`.
  Checked cases: `pets.dismiss` (native_owned_pet_dismiss_pass).
- [442_interactions_20261006_121.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_121.tar.gz.dvc), member `evidence/client_interactions_20261006_ui121/class_park02/episode.json`, SHA-256 `3904307321a561baea644c6f9c4b9c45c2d1adc5510aa2136a6a45efcc0a52e2`.
- [442_interactions_20261006_121.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_121.tar.gz.dvc), member `evidence/client_interactions_20261006_ui121/origin_finish02/episode.json`, SHA-256 `45ffa77d6c74e92aa442ed7eff30f2178e379b6f99fd289f4fd9d6390ae9c82b`.
- [442_interactions_20261006_121.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_121.tar.gz.dvc), member `evidence/client_interactions_20261006_ui121/primary_native_close01/episode.json`, SHA-256 `a7db183c36d66e543dcd038418a9b7307ac263bd1aa60724eb3395d5d5ad81b9`.
- [442_interactions_20261006_121.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_121.tar.gz.dvc), member `evidence/client_interactions_20261006_ui121/primary_idle_reentry01/episode.json`, SHA-256 `ca34c4ca8d7939de58083029044773dfa3a539a01f4b89bc64906897d3f009aa`.
- [442_interactions_20261006_121.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_121.tar.gz.dvc), member `evidence/client_interactions_20261006_ui121/dismiss_whole_review01.json`, SHA-256 `ebf5c4be3f3453af6c7a6988998cbe1325a7353cf6679309a113cd5a641b6801`.
- [442_interactions_20261006_121.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_121.tar.gz.dvc), member `evidence/client_interactions_20261006_ui121/verification.json`, SHA-256 `456f3ea4c6d585a39d1c65039f6ea0944c2cd6e6372ecfc7b7e5f78ce35ef43c`.

### owned_trained_imp_summon_from_absence

UI122 summon01 casts Summon Imp once from explicit native/public absence on normally trained level10 human warlock Harnessctrl/GUID5 with retained saved Imp2/Yaztog. Nine summon outcome,13 restoration and six protected-fixture checks pass. One modern/native688 cast has one matching native cast-counter completion and new owned runtime pet GUID20 after removed GUID19. The passive client probe agrees with exact GUID/name. Four samples settle without replay; no extra recovery cast. Whole closure includes original scout5, primary9 and runtime14/protected6. DVC122 remotely verifies19 JSON receipts and78 attributed images. Code controller, model None.

Remaining limits: Only this ordinary Summon Imp from genuine absence. Stock Dismiss is preparation only. No flyout button, other summon/class/pet/command/combat or family completion. The earlier UI110 probes and UI121 cleanup casts remain excluded as summon qualification; earlier whole failures remain recorded. Legitimate80388 purchase/9354 balance/Imp2 and original fixtures retained. No C++ build or native restart; same two clients on HDMI-1, scripts blocked, original softTargetInteract0 unrestored at1.

- [442_interactions_20261006_122.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_122.tar.gz.dvc), member `evidence/client_interactions_20261006_ui122/class_prepare01/episode.json`, SHA-256 `265029ef2387bf878c5276b7d25de0b3d13246f6b25bcb19e0c12a2d629cea79`.
- [442_interactions_20261006_122.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_122.tar.gz.dvc), member `evidence/client_interactions_20261006_ui122/class_enter01/episode.json`, SHA-256 `1138b96dc97b72cb89a09806bcf81e530479a1c4477c872853366d38404358f1`.
- [442_interactions_20261006_122.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_122.tar.gz.dvc), member `evidence/client_interactions_20261006_ui122/pet_entry_recon01/episode.json`, SHA-256 `51f909088592fe4fbd50418d62b296abbfc79071de8e6969840e4eca894c102c`.
- [442_interactions_20261006_122.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_122.tar.gz.dvc), member `evidence/client_interactions_20261006_ui122/pet_menu01/episode.json`, SHA-256 `8a624ca36eedf74e6fb23e8b0c69dee3f16b36297bde0a799bbb54cafc65668b`.
- [442_interactions_20261006_122.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_122.tar.gz.dvc), member `evidence/client_interactions_20261006_ui122/summon01/episode.json`, SHA-256 `631bea00cdda9bc10ffacc85aa69cfffd8459ca640e3451a4adea4782d46049d`.
  Checked cases: `pets.summon` (native_owned_pet_summon_pass).
- [442_interactions_20261006_122.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_122.tar.gz.dvc), member `evidence/client_interactions_20261006_ui122/class_park01/episode.json`, SHA-256 `36d08576748defa44b37731f993358200eb9fa797e4025f5602a46d7c3b433cd`.
- [442_interactions_20261006_122.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_122.tar.gz.dvc), member `evidence/client_interactions_20261006_ui122/origin_finish01/episode.json`, SHA-256 `74906d7e30ada5a858bd213075007eb8bceeacdab399a536198b74dfd335ac37`.
- [442_interactions_20261006_122.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_122.tar.gz.dvc), member `evidence/client_interactions_20261006_ui122/primary_native_close01/episode.json`, SHA-256 `c2a4e080a72745dedc639a5884abf251b5342c98660145ee7fd8c9004670c847`.
- [442_interactions_20261006_122.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_122.tar.gz.dvc), member `evidence/client_interactions_20261006_ui122/summon_whole_review01.json`, SHA-256 `ab6f3b2d9d258d4376c795503ecb3ef2decdd02a5b6fdefedb8aae4650f67e21`.
- [442_interactions_20261006_122.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_122.tar.gz.dvc), member `evidence/client_interactions_20261006_ui122/verification.json`, SHA-256 `33406e91e13e080794cc2e94b51761872dc88316957f75b04c5e50102754760b`.

### owned_trained_imp_stay_follow

One trained owned level10 warlock and retained Imp2 on map0 open ground. Stock Stay and Follow preserve the submitted native-owned pet GUID and catalog authority. Stay clears public Follow selection and keeps the idle pet behind while the owner moves14.05 meters through an observed binding; public ranges2/3 change to far and no native following path occurs. Follow selects its public indicator, delivers owned native splines to the client and returns the pet into both public ranges, with a native endpoint3.01 meters from the stationary owner. The original position, resources, saved rows, money9354, trained80388, retained Imp2, pose/bar and protected actors restore.

Remaining limits: Pet coordinates and UnitDistanceSquared are unavailable; range, idle speed, accepted owner XY, owned native paths and reviewed frames remain separate evidence. Only this ordinary ground fixture is qualified. Other pets/classes, MoveTo, attack, react modes, auto-cast, combat and the complete pet family remain open. Thirty episodes close27 successful3 failed; all failed prerequisites and earlier test/build/metadata adapter failures remain preserved and excluded. Remote review verifies50 JSON/137 images;174 frames320724978 bytes and exact340375171-byte archive/cache copies are offloaded. Native and both existing client lifetimes remain unchanged through bridge-only deployment; two clients on HDMI-1. Scripts blocked; original softTargetInteract0 remains unrestored at1.

- [442_interactions_20261006_125.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_125.tar.gz.dvc), member `evidence/client_interactions_20261006_ui125/class_prepare01/episode.json`, SHA-256 `d4590f9988f9975edd82a3729c5a3bb962035022f38888b0c8337a6c60d20216`.
- [442_interactions_20261006_125.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_125.tar.gz.dvc), member `evidence/client_interactions_20261006_ui125/class_enter01/episode.json`, SHA-256 `c5a26c62b39a89e4fc1cdfb54443c93994f6356b77571a051b8967f79f80c0af`.
- [442_interactions_20261006_125.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_125.tar.gz.dvc), member `evidence/client_interactions_20261006_ui125/pet_command_probe02/episode.json`, SHA-256 `42d7c86fb060a47f4dec08ac2a42b18307d1a187ee109f3ef85048b4e39de771`.
- [442_interactions_20261006_125.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_125.tar.gz.dvc), member `evidence/client_interactions_20261006_ui125/pet_ground_stage01/episode.json`, SHA-256 `fcd722bf7dcc4f607c1be012d5f1794e575e01268fbdd75376ca122e52e5068d`.
- [442_interactions_20261006_125.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_125.tar.gz.dvc), member `evidence/client_interactions_20261006_ui125/pet_commands01/episode.json`, SHA-256 `73093e5e21d4694df9185e4377518333f73be1b2dd86af22b310ac6595b5e62b`.
  Checked cases: `pets.command_stay` (owned_pet_command_pass), `pets.command_follow` (owned_pet_command_pass).
- [442_interactions_20261006_125.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_125.tar.gz.dvc), member `evidence/client_interactions_20261006_ui125/class_park01/episode.json`, SHA-256 `49ab46227f85495bd5969bb398addf16acf6b668acb0965216729d8b94e2b19e`.
- [442_interactions_20261006_125.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_125.tar.gz.dvc), member `evidence/client_interactions_20261006_ui125/origin_finish01/episode.json`, SHA-256 `cac907dfc658b32c2b69da7c64e55536e88dc9b627d8375382518ac05f19963b`.
- [442_interactions_20261006_125.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_125.tar.gz.dvc), member `evidence/client_interactions_20261006_ui125/primary_native_close01/episode.json`, SHA-256 `ce6f965afff3e7dbb0d3cf6338918a9265a1158bcf2c4f60684d3daae261f30d`.
- [442_interactions_20261006_125.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_125.tar.gz.dvc), member `evidence/client_interactions_20261006_ui125/pet_commands_whole_review01.json`, SHA-256 `99c6c91dd975d34207db2cd81168c1c1376b50d667382b3a59159d7acb8f2ad4`.
- [442_interactions_20261006_125.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_125.tar.gz.dvc), member `evidence/client_interactions_20261006_ui125/verification.json`, SHA-256 `16ea4e6db6d7f86318889228fa9f1b5b44aaded6156f6dad8a25b4ee30a5bd0a`.

### owned_trained_imp_passive_assist

One idle trained level10 warlock and retained Imp2. Stock Passive and observed stock Assist button8 each send one exact owned native reaction command under released native catalog and owner/summon authority. Ordinary reload delivers real native pet-info requests and catalogs with Passive0 and Assist3; native persisted Reactstate and public selection agree. Each mode passes15 checks; whole original resources, saved rows, position, vitals, money9354, trained80388, pose/AFK, pet/bar and protected actors restore through17 checks. Original scout5, primary9 and runtime14 closure checks pass.

Remaining limits: Mode control/readback only for this idle owned Imp. Combat reaction behavior, Defensive, aggressive, attack, autocast, other pets/classes and complete pet family remain open. UI126 unsupported petassist whole trial stays failed and excluded. Two expected old-codec prebuild failures retained; final175 focused and2540 foundation pass, later48 Python readback/geometry tests pass. Twenty episodes close successfully. Remote DVC127 review verifies39 JSON/112 referenced images;135 frames217378971 bytes and exact239212141-byte archive/cache copies offloaded. Native and both client lifetimes preserved through bridge-only deployment; two clients on HDMI-1. Scripts blocked; original softTargetInteract0 remains unrestored at1. Native pet savetime advances on real save/logout; every other retained field is exact.

- [442_interactions_20261006_127.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_127.tar.gz.dvc), member `evidence/client_interactions_20261006_ui127/class_prepare01/episode.json`, SHA-256 `0c09a2209b6d29feffe45956d5822f0ded1d8b5fcdce9aed248df9459e108650`.
- [442_interactions_20261006_127.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_127.tar.gz.dvc), member `evidence/client_interactions_20261006_ui127/class_enter01/episode.json`, SHA-256 `fc9d52a0d2f12d89d2e19ee2f5318244187d5962c0277d7f1378f0a276aaefd8`.
- [442_interactions_20261006_127.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_127.tar.gz.dvc), member `evidence/client_interactions_20261006_ui127/pet_command_probe01/episode.json`, SHA-256 `08eca6c9856a741318f1e4deb66730994a2dbf0fd30558b44b313f932823cd06`.
- [442_interactions_20261006_127.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_127.tar.gz.dvc), member `evidence/client_interactions_20261006_ui127/react_modes01/episode.json`, SHA-256 `b008e732ff0825ca76ca58ea02d72055ebba40e4b3ef83158eb4f3040c8b2618`.
  Checked cases: `pets.passive` (owned_native_react_mode_pass), `pets.assist` (owned_native_react_mode_pass).
- [442_interactions_20261006_127.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_127.tar.gz.dvc), member `evidence/client_interactions_20261006_ui127/class_park01/episode.json`, SHA-256 `df391a64eb8109ec687e05ecd25e0ad7a789e22b7c1d4aecd7d58390178352dd`.
- [442_interactions_20261006_127.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_127.tar.gz.dvc), member `evidence/client_interactions_20261006_ui127/origin_finish01/episode.json`, SHA-256 `59901397cd882a9636263e30bf00cb8bf2a7bcea4e90dc1eef53ca67405a9ca0`.
- [442_interactions_20261006_127.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_127.tar.gz.dvc), member `evidence/client_interactions_20261006_ui127/primary_native_close01/episode.json`, SHA-256 `3666c0164c23935d1c27f4ef06e2d040f11d00a968dd11af9f622c92e6b91cab`.
- [442_interactions_20261006_127.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_127.tar.gz.dvc), member `evidence/client_interactions_20261006_ui127/react_modes_whole_review01.json`, SHA-256 `80d22cd5941666d8b0306af7cedbb6d73cd7debc4893929881d8ff5397fe72c1`.
- [442_interactions_20261006_127.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_127.tar.gz.dvc), member `evidence/client_interactions_20261006_ui127/verification.json`, SHA-256 `07ad78847ed98f2523f501389668a2e532b370cef392a776004cf1e50eec80de`.

### owned_trained_imp_defensive

One idle trained level10 warlock and retained Imp2. Observed stock Defensive button9 sends one exact owned native reaction command under released native catalog and owner/summon authority. Ordinary reload delivers a real native pet-info request and catalog with mode1; persisted Reactstate1 and public selected Defensive agree. All15 mode checks pass. Supported Assist3 restoration passes15 checks and the whole original resources, saved rows, position, vitals, money9354, trained80388, pose/AFK, owned pet/bar and protected actors restore through17 checks. Original scout5, primary9 and runtime14 closure checks pass.

Remaining limits: Mode control/readback only for this idle owned Imp. Combat reaction behavior, autocast, aggressive, attack, other pets/classes and complete pet family remain open. Assist restoration is cleanup, already-qualified operations are not counted again. Expected old-codec positive failure and initial focused/world-auth failures remain preserved; the latter are an old Follow rejection vector corrected to unsupported Aggressive. Final259 focused and2622 world/auth tests pass. All19 episodes close successfully. DVC129 remote review verifies33 JSON/99 images;120 frames196885381 bytes and exact219066653-byte archive/cache copies offloaded. Native and both client lifetimes preserved through bridge-only deployment; two clients on HDMI-1. Scripts blocked; original softTargetInteract0 unrestored at1. Only real native pet savetime advances; all other retained fields are exact.

- [442_interactions_20261006_129.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_129.tar.gz.dvc), member `evidence/client_interactions_20261006_ui129/class_prepare01/episode.json`, SHA-256 `de227a62e1ad04ae9576b1f6071add20cbda93b203aed250887a7fa90683cf82`.
- [442_interactions_20261006_129.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_129.tar.gz.dvc), member `evidence/client_interactions_20261006_ui129/class_enter01/episode.json`, SHA-256 `df93c4098b8bfd60961d249043eccdfdcc6ed1e85eee6941f885000b898ad741`.
- [442_interactions_20261006_129.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_129.tar.gz.dvc), member `evidence/client_interactions_20261006_ui129/defensive_mode01/episode.json`, SHA-256 `6c8408930d5c96af8945a4af485453b9a7c63d2d5b582db4f1a036eb175a9994`.
  Checked cases: `pets.defensive` (owned_native_react_mode_pass).
- [442_interactions_20261006_129.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_129.tar.gz.dvc), member `evidence/client_interactions_20261006_ui129/class_park01/episode.json`, SHA-256 `e7e93545e723e0c879e0cea306f9e6c9e2b8dc8843ea82f18efe063dcd9a8578`.
- [442_interactions_20261006_129.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_129.tar.gz.dvc), member `evidence/client_interactions_20261006_ui129/origin_finish01/episode.json`, SHA-256 `93312fd4d32e6ad673f59305816d9be4d924c16f248803239b1eb68ffe784e71`.
- [442_interactions_20261006_129.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_129.tar.gz.dvc), member `evidence/client_interactions_20261006_ui129/primary_native_close01/episode.json`, SHA-256 `1e93ec575e214bf12e2098d27416df7e4f10b5a5aef318d02350df6d18df68b8`.
- [442_interactions_20261006_129.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_129.tar.gz.dvc), member `evidence/client_interactions_20261006_ui129/defensive_whole_review01.json`, SHA-256 `386d2804c6f08c16d1f7fb06427e04ce7579d9400a5bd049a3037bbad6952bdf`.
- [442_interactions_20261006_129.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_129.tar.gz.dvc), member `evidence/client_interactions_20261006_ui129/verification.json`, SHA-256 `38717ff97c5c40ab1711eb08991fef221a19072ae1c8b61247a26129322ad71f`.

### owned_trained_imp_autocast

One idle trained level10 warlock and retained Imp2. Observed stock Firebolt3110 and Blood Pact6307 each switch off/on once. All16 checks per switch pass: one exact owned native command under released native catalog and owner/summon plus learned spell/bar authority, ordinary reload pet-info and actual native catalog with exactly matching delivered modern catalog, native saved flags and public exact bar. Assist15 and whole17 original-state restoration pass. Original scout5, primary9 and runtime14/protected6 closure preserve80388, money9354, Imp2 and native/client lifetimes.

Remaining limits: Idle switch control/readback for this owned Imp only. Combat autocast behavior, other pets/classes, manual spell casting and other pet controls remain open. One subsequent actual24-byte Blood Pact PET_ACTION is diagnostic only, rejected without native mutation; its12 checks and whole17 restoration pass. No existing operation is counted again. Expected old-codec4 failures/31 deselected retained; final99 focused/2690 world-auth and later94 readback/13 restoration guards pass.20 closed episodes all successful. DVC131 remote34 JSON/219 images verified;269 PNG419562270 bytes and exact437193400-byte archive/cache copies offloaded. Native and both clients preserved through bridge-only deployment; HDMI-1. Only native pet savetime advances. Scripts blocked; original softTargetInteract0 remains unrestored at1.

- [442_interactions_20261006_131.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_131.tar.gz.dvc), member `evidence/client_interactions_20261006_ui131/class_prepare01/episode.json`, SHA-256 `6af8041ad29edbdd1df7decc7a08ade9ee5e21acdf0f64daaeee69b35ea8d8c4`.
- [442_interactions_20261006_131.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_131.tar.gz.dvc), member `evidence/client_interactions_20261006_ui131/class_enter01/episode.json`, SHA-256 `e5fad04845c42c318b482a3cf9c8ae9b46837f98ed0617a270e89bba26049b70`.
- [442_interactions_20261006_131.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_131.tar.gz.dvc), member `evidence/client_interactions_20261006_ui131/autocast01/episode.json`, SHA-256 `3797319cf4ecfba7efe748d80c678688aad178c3d0f5c91ef3ce50319c3ae627`.
  Checked cases: `pets.autocast_3110_off` (owned_native_autocast_pass), `pets.autocast_3110_on` (owned_native_autocast_pass), `pets.autocast_6307_off` (owned_native_autocast_pass), `pets.autocast_6307_on` (owned_native_autocast_pass).
- [442_interactions_20261006_131.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_131.tar.gz.dvc), member `evidence/client_interactions_20261006_ui131/class_park01/episode.json`, SHA-256 `2cfe8101aa8b1028206c109d26a2020c25bef505d57ef0384f0dca78836ce27f`.
- [442_interactions_20261006_131.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_131.tar.gz.dvc), member `evidence/client_interactions_20261006_ui131/origin_finish01/episode.json`, SHA-256 `207a865cfd4b50afbd1f407f311b607b7659d5c450ec80cbce2f9463a8aacef4`.
- [442_interactions_20261006_131.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_131.tar.gz.dvc), member `evidence/client_interactions_20261006_ui131/primary_native_close01/episode.json`, SHA-256 `db642ee1a1d6ed77123f67321820379876b103af405854a9f30185fe4db0bd27`.
- [442_interactions_20261006_131.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_131.tar.gz.dvc), member `evidence/client_interactions_20261006_ui131/autocast_whole_review01.json`, SHA-256 `97af779bc0c8601d156372ad3d6d27d7d151260a8fcb1002eaba9dd9a5122575`.
- [442_interactions_20261006_131.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_131.tar.gz.dvc), member `evidence/client_interactions_20261006_ui131/verification.json`, SHA-256 `db4fa10034bdf15ac59744a1af6d7fb038fe8d74c74abe27b21995c3a8e90f0a`.

### owned_trained_imp_blood_pact

One idle trained level10 warlock and original retained Imp2. A fresh observed stock Blood Pact6307 click passes22 checks: one exact owned modern/native cast, one matching owned native completion, current pet-caster native aura, public6307 buff and owner max-health increase. Ordinary captured owner /cancelaura Blood Pact resolves to one exact native current-pet aura cancellation9 and original aura/vitals cleanup10; Assist15 and whole17/protected6 restore all resources, saved rows, position, money9354,80388, pose/AFK and pet/bar. Original scout5, primary9 and runtime14 closure pass. Complete saved pet row matches pre-UI132 state except advancing savetime, with364 health/298 mana and no saved6307 aura. Owner188 health/383 mana restored.

Remaining limits: Idle owned Imp Blood Pact only; other spells, combat, pets/classes and remaining pet controls stay open. Three UI132 failed whole/recovery trials remain excluded; source-bound cleanup does not qualify them or replay their click. UI133 cancellation is diagnostic only. Recovery, cancellation and Assist add no separate operation. Expected old-codec1 failure retained;102 focused/79 cleanup guards/2911 world-auth pass, one-job build.20 closed episodes all successful. DVC13438 JSON/191 current images and one bound historical UI132 image verified;239 PNG371839308 bytes offloaded, exact390639630-byte archive/cache copies offloaded. Scoped DVC status records intentional missing cache and push confirms the remote is current. Initial same-batch reviewer refuses the historical baseline; committed explicit historical attribution passes17 guards, tracked in UI135. Native world and both clients preserve lifetimes through bridge-only deployment; HDMI-1. Scripts blocked; original softTargetInteract0 remains unrestored at1.

- [442_interactions_20261006_134.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_134.tar.gz.dvc), member `evidence/client_interactions_20261006_ui134/class_prepare01/episode.json`, SHA-256 `dd5b3bf4dc6eceb43555ffe918ad4276cdd07a7873e78cd88522a9805c9fb7e1`.
- [442_interactions_20261006_134.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_134.tar.gz.dvc), member `evidence/client_interactions_20261006_ui134/class_enter01/episode.json`, SHA-256 `0750052615e3411cdc3f241d480326e76569a459a0fb190a10bebafb5338f8dc`.
- [442_interactions_20261006_134.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_134.tar.gz.dvc), member `evidence/client_interactions_20261006_ui134/spell_recovery01/episode.json`, SHA-256 `b08cfba6e1acdd717aa72a591d1656ea3a89ae3dc2f3044b222ab41541aa8594`.
- [442_interactions_20261006_134.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_134.tar.gz.dvc), member `evidence/client_interactions_20261006_ui134/spell01/episode.json`, SHA-256 `bb5ef34abf4dbbd9f2bc7cf917dd193051edb702a00380c5a1f0555b92f0bb6e`.
  Checked cases: `pets.spell_cast` (owned_native_pet_spell_pass).
- [442_interactions_20261006_134.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_134.tar.gz.dvc), member `evidence/client_interactions_20261006_ui134/class_park01/episode.json`, SHA-256 `ee5bc5482ab042e53aed2371113bcf9bbbc2723b07cb6a0539e4ed0f4e58d0c6`.
- [442_interactions_20261006_134.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_134.tar.gz.dvc), member `evidence/client_interactions_20261006_ui134/origin_finish01/episode.json`, SHA-256 `1a4f1ffd4efd3e076fa52690b589970cf94bbd08ca2478d2e8a7af772129458e`.
- [442_interactions_20261006_134.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_134.tar.gz.dvc), member `evidence/client_interactions_20261006_ui134/primary_native_close01/episode.json`, SHA-256 `c24e56af468fc6f365222f37bf3ce334de83b13e6e287d23f3cc4eba9efa12a5`.
- [442_interactions_20261006_134.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_134.tar.gz.dvc), member `evidence/client_interactions_20261006_ui134/spell_whole_review01.json`, SHA-256 `c2c602f0da8d386758a8b28601a39efb5f7f32db4b30ec52a5755b6c51b8f554`.
- [442_interactions_20261006_134.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_134.tar.gz.dvc), member `evidence/client_interactions_20261006_ui134/spell_recovery_whole_review01.json`, SHA-256 `eaa83fe16450c7b2adf8aa65aa3994fe2195fc73b96a85ada21b618b7524ebb2`.
- [442_interactions_20261006_134.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_134.tar.gz.dvc), member `evidence/client_interactions_20261006_ui134/verification.json`, SHA-256 `44b6ab95cf9b60e9f47f2cd065d859640067716740351ca69f509833f28a766b`.
- [442_interactions_20261006_134.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_134.tar.gz.dvc), member `evidence/client_interactions_20261006_ui134/build_checks.json`, SHA-256 `cee9977ea4ba295e7c2c2ea0e64864e8b89df0039316a4375c6b2d531182d063`.

### owned_trained_imp_move_to

One idle trained level10 warlock and retained Imp2. Separately reviewed stock Move To reticle and one ordinary ground click submit current owned Imp38 and actual destination.20 native/public checks prove one exact native command4 and supported656ms path moving5.246m to the submitted endpoint, delivered to the client. Ordinary reload yields native command4/Assist3 and public Move To readback9. Images show actual pet displacement and no remaining reticle. Follow7, Assist15, aura/vitals10, whole17/protected6 restore all original resources, saved rows, pose/AFK, position, money9354, purchased80388 and pet/bar. Original scout5, primary9 and runtime14 closure pass; complete saved Imp2 row differs only by savetime.

Remaining limits: One owned Imp and destination only; public pet coordinates are unavailable, so native endpoint, visible movement and public range/speed remain separate. Pet Attack/combat, other pets/classes and remaining services stay open. UI135 failed spell-targeting trials remain excluded. Expected old-codec1 failure retained;177 codec/101 harness focused and3028 world-auth pass, one-job build.20 closed episodes all successful. DVC13636 JSON/126 attributed images verified;158 PNG249038877 bytes plus exact270343955-byte archive/cache copies offloaded. Scoped DVC status records intentional missing cache and push confirms the remote is current. Native world and both existing clients retain lifetimes through bridge-only deployment on HDMI-1. Scripts blocked; original softTargetInteract0 remains unrestored at1.

- [442_interactions_20261006_136.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_136.tar.gz.dvc), member `evidence/client_interactions_20261006_ui136/class_prepare01/episode.json`, SHA-256 `450642c8c4d47dafb4c6d6551cba43c3ce4d2f27fd7e1854e0364d77b8777bd3`.
- [442_interactions_20261006_136.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_136.tar.gz.dvc), member `evidence/client_interactions_20261006_ui136/class_enter01/episode.json`, SHA-256 `6c3d3a62c774be5ddcf2f95695f17cf3765cd16f999a1206fe6d277598b25fdb`.
- [442_interactions_20261006_136.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_136.tar.gz.dvc), member `evidence/client_interactions_20261006_ui136/moveto_begin01/episode.json`, SHA-256 `1e60d5eb3c38441106c2f44aeeec66a3cfba6c4596d405dec1244000d7f04571`.
- [442_interactions_20261006_136.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_136.tar.gz.dvc), member `evidence/client_interactions_20261006_ui136/moveto_begin01/ground_review01.json`, SHA-256 `7c1d301f51b0c9361b0a27d8777d98a32d5f1bd0f37bc2d496fd8bbf6a35fa9e`.
- [442_interactions_20261006_136.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_136.tar.gz.dvc), member `evidence/client_interactions_20261006_ui136/moveto01/episode.json`, SHA-256 `0465b0cba97395a27a9d671e69c9b18512c94e34bd148dba39d781afe3a3920c`.
  Checked cases: `pets.command_move_to` (owned_native_pet_moveto_pass).
- [442_interactions_20261006_136.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_136.tar.gz.dvc), member `evidence/client_interactions_20261006_ui136/moveto_whole_review01.json`, SHA-256 `ade4ea340e122723232caf4af434cf3be9ba832bbf798e8b863d7bd67077e0d5`.
- [442_interactions_20261006_136.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_136.tar.gz.dvc), member `evidence/client_interactions_20261006_ui136/class_park01/episode.json`, SHA-256 `713468149cbadc3a84c78d7329d9dc49c2415eb698c41bec40431e14f67e3769`.
- [442_interactions_20261006_136.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_136.tar.gz.dvc), member `evidence/client_interactions_20261006_ui136/origin_finish01/episode.json`, SHA-256 `4bbca599d4b5e9a07d5a5001b6ee9f3fc55b95894a5b1c7f0f085e180b85800a`.
- [442_interactions_20261006_136.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_136.tar.gz.dvc), member `evidence/client_interactions_20261006_ui136/primary_native_close01/episode.json`, SHA-256 `488fcfae229db3bdf7bf4b7e858aeebccec8590fa8ac495d25d917113af07edd`.
- [442_interactions_20261006_136.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_136.tar.gz.dvc), member `evidence/client_interactions_20261006_ui136/verification.json`, SHA-256 `947376197c21bb1402403862b7a7d45d4c8c78336d75c514206a13e2435c1d40`.
- [442_interactions_20261006_136.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_136.tar.gz.dvc), member `evidence/client_interactions_20261006_ui136/build_checks.json`, SHA-256 `4eded15dbd02c70c630f6a4cb8998f0e294c8f6dbf2cf54294fbc4911de9e99a`.

### owned_trained_imp_attack

One retained level10 Warlock and owned Imp2 attack the reviewed existing passive dummy through one stock Attack click. Fresh Stage04 passes10 scene and4 settled-pose checks; immediate input admission is78.94 seconds after the separately reviewed image. Attack02 passes31 checks including47 independently matched native/client Firebolt Start/completion packets and a public cast ID bound to delivery. Follow7, Assist15, Stop11, aura cancellation9, aura/vitals cleanup10, whole restoration17 and protected-state6 pass. Resources, saved rows, money9354, original ground pose, pet/bar and temporary teleport cleanup restore. Separate class logout recovery and original offline scout selection close the fixture.

Remaining limits: Attack command and Firebolt feedback on this Imp/dummy only. Applied health damage, kills, cadence, other targets, pets/classes and hunter services stay open. Failed Attack01, two chat-opening stages, owner-melee capture, interrupted parking and active-primary closure stay excluded. Source-bound sheath recovery independently restores17+6 checks. Owner melee emits two native6-damage packets and no client hit feedback; dummy health remains unchanged. Later ordinary primary logout is unattributed; Harnessone stays selected offline, with saved user position, money, spells and actions preserved. Native world and both existing clients retain lifetimes. UI139 remote archive full SHA,83 JSON/1628 referenced images and2 actual melee packets verified;1820 PNG3194018109 bytes and exact3153427083-byte archive/cache data offloaded. Earlier expected pre-build failures retained, then3181 world/auth checks pass. Scripts blocked; original softTargetInteract0 remains unrestored at1.

- [442_interactions_20261006_139.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_139.tar.gz.dvc), member `evidence/client_interactions_20261006_ui139/class_prepare01/episode.json`, SHA-256 `7b3b88b8604aa7efefc768340dc95c5a6566fae54c55b5f49174054ae781cd65`.
- [442_interactions_20261006_139.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_139.tar.gz.dvc), member `evidence/client_interactions_20261006_ui139/class_entry01/episode.json`, SHA-256 `2a0fca5bc388ee5fde2b04e1d1f0d1ed6ab6ce8b86f707c9e63131aa47da2ec6`.
- [442_interactions_20261006_139.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_139.tar.gz.dvc), member `evidence/client_interactions_20261006_ui139/scout_observer137_01/deployment.json`, SHA-256 `2a1c93c315be04f9332fcd74d9413fccf738445272900897c08883c99c9aad05`.
- [442_interactions_20261006_139.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_139.tar.gz.dvc), member `evidence/client_interactions_20261006_ui139/attack_stage04/episode.json`, SHA-256 `e3306322d85ab5d703151f0d500ba5a2c9a2b3909e71d76e7819eba68ee22352`.
- [442_interactions_20261006_139.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_139.tar.gz.dvc), member `evidence/client_interactions_20261006_ui139/attack_stage04/review01.json`, SHA-256 `4db4eb1f84406f0638502519d752542406257b36255d79c45271a9dea94718d9`.
- [442_interactions_20261006_139.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_139.tar.gz.dvc), member `evidence/client_interactions_20261006_ui139/attack02/episode.json`, SHA-256 `7e8572fe5b0e214480510eb686d9f1bd1f8569e776edb8aabb8a32955071fe72`.
  Checked cases: `pets.command_attack` (owned_native_pet_attack_pass).
- [442_interactions_20261006_139.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_139.tar.gz.dvc), member `evidence/client_interactions_20261006_ui139/bridge_visual_reviews01.json`, SHA-256 `cd3d9f9dd11dfd6c57f26210e096b54388d067d61bce05c20063a9c7fa087f5e`.
- [442_interactions_20261006_139.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_139.tar.gz.dvc), member `evidence/client_interactions_20261006_ui139/melee_pose_recovery01/episode.json`, SHA-256 `25c5b8f3952c4742c4f26ed03e50ba41f4e1fe55f6b63d4a2a778ba448564f2c`.
- [442_interactions_20261006_139.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_139.tar.gz.dvc), member `evidence/client_interactions_20261006_ui139/class_park_recovery01/episode.json`, SHA-256 `eabcb6c1dd2a2b37d5a2675d871a563f12b5a8d7aad98003db3d1b4ede81b762`.
- [442_interactions_20261006_139.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_139.tar.gz.dvc), member `evidence/client_interactions_20261006_ui139/origin_finish01/episode.json`, SHA-256 `a331443a6832183caf4364cb606412288cb32f763342de176f5c4fcfbc5a9fe5`.
- [442_interactions_20261006_139.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_139.tar.gz.dvc), member `evidence/client_interactions_20261006_ui139/final_visual_reviews01.json`, SHA-256 `6af86b21efa5a13069902af2abca30ddaf4aad37a55ec4f17e9d14ed12f46cf0`.
- [442_interactions_20261006_139.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_139.tar.gz.dvc), member `evidence/client_interactions_20261006_ui139/runtime_closure01.json`, SHA-256 `9bd6d585dabcba4a97f77bf7d0b4029310cc2ef835929b5dd62bd6f7e1899ba6`.
- [442_interactions_20261006_139.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_139.tar.gz.dvc), member `evidence/client_interactions_20261006_ui139/primary_offline_closure01.json`, SHA-256 `08275fb1038c299e9876a06cedae90b1b932a11e298d823b1954060223288b99`.

### owned_owner_melee_stop

One owned level10 Warlock uses ordinary /startattack and /stopattack on the separately reviewed existing passive dummy. Fresh whole melee_feedback02 passes14 hit checks, eight exact native/client physical hit pairs, public owned SWING_DAMAGE and four Stop checks including exactly one modern/native Stop request, delivered server Stop and inactive public autoattack. Separate fresh whole melee_health03 proves a5-damage owner hit and exact first native/public target health loss on one existing neutral Sheep, with delivered Start/Stop and no pet damage. Both trials restore all17 actor and6 protected-state checks. Ordinary class logout and separate stock selection restore original Harnesstwo offline; primary saved user pose and complete persisted state are preserved.

Remaining limits: Only this owner melee Stop fixture is newly counted. Melee Start, autoattack and Imp Attack already have scoped qualifications. Other classes/targets, abilities, cadence, monster combat and full combat compatibility remain open. All six failed UI140 episodes stay excluded, including the earlier health trial whose request-count verifier rejected a server Stop delivered during the chat opener. Final3294 world/auth checks pass. Native world and both existing clients preserve lifetimes on HDMI-1. Scripts stay blocked; original softTargetInteract0 remains unrestored at1. The actual1834636249-byte remote object SHA42d0eeb14aeab8ba552de192836d6c36805dfe1bea23b743e523bb1ec4512043, all89 current JSON/1102 images and18 exact accepted native/client hit packets are verified. A one-bit workspace-copy change is recorded separately; the DVC cache and actual remote object are valid, and exact cache relink restores the workspace without replaying gameplay.

- [442_interactions_20261006_140.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_140.tar.gz.dvc), member `evidence/client_interactions_20261006_ui140/class_prepare01/episode.json`, SHA-256 `5400957e7c15832d83de798b1354a4d31292e6df909ec322afff7f7d99f5658a`.
- [442_interactions_20261006_140.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_140.tar.gz.dvc), member `evidence/client_interactions_20261006_ui140/class_entry01/episode.json`, SHA-256 `f444cff09bd6f8c9eb5672be0f725445ea641b54be630242c561a4ac05e84c6c`.
- [442_interactions_20261006_140.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_140.tar.gz.dvc), member `evidence/client_interactions_20261006_ui140/melee_stage02/episode.json`, SHA-256 `d665565457b1649c8783f0099c421e6a98c85ae9346f4263eebe7c32771fc258`.
- [442_interactions_20261006_140.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_140.tar.gz.dvc), member `evidence/client_interactions_20261006_ui140/melee_stage02/review01.json`, SHA-256 `13d36d2446661c7a0f00fc619c2231912463588e7427831afd6987ac601ddfe8`.
- [442_interactions_20261006_140.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_140.tar.gz.dvc), member `evidence/client_interactions_20261006_ui140/melee_feedback02/episode.json`, SHA-256 `e2c0ca98235eaf8b29dd2de28295ea572555b620b04a9f109fc4e10839356763`.
- [442_interactions_20261006_140.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_140.tar.gz.dvc), member `evidence/client_interactions_20261006_ui140/melee_health_stage06/episode.json`, SHA-256 `edc434fe5d07371f0f8fb5b8fdd50fa8e71ca5a84c16446c9522a3b48147f99d`.
- [442_interactions_20261006_140.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_140.tar.gz.dvc), member `evidence/client_interactions_20261006_ui140/melee_health_stage06/review01.json`, SHA-256 `a2f2f1b7be30d2d08c12aa17f1c3b4323eefd307ef7f9659b25d5204d007400b`.
- [442_interactions_20261006_140.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_140.tar.gz.dvc), member `evidence/client_interactions_20261006_ui140/melee_health03/episode.json`, SHA-256 `858ca9f257e23943c0a810757b0dd1484d6b9a1e043bad2ea1810139e6654e47`.
- [442_interactions_20261006_140.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_140.tar.gz.dvc), member `evidence/client_interactions_20261006_ui140/combat_visual_reviews01.json`, SHA-256 `931022335d98707f150d63b9206751c06c619ecc7d149fd4306479307076af4e`.
- [442_interactions_20261006_140.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_140.tar.gz.dvc), member `evidence/client_interactions_20261006_ui140/class_park01/episode.json`, SHA-256 `4e1dcea6d7587e1b3b363007b4f630ed7263a233f2de0e0991ef34c4ced6678b`.
- [442_interactions_20261006_140.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_140.tar.gz.dvc), member `evidence/client_interactions_20261006_ui140/origin_select01/review01.json`, SHA-256 `5454c064b99f927e4f9a105d065633176f4ecf6f2253e209bc64edcb65431ff3`.
- [442_interactions_20261006_140.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_140.tar.gz.dvc), member `evidence/client_interactions_20261006_ui140/origin_finish01/episode.json`, SHA-256 `555e3510ea72adb6826927b9477824c495f9bedf8b36e3a4c031e55ddba20913`.
- [442_interactions_20261006_140.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_140.tar.gz.dvc), member `evidence/client_interactions_20261006_ui140/primary_closure01/episode.json`, SHA-256 `f20c619d010354f2bb428ed986da33b2ed008c29654956f57ae652e36e4a4e2a`.
- [442_interactions_20261006_140.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_140.tar.gz.dvc), member `evidence/client_interactions_20261006_ui140/runtime_closure01.json`, SHA-256 `6d904183413746feabb2086ef572c1630d9fa692532d567afe21511cfb6714e0`.
- [442_interactions_20261006_140.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_140.tar.gz.dvc), member `evidence/client_interactions_20261006_ui140/build_checks01.json`, SHA-256 `539c52eaf59bf44130c0ed1363fd1427b93ad001ad469622dab768a6d5cff739`.
- [442_interactions_20261006_140.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_140.tar.gz.dvc), member `evidence/client_interactions_20261006_ui140/build_checks02.json`, SHA-256 `8e0e2d0e969ac7dac76cbb2f866c1e68b0cc523670b837485c6594c0a55eb885`.
- [442_interactions_20261006_140.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261006_140.tar.gz.dvc), member `evidence/client_interactions_20261006_ui140/build_checks03.json`, SHA-256 `46190b28478c3ca76597d9aaba49d960437a7ddc7e5e6e1808f17578dee73732`.

### owned_hunter_one_time_rename

Ordinary owned Hunter pet-frame Rename, literal Harnesswolf field, separate stock Accept and Yes confirmation, exact submitted native GUID/name, native database/public name-query agreement and one-time permission removal. The same saved pet/name persists through an ordinary offline-to-native-login epoch; Rename remains absent and Abandon available.18 acceptance/14 persistence/4 menu checks each and13 restoration checks each pass;22 final closure checks preserve all five prior actors, the primary saved user pose and both HDMI-1 client/world lifetimes.

Remaining limits: One synthetic Hunter6/pet4 ASCII name, with no declined names. Other pet names, invalid/reserved/unicode names, decline/cancel variants and other pet services remain open. Paid Control lessons are never repurchased. Initial two-dialog capture, stale-image refusal and mistaken transport-session persistence episodes stay whole failed/excluded. Scripts remain blocked and the accepted original CVar0 remains unrestored at1. Actual remote full compressed SHA and all120 JSON/361 PNG members plus exact private Rename/name replies are verified before offloading; this does not qualify a whole family.

- [442_interactions_20261007_143.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_143.tar.gz.dvc), member `evidence/client_interactions_20261007_ui143/hunter_rename_capture02/episode.json`, SHA-256 `8c6b1c93d8dd04779635cc5838c6230c53dd5818465009a3713593937d8a7d1d`.
- [442_interactions_20261007_143.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_143.tar.gz.dvc), member `evidence/client_interactions_20261007_ui143/hunter_rename_native_authority01.json`, SHA-256 `882d575c3868d6dcb5b2a696d285a896b0df15fd6ceb8d79ff6c7034cffa48d4`.
- [442_interactions_20261007_143.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_143.tar.gz.dvc), member `evidence/client_interactions_20261007_ui143/hunter_rename_deploy01/deployment.json`, SHA-256 `c90bd9d8bdc42da90fe7fc6d9356e2a036b2a03a023557ebc9ceff8a5e6532cc`.
- [442_interactions_20261007_143.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_143.tar.gz.dvc), member `evidence/client_interactions_20261007_ui143/hunter_rename_prepare01/episode.json`, SHA-256 `8ccfaa33ae9aaee57e0058212de1779862077b1c3f5418536994c5e8991839e8`.
- [442_interactions_20261007_143.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_143.tar.gz.dvc), member `evidence/client_interactions_20261007_ui143/hunter_rename_entry01/episode.json`, SHA-256 `6ac9362251b3462e9fa05c116553b370fe2e250a080888285a542898131e01a3`.
- [442_interactions_20261007_143.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_143.tar.gz.dvc), member `evidence/client_interactions_20261007_ui143/hunter_rename_native_confirmation02/episode.json`, SHA-256 `76b69016ab8d8d5502def7c1e1b4a6805746e378066bd516321af37952205b1d`.
- [442_interactions_20261007_143.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_143.tar.gz.dvc), member `evidence/client_interactions_20261007_ui143/hunter_rename_native_confirmation02/review01.json`, SHA-256 `1a2a78f3625c10b96e003e01dbf9625248bee0ae05d246293e26122abaa091b6`.
- [442_interactions_20261007_143.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_143.tar.gz.dvc), member `evidence/client_interactions_20261007_ui143/hunter_rename_accept01/episode.json`, SHA-256 `a765d1348508ad11553f15182b19b630ac4326147a333e3ae0feaf2c0f21164e`.
- [442_interactions_20261007_143.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_143.tar.gz.dvc), member `evidence/client_interactions_20261007_ui143/hunter_name_reentry_prepare01/episode.json`, SHA-256 `405e4452ae19a2127ca8c53c3bf9a5e5cf9bc74f3566fcffa86e098fccafcdae`.
- [442_interactions_20261007_143.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_143.tar.gz.dvc), member `evidence/client_interactions_20261007_ui143/hunter_name_reentry_entry01/episode.json`, SHA-256 `ec59cbe3863cff91e8ec5d6849e65b781db56495eaf77743b63d65e8889ef03b`.
- [442_interactions_20261007_143.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_143.tar.gz.dvc), member `evidence/client_interactions_20261007_ui143/hunter_name_persistence02/episode.json`, SHA-256 `ba74a754d1b4f25c62895ba9c16efe5b923abb7d1aecad2d94680773d6342d9d`.
- [442_interactions_20261007_143.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_143.tar.gz.dvc), member `evidence/client_interactions_20261007_ui143/hunter_name_final_park01/episode.json`, SHA-256 `fd59481cfc22e17bb01ad20ab45a651d70608e6c299ac188c4f66a1cb365dff3`.
- [442_interactions_20261007_143.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_143.tar.gz.dvc), member `evidence/client_interactions_20261007_ui143/hunter_name_final_origin_select01/review01.json`, SHA-256 `8708b8ba54657c4552983ce4e2009f66a8e0cdcd0df961a13fb5de3dd771e67d`.
- [442_interactions_20261007_143.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_143.tar.gz.dvc), member `evidence/client_interactions_20261007_ui143/hunter_name_final_origin_finish01/episode.json`, SHA-256 `520dd30bb4a6c86f1e422353ed8711ac53c18acf3f78802b6f05ddc58505ec58`.
- [442_interactions_20261007_143.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_143.tar.gz.dvc), member `evidence/client_interactions_20261007_ui143/hunter_rename_closed_boundary01.json`, SHA-256 `2b98009088c616c78a4a375c06230893a4dcfab3d12b94376d6164f1b9096170`.

### owned_hunter_native_stable_open

Ordinary owned Hunter6 Erma gossip service opens the stock stable panel with retained Harnesswolf pet4, level10, entry42717, model903 and active slot1 selected. Exact native catalog, one public stable read, type22 notification and passive PET_STABLE_SHOW agree. All9 opening,13 restoration,5 protected-actor and22 final closure checks pass; both original actors finish offline and selected with saved primary user pose unchanged.

Remaining limits: Opening only. Stable slot mutation, swapping,200-cell capacity, tame, revive, abandon and combat variants remain open. Native stable capacity is16. Earlier whole failed openings and the old mirrored decoder stay excluded. Scripts remain blocked; original CVar0 remains unrestored at1. Actual701117520-byte remote compressed SHA and all242 JSON/369 PNG hashes are verified. No retained pet rename, purchase or permission reset.

- [442_interactions_20261007_144.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_144.tar.gz.dvc), member `evidence/client_interactions_20261007_ui144/stable_alignment_deploy01/deployment.json`, SHA-256 `5ec3fcd779e4bdfbfc585ea5e07919b64ead5b1c38f6fe57a31a80fb9da42cb5`.
- [442_interactions_20261007_144.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_144.tar.gz.dvc), member `evidence/client_interactions_20261007_ui144/hunter_stable_alignment_prepare01/episode.json`, SHA-256 `5a6dfefbb497d0ae56ba1e1976802262651729754c85086c237130c5019e60cf`.
- [442_interactions_20261007_144.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_144.tar.gz.dvc), member `evidence/client_interactions_20261007_ui144/hunter_stable_alignment_entry01/episode.json`, SHA-256 `eebfcab834f5ea2805c4bab4b70a2ef814b80e8f9fedf5db0e2a83c749b2c5c0`.
- [442_interactions_20261007_144.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_144.tar.gz.dvc), member `evidence/client_interactions_20261007_ui144/hunter_stable_alignment_stage01/episode.json`, SHA-256 `1ed5ca5f58bcf092578476612fa7bae9d98ccc1e5ba6d17e54900c9681533f8a`.
- [442_interactions_20261007_144.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_144.tar.gz.dvc), member `evidence/client_interactions_20261007_ui144/hunter_stable_alignment_stage01/review01.json`, SHA-256 `be597c2e536ca88b58c107fb052954c865c425a3db0d48453561dfd0418ff3c8`.
- [442_interactions_20261007_144.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_144.tar.gz.dvc), member `evidence/client_interactions_20261007_ui144/hunter_stable_native_open05/episode.json`, SHA-256 `0bb8f8ab1a793f75578b4955de7cb50413124b2003f83b3547eeb7805673f9de`.
- [442_interactions_20261007_144.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_144.tar.gz.dvc), member `evidence/client_interactions_20261007_ui144/stable_open_visual_review01.json`, SHA-256 `1a5def5f3a0507809db32b162c75ccae50da9be3037a380854cce43be764dcf3`.
- [442_interactions_20261007_144.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_144.tar.gz.dvc), member `evidence/client_interactions_20261007_ui144/hunter_stable_final_park01/episode.json`, SHA-256 `c346ff2562719ef1c6ef37186bf3dff994486e301cf85344e72ad51220703cc5`.
- [442_interactions_20261007_144.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_144.tar.gz.dvc), member `evidence/client_interactions_20261007_ui144/hunter_stable_final_origin_finish01/episode.json`, SHA-256 `d48359ba1a2a439f03500089be7c383ab6683d5a2c0ce4d9333593810ed04f8d`.
- [442_interactions_20261007_144.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_144.tar.gz.dvc), member `evidence/client_interactions_20261007_ui144/hunter_stable_closed_boundary01/episode.json`, SHA-256 `0d8ef6aa8c45b6afe558fff59b17c2fa0a29cc72ec87dbfc4f6da4318e74b8ac`.
- [442_interactions_20261007_144.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_144.tar.gz.dvc), member `evidence/client_interactions_20261007_ui144/stable_closed_visual_review01.json`, SHA-256 `b52fcb310952d37df6fe0ef1a5b86b791a8555c37f01c74a530643550d0b959d`.

### owned_primary_native_melee_range_feedback

One fresh native-login Harnessone level 85 melee attempt against the exact static native Parched Buzzard 2830, 20.7449 metres from the saved user pose. One exact owned Attack produces native SMSG_ATTACKSWING_NOTINRANGE, matching modern error body00 and fresh stock UI_ERROR_MESSAGE code 265 You are too far away! All 10 range/10 restoration and 7 final normal parking checks pass; 15 entry checks preserve the primary and five other actors. The accompanying primary critter swing separately passes 13 damage/10 restoration checks, with 9847 damage clipped to 15 health and matching native/client SWING_DAMAGE.

Remaining limits: First fresh native range notification on this installed English client only. Repeated notifications across Stop/reload, moving targets, facing, spell range, hostile combat, class abilities and sustained cadence remain open. Native core deduplicates unchanged swing errors. Three failed selection preparations and three failed range trials remain whole excluded; no retroqualification. Scripts stay blocked, original CVar 0 unrestored at 1; only two existing HDMI-1 clients and no process restarts/models. Actual remote 520751252-byte compressed SHA and all 56 JSON / 227 PNG hashes plus accepted packet bodies are verified.

- [442_interactions_20261007_145.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_145.tar.gz.dvc), member `evidence/client_interactions_20261007_ui145/primary_combat_entry01/episode.json`, SHA-256 `4511f55272999e895de29be82ea4517e1aa3d766e11b2e6bc8df75afd741f3b2`.
- [442_interactions_20261007_145.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_145.tar.gz.dvc), member `evidence/client_interactions_20261007_ui145/primary_melee_stage01/episode.json`, SHA-256 `5d077517a744b87297805f21c06e82669561a57d1eac2956faa4fb2b3b9717ec`.
- [442_interactions_20261007_145.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_145.tar.gz.dvc), member `evidence/client_interactions_20261007_ui145/primary_melee_damage01/episode.json`, SHA-256 `efcab2c170e6614343ea9804f5b6ba944bd2ce08d88142fc577f1e3bfeb63c31`.
- [442_interactions_20261007_145.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_145.tar.gz.dvc), member `evidence/client_interactions_20261007_ui145/primary_range_native_dedup_authority01.json`, SHA-256 `5b45f112e750eddebd8267472ee3e534c7893cfcdbcdc31fa87ede1415e541a0`.
- [442_interactions_20261007_145.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_145.tar.gz.dvc), member `evidence/client_interactions_20261007_ui145/primary_combat_entry03/episode.json`, SHA-256 `e06eaa93ec75a48b741a41a44cb814df935abbace88425606e032a21f8e297c5`.
- [442_interactions_20261007_145.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_145.tar.gz.dvc), member `evidence/client_interactions_20261007_ui145/primary_buzzard_template_name_authority03.json`, SHA-256 `6af736b553f79c3d2f0f56881a99f0e4ed88b988fd26c34a1ba4b4723742777a`.
- [442_interactions_20261007_145.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_145.tar.gz.dvc), member `evidence/client_interactions_20261007_ui145/primary_range_stage07/episode.json`, SHA-256 `e40f9c04251027943caa69517d7522e7a5173208d26a87c4622a86c5e678c614`.
- [442_interactions_20261007_145.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_145.tar.gz.dvc), member `evidence/client_interactions_20261007_ui145/primary_range_stage07/review01.json`, SHA-256 `2600ab4b65e3074b2142c82a5d7e576ac96187938d59ff8c2d90846f1295515e`.
- [442_interactions_20261007_145.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_145.tar.gz.dvc), member `evidence/client_interactions_20261007_ui145/primary_range_error04/episode.json`, SHA-256 `de148ae98d7a0741af59cbb28d67ff0a74cf667eaba8cd6c38d17ad16767fdba`.
- [442_interactions_20261007_145.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_145.tar.gz.dvc), member `evidence/client_interactions_20261007_ui145/primary_range_visual_review01.json`, SHA-256 `0959c0a54b32d1da0259e4dc0de90767ce1da69a79fd6b177182b1b0594e8270`.
- [442_interactions_20261007_145.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_145.tar.gz.dvc), member `evidence/client_interactions_20261007_ui145/primary_combat_final_park01/episode.json`, SHA-256 `486e9bf2da74b77bdf134e9b4576c1067829397cb74d31df143b64ba42abd899`.
- [442_interactions_20261007_145.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_145.tar.gz.dvc), member `evidence/client_interactions_20261007_ui145/primary_combat_scout_boundary01/episode.json`, SHA-256 `d67947aa4b3cd9fb00a000082d3c39ed3acf234cc7308de1cc9b323e062c9589`.
- [442_interactions_20261007_145.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_145.tar.gz.dvc), member `evidence/client_interactions_20261007_ui145/primary_combat_closed_capture01/episode.json`, SHA-256 `98e456879416aa9bfad242a453eff9da64ca2767fec12d84e121f632522e255c`.
- [442_interactions_20261007_145.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_145.tar.gz.dvc), member `evidence/client_interactions_20261007_ui145/primary_combat_closed_visual_review01.json`, SHA-256 `1d9f90b0104b88d2d9be457c85d3fdeb26357b7182bf542f2fa7372abed4754c`.
- [442_interactions_20261007_145.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261007_145.tar.gz.dvc), member `evidence/client_interactions_20261007_ui145/primary_combat_admission_guards01.json`, SHA-256 `e136cd4d078a3e41cd160e0a28a361e4edfd8056b2405bb0cfb1dfb719d5cfef`.
