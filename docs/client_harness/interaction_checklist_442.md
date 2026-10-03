# 4.4.2 player interaction checklist

916 operation contracts across 45 families. 201 have a qualified fixture variant; the rest remain pending.

A checked box means the linked evidence qualifies the stated fixture variant. It does not close other content, class, map, permission, persistence or failure variants. Opening a panel qualifies only opening that panel.

Player interaction families and every installed binding. Per-spell/item/quest/encounter variants are expanded by the native content census.

Regression trials use code-controlled ordinary keyboard/mouse inputs. The October 3 user-requested desktop-isolation probe explicitly uses Laya on two private client displays. Controller/model identities are recorded per episode. Screenshots and normal addon-visible state are retained. Fixture setup, cleanup and outcome checks are recorded separately. Input, observer and protocol failures have distinct evidence.

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
- [ ] `character.equipment_tooltips`
- [ ] `character.compare_items`
- [x] `character.equip` (qualified variant; [evidence](#equipment))
- [x] `character.unequip` (qualified variant; [evidence](#equipment))
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

- [x] `reputation.open` (qualified variant; [evidence](#panel_visibility))
- [x] `reputation.close` (qualified variant; [evidence](#panel_visibility))
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

- [x] `spellbook.open` (qualified variant; [evidence](#panel_visibility))
- [x] `spellbook.close` (qualified variant; [evidence](#panel_visibility))
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
- [ ] `talents.glyph_filter_known`
- [ ] `talents.glyph_filter_unknown`
- [ ] `talents.glyph_filter_prime`
- [ ] `talents.glyph_filter_major`
- [ ] `talents.glyph_filter_minor`
- [ ] `talents.glyph_learn`
- [ ] `talents.glyph_apply`
- [ ] `talents.glyph_replace`
- [ ] `talents.glyph_remove`
- [ ] `talents.glyph_tooltip`
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
- [ ] `archaeology.close`
- [ ] `archaeology.race_select`
- [ ] `archaeology.project_select`
- [ ] `archaeology.project_tooltip`
- [x] `archaeology.survey` (qualified variant; [evidence](#archaeology_loop))
- [ ] `archaeology.cast_bar`
- [x] `archaeology.telescope_direction` (qualified variant; [evidence](#archaeology_loop))
- [x] `archaeology.distance_lantern` (qualified variant; [evidence](#archaeology_loop))
- [x] `archaeology.approach_find` (qualified variant; [evidence](#archaeology_loop))
- [x] `archaeology.loot_find` (qualified variant; [evidence](#archaeology_loop))
- [ ] `archaeology.solve_project`
- [ ] `archaeology.use_keystone`
- [ ] `archaeology.project_completion`
- [x] `archaeology.site_completion` (qualified variant; [evidence](#archaeology_loop))
- [x] `archaeology.site_rotation` (qualified variant; [evidence](#archaeology_loop))
- [ ] `archaeology.continent_map`
- [ ] `archaeology.fragments_cap`
- [ ] `archaeology.persist`

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
- [x] `quests.giver_available_marker` (qualified variant; [evidence](#available_quest_marker))
- [ ] `quests.giver_trivial_marker`
- [ ] `quests.giver_incomplete_marker`
- [x] `quests.giver_complete_marker` (qualified variant; [evidence](#ordinary_quest_melee_completion))
- [ ] `quests.giver_repeatable_marker`
- [ ] `quests.giver_unavailable_marker`

## map

Fixture: `map_variants`.

- [x] `map.open` (qualified variant; [evidence](#panel_visibility))
- [x] `map.close` (qualified variant; [evidence](#panel_visibility))
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

- [x] `achievements.open` (qualified variant; [evidence](#panel_visibility))
- [x] `achievements.close` (qualified variant; [evidence](#panel_visibility))
- [ ] `achievements.category`
- [ ] `achievements.achievement`
- [ ] `achievements.search`
- [ ] `achievements.tooltip`
- [ ] `achievements.track`
- [ ] `achievements.untrack`
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

- [ ] `actionbars.drag_spell`
- [ ] `actionbars.drag_item`
- [x] `actionbars.drag_macro` (qualified variant; [evidence](#macro_mutation))
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
- [x] `actionbars.restore_original` (qualified variant; [evidence](#macro_mutation))

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

One helmet unequipped and reequipped; native and visible strength, armor, damage and maximum-health deltas agree and the entire fixture is restored.

Remaining limits: Unsampled gear slots, weapon swaps, sets and item comparison/tooltips remain open.

- [442_interactions_20261002_04.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261002_04.tar.gz.dvc), member `evidence/client_interactions_20261002_ui03/equipment_02/episode.json`, SHA-256 `44214da3f31946df95c34cedc4a2ef828f8d15adbe3dc98fd39ca9797abe3a0c`.
  Checked cases: `character.unequip` (equipment_change_pass), `character.equip` (equipment_change_pass), `character.stats.unequipped` (character_stats_pass), `character.stats.equipped_after` (character_stats_pass).

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

Remaining limits: Code-controlled fixture inputs qualify client behavior. Objective progress, completion/rewards, sharing, persistence, other questgiver types, eligibility and objective variants remain open.

- [442_interactions_20261003_24.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_24.tar.gz.dvc), member `evidence/client_interactions_20261003_ui23/manual_quest_accept_11/episode.json`, SHA-256 `d0777925ada8a4ae8be930d95b59912ab50136d45872dd53242baa2bc724b386`.
  Checked cases: `quests.manual_accept` (quest_manual_accept_pass), `quests.manual_collapse` (quest_zone_collapse_pass), `quests.manual_abandon_cancel` (quest_abandon_cancel_pass), `quests.manual_read_log` (quest_log_details_pass), `quests.manual_abandon_confirm` (quest_abandon_pass).
- [442_interactions_20261003_24.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_24.tar.gz.dvc), member `evidence/client_interactions_20261003_ui23/manual_quest_decline_12/episode.json`, SHA-256 `56635a814a344dd1d2f7d3d53b2f9d78edfc482b749a7138df0b67781b33b23e`.
  Checked cases: `quests.manual_decline` (quest_manual_decline_pass).

### glyph_socket_panel

Stock glyph panel opens with nine correctly cropped enabled Prime/Major/Minor sockets; native talent/glyph state and inventory/money remain unchanged.

Remaining limits: Application, removal, learning, tooltips, other classes and level/locked variants remain open.

- [442_interactions_20261003_25.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_25.tar.gz.dvc), member `evidence/client_interactions_20261003_ui24/talent_glyph_panels_02/episode.json`, SHA-256 `b237358829981a0f17ea853cdd503c3add2f03b64ead9c04f5b0875bd2688a58`.
  Checked cases: `talents.glyph_open_repaired` (glyph_panel_pass).

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

Remaining limits: Learned glyphs, filters, tooltips, socket positions, placement/removal and effects remain open. Catalog type agreement does not establish the correct GlyphSlot ID mapping.

- [442_interactions_20261003_26.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_26.tar.gz.dvc), member `evidence/client_interactions_20261003_ui25/talent_glyph_catalog_02/episode.json`, SHA-256 `2a654b0848ea92421b16ff362beff3a3feb3313d469f199b39ba4d02050c4655`.
- [442_interactions_20261003_26.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_26.tar.gz.dvc), member `evidence/client_interactions_20261003_ui25/talent_glyph_catalog_02/glyph_catalog_review.json`, SHA-256 `b1c89757271a444870323ce1f31eea6a80ad302aaff8de8b1ab2f85db9d540f8`.

### ordinary_quest_melee_completion

One quest 52 run earns five bear and eight wolf kills through ordinary melee against existing creatures. Each attack start and native/public/translated credit matches its victim; 8/5 objectives complete and Guard Thomas shows a visible yellow turn-in question mark.

Remaining limits: Reward turn-in failed its capped XP oracle before claiming and remains open. Setup uses native pose staging, so it does not qualify navigation. Repeated swing cadence, damage values, alive-target stop, ranged/spell combat and other marker categories remain open.

- [442_interactions_20261003_26.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_26.tar.gz.dvc), member `evidence/client_interactions_20261003_ui25/quest_reward_03/episode.json`, SHA-256 `82dbeca029d751b5a8bd5e8bbe2b7d6e9c41ac9df3d46cce95381f51738c1a22`.
- [442_interactions_20261003_26.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_26.tar.gz.dvc), member `evidence/client_interactions_20261003_ui25/quest_reward_03/melee_review.json`, SHA-256 `5345ded64629c637902dd9e8c6d04ed69cb0a151198e860248d67b5fa8536036`.
