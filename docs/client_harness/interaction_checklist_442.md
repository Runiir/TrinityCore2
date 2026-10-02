# 4.4.2 player interaction checklist

891 operation contracts across 45 families. Each is pending qualification until a run supplies evidence.

Player interaction families and every installed binding. Per-spell/item/quest/encounter variants are expanded by the native content census.

Laya chooses ordinary keyboard/mouse actions. Screenshots are retained; this text-only model reads addon-visible state. Fixture setup, cleanup and outcome checks are recorded separately. A model error and a protocol error have different results.

Each successful mutation needs its native or local saved-state oracle and cleanup. Variants include class, race, faction, account versus character, solo versus group, combat versus idle, dead versus alive, zones, permissions and failure paths. Content IDs come from the existing content census.

## lifecycle

Fixture: `disposable_account`.

- [ ] `lifecycle.select_realm`
- [ ] `lifecycle.select_character`
- [ ] `lifecycle.create_character`
- [ ] `lifecycle.appearance_preview`
- [ ] `lifecycle.name_validation`
- [ ] `lifecycle.delete_character`
- [ ] `lifecycle.enter_world`
- [ ] `lifecycle.logout_cancel`
- [ ] `lifecycle.logout_confirm`
- [ ] `lifecycle.reconnect`
- [ ] `lifecycle.launcher_login`
- [ ] `lifecycle.password_login`
- [ ] `lifecycle.addon_enable`
- [ ] `lifecycle.addon_disable`
- [ ] `lifecycle.character_rename_if_available`

## character

Fixture: `equipped_character`.

- [ ] `character.open`
- [ ] `character.close`
- [ ] `character.stats`
- [ ] `character.equipment_tooltips`
- [ ] `character.compare_items`
- [ ] `character.equip`
- [ ] `character.unequip`
- [ ] `character.weapon_swap`
- [ ] `character.display_helm`
- [ ] `character.display_cloak`
- [ ] `character.equipment_set_create`
- [ ] `character.equipment_set_save`
- [ ] `character.equipment_set_equip`
- [ ] `character.equipment_set_delete`
- [ ] `character.titles`
- [ ] `character.select_title`

## reputation

Fixture: `known_factions`.

- [ ] `reputation.open`
- [ ] `reputation.close`
- [ ] `reputation.expand`
- [ ] `reputation.collapse`
- [ ] `reputation.inspect_standing`
- [ ] `reputation.at_war_toggle`
- [ ] `reputation.inactive_toggle`
- [ ] `reputation.watched_faction`
- [ ] `reputation.gain_standing`
- [ ] `reputation.lose_standing`
- [ ] `reputation.persist`

## currency

Fixture: `known_currencies`.

- [ ] `currency.open`
- [ ] `currency.close`
- [ ] `currency.expand`
- [ ] `currency.collapse`
- [ ] `currency.inspect_currency`
- [ ] `currency.backpack_toggle`
- [ ] `currency.unused_toggle`
- [ ] `currency.gain_currency`
- [ ] `currency.spend_currency`
- [ ] `currency.weekly_cap`
- [ ] `currency.persist`

## spellbook

Fixture: `class_variants`.

- [ ] `spellbook.open`
- [ ] `spellbook.close`
- [ ] `spellbook.general_tab`
- [ ] `spellbook.class_tab`
- [ ] `spellbook.pet_tab`
- [ ] `spellbook.professions_tab`
- [ ] `spellbook.next_page`
- [ ] `spellbook.previous_page`
- [ ] `spellbook.spell_tooltip`
- [ ] `spellbook.passive_tooltip`
- [ ] `spellbook.drag_to_bar`
- [ ] `spellbook.cast_spell`
- [ ] `spellbook.learn_spell`
- [ ] `spellbook.unlearn_spell`
- [ ] `spellbook.rank_resolution`

## talents

Fixture: `class_variants`.

- [ ] `talents.open`
- [ ] `talents.close`
- [ ] `talents.specialization_preview`
- [ ] `talents.choose_specialization`
- [ ] `talents.spend_point`
- [ ] `talents.reset_talents`
- [ ] `talents.dual_spec`
- [ ] `talents.switch_spec`
- [ ] `talents.inspect_talents`
- [ ] `talents.glyph_open`
- [ ] `talents.glyph_learn`
- [ ] `talents.glyph_apply`
- [ ] `talents.glyph_remove`
- [ ] `talents.glyph_tooltip`
- [ ] `talents.persist`

