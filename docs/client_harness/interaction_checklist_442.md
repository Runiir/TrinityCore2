# 4.4.2 player interaction checklist

916 operation contracts across 45 families. 306 have a qualified fixture variant; the rest remain pending.

A checked box means the linked evidence qualifies the stated fixture variant. It does not close other content, class, map, permission, persistence or failure variants. Opening a panel qualifies only opening that panel.

Player interaction families and every installed binding. Per-spell/item/quest/encounter variants are expanded by the native content census.

New regression trials use code-controlled ordinary keyboard/mouse inputs under the current AGENTS.md. Historical desktop-isolation evidence retains its actual Laya identity. Controller/model identities are recorded per episode. Screenshots and normal addon-visible state are retained. Fixture setup, cleanup and outcome checks are recorded separately. Input, observer and protocol failures have distinct evidence.

Each successful mutation needs its native or local saved-state oracle and cleanup. Variants include class, race, faction, account versus character, solo versus group, combat versus idle, dead versus alive, zones, permissions and failure paths. Content IDs come from the existing content census.

## lifecycle

Fixture: `disposable_account`.

- [ ] `lifecycle.select_realm`
- [ ] `lifecycle.select_character`
- [ ] `lifecycle.create_character`
- [ ] `lifecycle.appearance_preview`
- [ ] `lifecycle.name_validation`
- [ ] `lifecycle.delete_character`
- [x] `lifecycle.enter_world` (qualified variant; [evidence](#logout_reentry))
- [x] `lifecycle.logout_cancel` (qualified variant; [evidence](#logout_reentry))
- [x] `lifecycle.logout_confirm` (qualified variant; [evidence](#logout_reentry))
- [ ] `lifecycle.reconnect`
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
- [ ] `spellbook.pet_tab`
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
- [ ] `professions.recipe_filter`
- [ ] `professions.recipe_tooltip`
- [x] `professions.recipe_select` (qualified variant; [evidence](#crafting))
- [ ] `professions.reagent_tooltip`
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
- [ ] `bags.item_tooltip`
- [ ] `bags.compare_tooltip`
- [ ] `bags.item_link`
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
- [ ] `friends.list`
- [x] `friends.add_friend` (qualified variant; [evidence](#party_invitation))
- [ ] `friends.online_presence`
- [ ] `friends.offline_presence`
- [ ] `friends.note_edit`
- [ ] `friends.note_persist`
- [ ] `friends.remove_friend`
- [ ] `friends.add_ignore`
- [ ] `friends.ignored_chat`
- [ ] `friends.remove_ignore`
- [ ] `friends.who_open`
- [ ] `friends.who_search`
- [ ] `friends.whisper`
- [ ] `friends.self_friend_error`
- [ ] `friends.nonexistent_friend_error`
- [ ] `friends.duplicate_friend_error`
- [ ] `friends.friend_limit`

## chat

Fixture: `owned_second_actor`.

- [x] `chat.say` (qualified variant; [evidence](#chat))
- [x] `chat.yell` (qualified variant; [evidence](#chat))
- [x] `chat.whisper` (qualified variant; [evidence](#chat))
- [ ] `chat.reply`
- [ ] `chat.party`
- [x] `chat.raid` (qualified variant; [evidence](#chat))
- [x] `chat.raid_warning` (qualified variant; [evidence](#chat))
- [x] `chat.guild` (qualified variant; [evidence](#guild_notes))
- [x] `chat.officer` (qualified variant; [evidence](#guild_notes))
- [ ] `chat.channel_join`
- [ ] `chat.channel_leave`
- [ ] `chat.channel_list`
- [ ] `chat.channel_password`
- [ ] `chat.channel_owner`
- [x] `chat.emote` (qualified variant; [evidence](#chat))
- [ ] `chat.language_switch`
- [ ] `chat.combat_log`
- [ ] `chat.chat_settings`
- [ ] `chat.chat_tab_create`
- [ ] `chat.chat_tab_rename`
- [ ] `chat.chat_tab_close`
- [ ] `chat.font_size`
- [ ] `chat.timestamps`
- [ ] `chat.chat_links`
- [ ] `chat.scroll_history`
- [ ] `chat.copy_if_available`
- [ ] `chat.mute_voice`
- [ ] `chat.report_ui_cancel`

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

- [ ] `keybindings.open`
- [ ] `keybindings.close`
- [x] `keybindings.category_search` (qualified variant; [evidence](#keybinding_mutation))
- [x] `keybindings.select_action` (qualified variant; [evidence](#keybinding_mutation))
- [ ] `keybindings.assign_key`
- [x] `keybindings.assign_second_key` (qualified variant; [evidence](#keybinding_mutation))
- [x] `keybindings.modifier_chord` (qualified variant; [evidence](#keybinding_mutation))
- [ ] `keybindings.conflict_replace`
- [ ] `keybindings.conflict_cancel`
- [ ] `keybindings.clear_binding`
- [ ] `keybindings.per_character_toggle`
- [ ] `keybindings.defaults_cancel`
- [ ] `keybindings.defaults_apply`
- [x] `keybindings.save` (qualified variant; [evidence](#keybinding_mutation))
- [ ] `keybindings.cancel`
- [x] `keybindings.persistence` (qualified variant; [evidence](#keybinding_mutation))
- [x] `keybindings.restore_original` (qualified variant; [evidence](#keybinding_mutation))

## macros

Fixture: `saved_local_macros`.

- [x] `macros.open` (qualified variant; [evidence](#panel_visibility))
- [x] `macros.close` (qualified variant; [evidence](#panel_visibility))
- [ ] `macros.account_tab`
- [ ] `macros.character_tab`
- [x] `macros.create` (qualified variant; [evidence](#macro_mutation))
- [x] `macros.name` (qualified variant; [evidence](#macro_mutation))
- [ ] `macros.icon`
- [ ] `macros.select`
- [x] `macros.edit_body` (qualified variant; [evidence](#macro_mutation))
- [x] `macros.save` (qualified variant; [evidence](#macro_mutation))
- [ ] `macros.rename`
- [x] `macros.drag_to_actionbar` (qualified variant; [evidence](#macro_mutation))
- [x] `macros.execute` (qualified variant; [evidence](#macro_mutation))
- [x] `macros.delete_confirm` (qualified variant; [evidence](#macro_mutation))
- [ ] `macros.delete_cancel`
- [ ] `macros.macro_limit`
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
- [ ] `actionbars.extra_bars_toggle`
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
- [ ] `settings.graphics`
- [ ] `settings.resolution`
- [ ] `settings.window_mode`
- [ ] `settings.monitor_selection`
- [ ] `settings.render_scale`
- [ ] `settings.quality`
- [ ] `settings.sound_volume`
- [x] `settings.mute` (qualified variant; [evidence](#stock_boolean_settings_roundtrip))
- [ ] `settings.interface`
- [ ] `settings.mouse_sensitivity`
- [ ] `settings.keyboard_controls`
- [ ] `settings.accessibility`
- [x] `settings.camera` (qualified variant; [evidence](#stock_interface_boolean_settings))
- [x] `settings.nameplates` (qualified variant; [evidence](#stock_interface_boolean_settings))
- [x] `settings.floating_combat_text` (qualified variant; [evidence](#stock_interface_boolean_settings))
- [x] `settings.auto_loot` (qualified variant; [evidence](#stock_boolean_settings_roundtrip))
- [x] `settings.tutorials` (qualified variant; [evidence](#stock_interface_boolean_settings))
- [ ] `settings.addons`
- [ ] `settings.apply`
- [ ] `settings.cancel`
- [ ] `settings.defaults_cancel`
- [ ] `settings.defaults_apply`
- [ ] `settings.persistence`
- [x] `settings.restore_original` (qualified variant; [evidence](#stock_boolean_settings_roundtrip))

## menu

Fixture: `in_world`.

- [x] `menu.open` (qualified variant; [evidence](#panel_visibility))
- [x] `menu.close` (qualified variant; [evidence](#panel_visibility))
- [ ] `menu.options`
- [ ] `menu.keybindings`
- [ ] `menu.macros`
- [ ] `menu.addons`
- [ ] `menu.help`
- [ ] `menu.logout`
- [ ] `menu.exit_cancel`

## help

Fixture: `offline_local_server`.

- [ ] `help.open`
- [ ] `help.close`
- [ ] `help.unstuck`
- [ ] `help.support_category`
- [ ] `help.ticket_create_if_supported`
- [ ] `help.ticket_status_if_supported`
- [ ] `help.report_bug_if_supported`
- [ ] `help.survey_if_supported`

## movement

Fixture: `safe_terrain_variants`.

- [ ] `movement.forward`
- [ ] `movement.backward`
- [ ] `movement.turn_left`
- [ ] `movement.turn_right`
- [ ] `movement.strafe_left`
- [x] `movement.strafe_right` (qualified variant; [evidence](#follow))
- [ ] `movement.mouse_turn`
- [ ] `movement.autorun`
- [ ] `movement.stop`
- [ ] `movement.walk_toggle`
- [ ] `movement.jump`
- [ ] `movement.sit`
- [ ] `movement.stand`
- [ ] `movement.sheath`
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

- [ ] `targeting.click_target`
- [ ] `targeting.tab_enemy`
- [ ] `targeting.previous_enemy`
- [x] `targeting.friendly_target` (qualified variant; [evidence](#nearby_target))
- [ ] `targeting.clear_target`
- [ ] `targeting.target_self`
- [ ] `targeting.party_target`
- [ ] `targeting.raid_target`
- [ ] `targeting.assist`
- [ ] `targeting.focus`
- [ ] `targeting.clear_focus`
- [ ] `targeting.target_target`
- [ ] `targeting.target_last`
- [ ] `targeting.mouseover`
- [ ] `targeting.tooltip`
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
- [ ] `combat.melee_stop`
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
- [ ] `combat.range_error`
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

- [ ] `pets.summon`
- [ ] `pets.dismiss`
- [ ] `pets.command_attack`
- [ ] `pets.command_follow`
- [ ] `pets.command_stay`
- [ ] `pets.command_move_to`
- [ ] `pets.passive`
- [ ] `pets.defensive`
- [ ] `pets.assist`
- [ ] `pets.autocast_toggle`
- [ ] `pets.spell_cast`
- [ ] `pets.pet_target`
- [ ] `pets.pet_health`
- [ ] `pets.pet_power`
- [ ] `pets.happiness_if_available`
- [ ] `pets.rename`
- [ ] `pets.stable_open`
- [ ] `pets.stable_slot`
- [ ] `pets.stable_swap`
- [ ] `pets.tame`
- [ ] `pets.abandon_confirm`
- [ ] `pets.abandon_cancel`
- [ ] `pets.revive`
- [ ] `pets.vehicle_pet_bar`
- [ ] `pets.persist`

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
- [ ] `ui_misc.item_text_open`
- [ ] `ui_misc.item_text_page`
- [ ] `ui_misc.item_text_close`
- [x] `ui_misc.tooltip_compare` (qualified variant; [evidence](#stock_owned_sword_comparison))
- [ ] `ui_misc.achievement_link`
- [ ] `ui_misc.quest_link`
- [ ] `ui_misc.item_link`
- [ ] `ui_misc.spell_link`
- [ ] `ui_misc.copy_name`
- [x] `ui_misc.screenshot` (qualified variant; [evidence](#stock_display_controls))
- [x] `ui_misc.toggle_ui` (qualified variant; [evidence](#stock_display_controls))
- [x] `ui_misc.zoom_camera` (qualified variant; [evidence](#stock_camera_zoom_latency))
- [ ] `ui_misc.camera_reset`
- [ ] `ui_misc.cinematics_skip`
- [ ] `ui_misc.movie_skip`
- [x] `ui_misc.cursor_pickup` (qualified variant; [evidence](#stock_spellbook_action_roundtrip))
- [x] `ui_misc.cursor_cancel` (qualified variant; [evidence](#stock_spellbook_action_roundtrip))
- [ ] `ui_misc.popup_confirm`
- [ ] `ui_misc.popup_cancel`
- [x] `ui_misc.latency_display` (qualified variant; [evidence](#stock_camera_zoom_latency))
- [x] `ui_misc.fps_display` (qualified variant; [evidence](#stock_display_controls))
- [ ] `ui_misc.network_disconnect_notification`

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