## professions

Fixture: `profession_variants`.

- [ ] `professions.open`
- [ ] `professions.close`
- [ ] `professions.primary_one`
- [ ] `professions.primary_two`
- [ ] `professions.cooking`
- [ ] `professions.first_aid`
- [ ] `professions.fishing`
- [ ] `professions.archaeology`
- [ ] `professions.recipe_list`
- [ ] `professions.recipe_search`
- [ ] `professions.recipe_filter`
- [ ] `professions.recipe_tooltip`
- [ ] `professions.recipe_select`
- [ ] `professions.reagent_tooltip`
- [ ] `professions.craft_one`
- [ ] `professions.craft_multiple`
- [ ] `professions.cancel_craft`
- [ ] `professions.craft_result`
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

- [ ] `archaeology.open`
- [ ] `archaeology.close`
- [ ] `archaeology.race_select`
- [ ] `archaeology.project_select`
- [ ] `archaeology.project_tooltip`
- [ ] `archaeology.survey`
- [ ] `archaeology.cast_bar`
- [ ] `archaeology.telescope_direction`
- [ ] `archaeology.distance_lantern`
- [ ] `archaeology.approach_find`
- [ ] `archaeology.loot_find`
- [ ] `archaeology.solve_project`
- [ ] `archaeology.use_keystone`
- [ ] `archaeology.project_completion`
- [ ] `archaeology.site_completion`
- [ ] `archaeology.site_rotation`
- [ ] `archaeology.continent_map`
- [ ] `archaeology.fragments_cap`
- [ ] `archaeology.persist`

## bags

Fixture: `inventory_items`.

- [ ] `bags.open_all`
- [ ] `bags.close_all`
- [ ] `bags.backpack`
- [ ] `bags.bag_one`
- [ ] `bags.bag_two`
- [ ] `bags.bag_three`
- [ ] `bags.bag_four`
- [ ] `bags.combined_bags_toggle`
- [ ] `bags.sort`
- [ ] `bags.search`
- [ ] `bags.quality_filter`
- [ ] `bags.item_tooltip`
- [ ] `bags.compare_tooltip`
- [ ] `bags.item_link`
- [ ] `bags.move_item`
- [ ] `bags.swap_item`
- [ ] `bags.split_stack`
- [ ] `bags.merge_stack`
- [ ] `bags.use_item`
- [ ] `bags.equip_item`
- [ ] `bags.unequip_item`
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

- [ ] `bank.open`
- [ ] `bank.close`
- [ ] `bank.deposit`
- [ ] `bank.withdraw`
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

- [ ] `merchant.open`
- [ ] `merchant.close`
- [ ] `merchant.browse_page`
- [ ] `merchant.buy_one`
- [ ] `merchant.buy_stack`
- [ ] `merchant.sell`
- [ ] `merchant.buyback`
- [ ] `merchant.repair_one`
- [ ] `merchant.repair_all`
- [ ] `merchant.insufficient_money`
- [ ] `merchant.unavailable_stock`
- [ ] `merchant.currency_cost`
- [ ] `merchant.reputation_discount`
- [ ] `merchant.persist`

## trainer

Fixture: `trainer_skills`.

- [ ] `trainer.open`
- [ ] `trainer.close`
- [ ] `trainer.filter_available`
- [ ] `trainer.filter_unavailable`
- [ ] `trainer.skill_tooltip`
- [ ] `trainer.learn_skill`
- [ ] `trainer.learn_rank`
- [ ] `trainer.insufficient_money`
- [ ] `trainer.prerequisite_error`
- [ ] `trainer.profession_limit`
- [ ] `trainer.persist`

## quests

Fixture: `quest_variants`.

- [ ] `quests.open_log`
- [ ] `quests.close_log`
- [ ] `quests.select`
- [ ] `quests.expand_zone`
- [ ] `quests.collapse_zone`
- [ ] `quests.details`
- [ ] `quests.track`
- [ ] `quests.untrack`
- [ ] `quests.abandon_cancel`
- [ ] `quests.abandon_confirm`
- [ ] `quests.share`
- [ ] `quests.accept`
- [ ] `quests.decline`
- [ ] `quests.progress`
- [ ] `quests.complete`
- [ ] `quests.choose_reward`
- [ ] `quests.reward_item`
- [ ] `quests.reward_money`
- [ ] `quests.escort`
- [ ] `quests.timed`
- [ ] `quests.daily`
- [ ] `quests.repeatable`
- [ ] `quests.auto_accept`
- [ ] `quests.auto_complete`
- [ ] `quests.unavailable_prerequisite`
- [ ] `quests.persist`

## map

Fixture: `map_variants`.

- [ ] `map.open`
- [ ] `map.close`
- [ ] `map.continent`
- [ ] `map.zone`
- [ ] `map.subzone`
- [ ] `map.zoom_in`
- [ ] `map.zoom_out`
- [ ] `map.pan`
- [ ] `map.quest_pin`
- [ ] `map.quest_details`
- [ ] `map.quest_route`
- [ ] `map.digsite_overlay`
- [ ] `map.taxi_overlay`
- [ ] `map.dungeon_floor`
- [ ] `map.coordinates`
- [ ] `map.player_position`
- [ ] `map.tracking_menu`
- [ ] `map.world_map_binding`
- [ ] `map.minimap_zoom`
- [ ] `map.minimap_tracking`
- [ ] `map.minimap_calendar`
- [ ] `map.minimap_clock`
- [ ] `map.minimap_mail`
- [ ] `map.minimap_battleground`

## achievements

Fixture: `achievement_variants`.

- [ ] `achievements.open`
- [ ] `achievements.close`
- [ ] `achievements.category`
- [ ] `achievements.achievement`
- [ ] `achievements.search`
- [ ] `achievements.tooltip`
- [ ] `achievements.track`
- [ ] `achievements.untrack`
- [ ] `achievements.compare`
- [ ] `achievements.criteria_progress`
- [ ] `achievements.earned_notification`
- [ ] `achievements.statistics`
- [ ] `achievements.persist`

## collections

Fixture: `mount_pet_variants`.

- [ ] `collections.open`
- [ ] `collections.close`
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

- [ ] `journal.open`
- [ ] `journal.close`
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

- [ ] `friends.open`
- [ ] `friends.close`
- [ ] `friends.list`
- [ ] `friends.add_friend`
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

- [ ] `chat.say`
- [ ] `chat.yell`
- [ ] `chat.whisper`
- [ ] `chat.reply`
- [ ] `chat.party`
- [ ] `chat.raid`
- [ ] `chat.raid_warning`
- [ ] `chat.guild`
- [ ] `chat.officer`
- [ ] `chat.channel_join`
- [ ] `chat.channel_leave`
- [ ] `chat.channel_list`
- [ ] `chat.channel_password`
- [ ] `chat.channel_owner`
- [ ] `chat.emote`
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

- [ ] `party.invite`
- [ ] `party.accept`
- [ ] `party.decline`
- [ ] `party.cancel_pending`
- [ ] `party.duplicate_invite`
- [ ] `party.full_group_error`
- [ ] `party.cross_map_invite`
- [ ] `party.leader_promote`
- [ ] `party.role_assign`
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

- [ ] `raid.convert_from_party`
- [ ] `raid.convert_to_party`
- [ ] `raid.raid_panel`
- [ ] `raid.roster`
- [ ] `raid.subgroup_move`
- [ ] `raid.assistant_promote`
- [ ] `raid.assistant_demote`
- [ ] `raid.main_tank`
- [ ] `raid.main_assist`
- [ ] `raid.ready_check`
- [ ] `raid.raid_target`
- [ ] `raid.world_marker`
- [ ] `raid.clear_marker`
- [ ] `raid.raid_warning`
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

- [ ] `guild.open`
- [ ] `guild.close`
- [ ] `guild.roster`
- [ ] `guild.online_filter`
- [ ] `guild.member_detail`
- [ ] `guild.note`
- [ ] `guild.officer_note`
- [ ] `guild.invite`
- [ ] `guild.accept`
- [ ] `guild.decline`
- [ ] `guild.rank_promote`
- [ ] `guild.rank_demote`
- [ ] `guild.remove_member`
- [ ] `guild.leadership_transfer`
- [ ] `guild.motd`
- [ ] `guild.information`
- [ ] `guild.chat`
- [ ] `guild.permissions`
- [ ] `guild.news`
- [ ] `guild.achievements`
- [ ] `guild.reputation`
- [ ] `guild.rewards`
- [ ] `guild.recruitment`
- [ ] `guild.charter_buy`
- [ ] `guild.charter_sign`
- [ ] `guild.charter_turn_in`
- [ ] `guild.leave`
- [ ] `guild.disband`
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

- [ ] `trade.request`
- [ ] `trade.accept`
- [ ] `trade.cancel`
- [ ] `trade.offer_item`
- [ ] `trade.remove_item`
- [ ] `trade.offer_stack`
- [ ] `trade.offer_money`
- [ ] `trade.nontraded_item`
- [ ] `trade.enchant_nontraded`
- [ ] `trade.confirm`
- [ ] `trade.changed_offer_reconfirm`
- [ ] `trade.out_of_range`
- [ ] `trade.reject`
- [ ] `trade.full_bag_error`
- [ ] `trade.persist`

## mail

Fixture: `owned_second_actor_mailbox`.

- [ ] `mail.open`
- [ ] `mail.close`
- [ ] `mail.inbox`
- [ ] `mail.read`
- [ ] `mail.attachment_money`
- [ ] `mail.take_item`
- [ ] `mail.take_all`
- [ ] `mail.return`
- [ ] `mail.delete`
- [ ] `mail.reply`
- [ ] `mail.compose`
- [ ] `mail.add_recipient`
- [ ] `mail.attach_item`
- [ ] `mail.attach_money`
- [ ] `mail.cod_send`
- [ ] `mail.cod_accept`
- [ ] `mail.send`
- [ ] `mail.postage`
- [ ] `mail.insufficient_money`
- [ ] `mail.full_bag_error`
- [ ] `mail.expired_mail`
- [ ] `mail.persist`

## auction

Fixture: `disposable_auction`.

- [ ] `auction.open`
- [ ] `auction.close`
- [ ] `auction.browse`
- [ ] `auction.search`
- [ ] `auction.category`
- [ ] `auction.filter`
- [ ] `auction.sort`
- [ ] `auction.select`
- [ ] `auction.inspect`
- [ ] `auction.bid`
- [ ] `auction.buyout`
- [ ] `auction.sell_stack`
- [ ] `auction.duration`
- [ ] `auction.deposit`
- [ ] `auction.auction_cancel`
- [ ] `auction.owned_auctions`
- [ ] `auction.bids_outbid`
- [ ] `auction.mail_delivery`
- [ ] `auction.persist`

## calendar

Fixture: `disposable_calendar`.

- [ ] `calendar.open`
- [ ] `calendar.close`
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
- [ ] `keybindings.category_search`
- [ ] `keybindings.select_action`
- [ ] `keybindings.assign_key`
- [ ] `keybindings.assign_second_key`
- [ ] `keybindings.modifier_chord`
- [ ] `keybindings.conflict_replace`
- [ ] `keybindings.conflict_cancel`
- [ ] `keybindings.clear_binding`
- [ ] `keybindings.per_character_toggle`
- [ ] `keybindings.defaults_cancel`
- [ ] `keybindings.defaults_apply`
- [ ] `keybindings.save`
- [ ] `keybindings.cancel`
- [ ] `keybindings.persistence`
- [ ] `keybindings.restore_original`

## macros

Fixture: `saved_local_macros`.

- [ ] `macros.open`
- [ ] `macros.close`
- [ ] `macros.account_tab`
- [ ] `macros.character_tab`
- [ ] `macros.create`
- [ ] `macros.name`
- [ ] `macros.icon`
- [ ] `macros.select`
- [ ] `macros.edit_body`
- [ ] `macros.save`
- [ ] `macros.rename`
- [ ] `macros.drag_to_actionbar`
- [ ] `macros.execute`
- [ ] `macros.delete_confirm`
- [ ] `macros.delete_cancel`
- [ ] `macros.macro_limit`
- [ ] `macros.persistence`
- [ ] `macros.restore_original`

## actionbars

Fixture: `saved_local_bars`.

- [ ] `actionbars.drag_spell`
- [ ] `actionbars.drag_item`
- [ ] `actionbars.drag_macro`
- [ ] `actionbars.clear_slot`
- [ ] `actionbars.swap_slots`
- [ ] `actionbars.page_next`
- [ ] `actionbars.page_previous`
- [ ] `actionbars.direct_page`
- [ ] `actionbars.extra_bars_toggle`
- [ ] `actionbars.lock_toggle`
- [ ] `actionbars.cooldown`
- [ ] `actionbars.charges`
- [ ] `actionbars.range_indicator`
- [ ] `actionbars.resource_indicator`
- [ ] `actionbars.vehicle_bar`
- [ ] `actionbars.stance_bar`
- [ ] `actionbars.pet_bar`
- [ ] `actionbars.override_bar`
- [ ] `actionbars.extra_action_button`
- [ ] `actionbars.persist`
- [ ] `actionbars.restore_original`

## settings

Fixture: `saved_local_settings`.

- [ ] `settings.open`
- [ ] `settings.close`
- [ ] `settings.graphics`
- [ ] `settings.resolution`
- [ ] `settings.window_mode`
- [ ] `settings.monitor_selection`
- [ ] `settings.render_scale`
- [ ] `settings.quality`
- [ ] `settings.sound_volume`
- [ ] `settings.mute`
- [ ] `settings.interface`
- [ ] `settings.mouse_sensitivity`
- [ ] `settings.keyboard_controls`
- [ ] `settings.accessibility`
- [ ] `settings.camera`
- [ ] `settings.nameplates`
- [ ] `settings.floating_combat_text`
- [ ] `settings.auto_loot`
- [ ] `settings.tutorials`
- [ ] `settings.addons`
- [ ] `settings.apply`
- [ ] `settings.cancel`
- [ ] `settings.defaults_cancel`
- [ ] `settings.defaults_apply`
- [ ] `settings.persistence`
- [ ] `settings.restore_original`

## menu

Fixture: `in_world`.

- [ ] `menu.open`
- [ ] `menu.close`
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
- [ ] `movement.strafe_right`
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
- [ ] `movement.follow`
- [ ] `movement.interact_with_target`

## targeting

Fixture: `owned_targets`.

- [ ] `targeting.click_target`
- [ ] `targeting.tab_enemy`
- [ ] `targeting.previous_enemy`
- [ ] `targeting.friendly_target`
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
- [ ] `targeting.inspect_player`
- [ ] `targeting.trade_context`
- [ ] `targeting.duel_context`
- [ ] `targeting.follow_context`
- [ ] `targeting.invite_context`
- [ ] `targeting.report_context_cancel`

## combat

Fixture: `class_variants`.

- [ ] `combat.melee_start`
- [ ] `combat.melee_stop`
- [ ] `combat.ranged_attack`
- [ ] `combat.instant_cast`
- [ ] `combat.cast_time`
- [ ] `combat.channel`
- [ ] `combat.cast_cancel`
- [ ] `combat.interrupt`
- [ ] `combat.auto_attack`
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
- [ ] `combat.stance`
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

- [ ] `pve_group_finder.open`
- [ ] `pve_group_finder.close`
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

- [ ] `pvp.open`
- [ ] `pvp.close`
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

- [ ] `ui_misc.dressup_open`
- [ ] `ui_misc.dressup_item`
- [ ] `ui_misc.dressup_rotate`
- [ ] `ui_misc.dressup_close`
- [ ] `ui_misc.item_text_open`
- [ ] `ui_misc.item_text_page`
- [ ] `ui_misc.item_text_close`
- [ ] `ui_misc.tooltip_compare`
- [ ] `ui_misc.achievement_link`
- [ ] `ui_misc.quest_link`
- [ ] `ui_misc.item_link`
- [ ] `ui_misc.spell_link`
- [ ] `ui_misc.copy_name`
- [ ] `ui_misc.screenshot`
- [ ] `ui_misc.toggle_ui`
- [ ] `ui_misc.zoom_camera`
- [ ] `ui_misc.camera_reset`
- [ ] `ui_misc.cinematics_skip`
- [ ] `ui_misc.movie_skip`
- [ ] `ui_misc.cursor_pickup`
- [ ] `ui_misc.cursor_cancel`
- [ ] `ui_misc.popup_confirm`
- [ ] `ui_misc.popup_cancel`
- [ ] `ui_misc.latency_display`
- [ ] `ui_misc.fps_display`
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
