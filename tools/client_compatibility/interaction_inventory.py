"""Player interaction checklist, expanded with every binding in the installed client."""
import argparse
import json
import math
import time
from collections import Counter
from . import lab_runtime as lab, owned_input, actors
from .observation.interactions import decode_image
from .interaction_qualifications import reconcile,load,render_evidence

MANIFEST=lab.REPO/'experiments/configs/client_harness/442_interactions_v1.json'
# Operations are contracts, not passes. Class/content variants use the content census.
FAMILIES={
 'lifecycle':('disposable_account','select_realm select_character create_character appearance_preview name_validation delete_character enter_world logout_cancel logout_confirm reconnect launcher_login password_login addon_enable addon_disable character_rename_if_available'),
 'character':('equipped_character','open close stats equipment_tooltips compare_items equip unequip weapon_swap display_helm display_cloak equipment_set_create equipment_set_save equipment_set_equip equipment_set_delete titles select_title'),
 'reputation':('known_factions','open close expand collapse inspect_standing at_war_toggle inactive_toggle watched_faction gain_standing lose_standing persist'),
 'currency':('known_currencies','open close expand collapse inspect_currency backpack_toggle unused_toggle gain_currency spend_currency weekly_cap persist'),
 'spellbook':('class_variants','open close general_tab class_tab pet_tab professions_tab next_page previous_page spell_tooltip passive_tooltip drag_to_bar cast_spell learn_spell unlearn_spell rank_resolution'),
 'talents':('class_variants','open close specialization_preview choose_specialization spend_point reset_talents dual_spec switch_spec inspect_talents glyph_open glyph_learn glyph_apply glyph_remove glyph_tooltip persist'),
 'professions':('profession_variants','open close primary_one primary_two cooking first_aid fishing archaeology recipe_list recipe_search recipe_filter recipe_tooltip recipe_select reagent_tooltip craft_one craft_multiple cancel_craft craft_result skill_gain learn_recipe unlearn_profession profession_cooldown enchant_item enchant_trade socket_item gather_node gather_loot persist'),
 'archaeology':('digsite_variants','open close race_select project_select project_tooltip survey cast_bar telescope_direction distance_lantern approach_find loot_find solve_project use_keystone project_completion site_completion site_rotation continent_map fragments_cap persist'),
 'bags':('inventory_items','open_all close_all backpack bag_one bag_two bag_three bag_four combined_bags_toggle sort search quality_filter item_tooltip compare_tooltip item_link move_item swap_item split_stack merge_stack use_item equip_item unequip_item destroy_confirm destroy_cancel bag_replace keyring_if_available cooldown_display full_bag_error locked_item_error persist'),
 'bank':('banker_inventory','open close deposit withdraw swap split buy_slot equip_bank_bag bank_bag_open reagent_bank_if_available guild_bank_link persist'),
 'merchant':('merchant_inventory','open close browse_page buy_one buy_stack sell buyback repair_one repair_all insufficient_money unavailable_stock currency_cost reputation_discount persist'),
 'trainer':('trainer_skills','open close filter_available filter_unavailable filter_known skill_tooltip learn_skill learn_rank insufficient_money prerequisite_error profession_limit persist'),
 'quests':('quest_variants','open_log close_log select expand_zone collapse_zone details track untrack abandon_cancel abandon_confirm share accept decline progress complete choose_reward reward_item reward_money escort timed daily repeatable auto_accept auto_complete unavailable_prerequisite persist'),
 'map':('map_variants','open close continent zone subzone zoom_in zoom_out pan quest_pin quest_details quest_route digsite_overlay taxi_overlay dungeon_floor coordinates player_position tracking_menu world_map_binding minimap_zoom minimap_tracking minimap_calendar minimap_clock minimap_mail minimap_battleground'),
 'achievements':('achievement_variants','open close category achievement search tooltip track untrack compare criteria_progress earned_notification statistics persist'),
 'collections':('mount_pet_variants','open close mount_tab mount_search mount_filter mount_preview mount_summon dismount favorite_mount ground_mount flying_mount passenger_mount companion_tab companion_search companion_preview companion_summon companion_dismiss favorite_companion pet_battle_if_available toy_tab_if_available heirloom_tab_if_available persist'),
 'journal':('encounter_variants','open close expansion instance difficulty boss overview ability loot role_filter class_filter slot_filter search map_link model_preview'),
 'friends':('owned_second_actor','open close list add_friend online_presence offline_presence note_edit note_persist remove_friend add_ignore ignored_chat remove_ignore who_open who_search whisper self_friend_error nonexistent_friend_error duplicate_friend_error friend_limit'),
 'chat':('owned_second_actor','say yell whisper reply party raid raid_warning guild officer channel_join channel_leave channel_list channel_password channel_owner emote language_switch combat_log chat_settings chat_tab_create chat_tab_rename chat_tab_close font_size timestamps chat_links scroll_history copy_if_available mute_voice report_ui_cancel'),
 'party':('owned_second_actor','invite accept decline cancel_pending duplicate_invite full_group_error cross_map_invite leader_promote role_poll role_assign loot_method loot_threshold master_looter target_marker ready_check ready_accept ready_decline party_chat leave kick disband disconnect_rejoin persist'),
 'raid':('owned_group','convert_from_party convert_to_party raid_panel roster roster_health_bars subgroup_move assistant_promote assistant_demote everyone_assistant frame_lock frame_unlock frame_show frame_hide main_tank main_assist ready_check ready_timeout raid_target world_marker clear_marker raid_warning loot_method leave kick disband raid_info lockout_extend reset_instance difficulty_normal difficulty_heroic raid_size_10 raid_size_25'),
 'guild':('disposable_guild','open close roster online_filter member_detail note officer_note invite accept decline rank_promote rank_demote remove_member leadership_transfer motd information chat permissions news achievements reputation rewards recruitment charter_buy charter_sign charter_turn_in leave disband persist'),
 'guild_bank':('disposable_guild_bank','open close tab_select view_item deposit withdraw split_stack deposit_money withdraw_money buy_tab tab_name tab_icon tab_text log_view permissions_error persist'),
 'trade':('owned_second_actor','request accept cancel offer_item remove_item offer_stack offer_money nontraded_item enchant_nontraded confirm changed_offer_reconfirm out_of_range reject full_bag_error persist'),
 'mail':('owned_second_actor_mailbox','open close inbox read attachment_money take_item take_all return delete reply compose add_recipient attach_item attach_money cod_send cod_accept send postage insufficient_money full_bag_error expired_mail persist'),
 'auction':('disposable_auction','open close browse search category filter sort select inspect bid buyout sell_item sell_stack duration deposit auction_cancel owned_auctions bids_outbid mail_delivery persist'),
 'calendar':('disposable_calendar','open close previous_month next_month event_view event_create event_edit event_delete invite rsvp_accept rsvp_decline rsvp_tentative moderator recurring_event server_time persist'),
 'keybindings':('saved_local_bindings','open close category_search select_action assign_key assign_second_key modifier_chord conflict_replace conflict_cancel clear_binding per_character_toggle defaults_cancel defaults_apply save cancel persistence restore_original'),
 'macros':('saved_local_macros','open close account_tab character_tab create name icon select edit_body save rename drag_to_actionbar execute delete_confirm delete_cancel macro_limit persistence restore_original'),
 'actionbars':('saved_local_bars','drag_spell drag_item drag_macro clear_slot swap_slots page_next page_previous direct_page extra_bars_toggle lock_toggle cooldown charges range_indicator resource_indicator vehicle_bar stance_bar pet_bar override_bar extra_action_button persist restore_original'),
 'settings':('saved_local_settings','open close graphics resolution window_mode monitor_selection render_scale quality sound_volume mute interface mouse_sensitivity keyboard_controls accessibility camera nameplates floating_combat_text auto_loot tutorials addons apply cancel defaults_cancel defaults_apply persistence restore_original'),
 'menu':('in_world','open close options keybindings macros addons help logout exit_cancel'),
 'help':('offline_local_server','open close unstuck support_category ticket_create_if_supported ticket_status_if_supported report_bug_if_supported survey_if_supported'),
 'movement':('safe_terrain_variants','forward backward turn_left turn_right strafe_left strafe_right mouse_turn autorun stop walk_toggle jump sit stand sheath swim dive surface breath falling fall_damage collision slope water_entry water_exit mount_ground mount_fly takeoff ascend descend land dismount indoor_mount_error taxi board_transport leave_transport vehicle_enter vehicle_exit vehicle_seat follow interact_with_target'),
 'targeting':('owned_targets','click_target tab_enemy previous_enemy friendly_target clear_target target_self party_target raid_target assist focus clear_focus target_target target_last mouseover tooltip nameplate inspect_player trade_context duel_context follow_context invite_context report_context_cancel'),
 'combat':('class_variants','melee_start melee_stop ranged_attack instant_cast cast_time channel cast_cancel interrupt auto_attack cooldown resource_cost insufficient_resource range_error line_of_sight_error facing_error moving_cast_error aura_apply aura_expire aura_cancel dispel combat_flag threat aggro equipment_lock immunity crowd_control shapeshift stance combo_points rune_resource holy_power eclipse totems resurrection persist'),
 'pets':('pet_class_variants','summon dismiss command_attack command_follow command_stay command_move_to passive defensive assist autocast_toggle spell_cast pet_target pet_health pet_power happiness_if_available rename stable_open stable_slot stable_swap tame abandon_confirm abandon_cancel revive vehicle_pet_bar persist'),
 'loot':('loot_variants','open close corpse_money item_pickup auto_loot quest_loot gather_loot fishing_loot skinning disenchant prospect mill group_roll_need group_roll_greed group_roll_pass master_loot free_for_all round_robin full_bag_error bind_confirm loot_release persist'),
 'death':('disposable_actor','death_animation release_spirit graveyard movement_ghost corpse_reclaim resurrection_accept resurrection_decline spirit_healer resurrection_sickness durability_loss disconnect_dead persist'),
 'travel':('travel_variants','hearthstone teleport_spell portal_enter boat zeppelin tram taxi_open taxi_learn taxi_select taxi_cost taxi_animation taxi_complete taxi_instant_experiment_only flight_ground_control flight_master_license cold_weather_flying outland_flying cross_continent_transfer instance_enter instance_leave dungeon_portal summon_accept summon_decline summon_expire'),
 'pve_group_finder':('owned_group_and_queue','open close role_choose dungeon_select random_dungeon queue cancel_queue role_check accept_proposal decline_proposal teleport_in teleport_out vote_kick deserter reward raid_browser raid_finder_if_available difficulty_lock instance_reset saved_instances'),
 'pvp':('owned_pvp_fixture','open close battleground_select battleground_queue group_queue cancel_queue accept_invite decline_invite leave_battleground scoreboard objective_flag objective_capture honor_gain honor_purchase arena_team_create arena_team_invite arena_team_leave arena_queue arena_rating arena_reward duel_request duel_accept duel_decline duel_complete duel_cancel world_pvp_toggle persist'),
 'world_objects':('object_variants','gossip_open gossip_select gossip_back close inspect text_page door chest lever quest_object fishing_pool destructible_object chair transport gameobject_cast cancel_gameobject_cast unavailable_object error_distance'),
 'ui_misc':('in_world','dressup_open dressup_item dressup_rotate dressup_close item_text_open item_text_page item_text_close tooltip_compare achievement_link quest_link item_link spell_link copy_name screenshot toggle_ui zoom_camera camera_reset cinematics_skip movie_skip cursor_pickup cursor_cancel popup_confirm popup_cancel latency_display fps_display network_disconnect_notification'),
 'account_services':('unsupported_service_contract','shop_open store_offer_request token_ui character_boost race_change faction_change paid_rename paid_transfer social_contract battlenet_friends battlenet_whisper voice_chat collections_account_sync support_ticket'),
}


def checklist():
    cases=[]
    for family,(fixture,words) in FAMILIES.items():
        for operation in words.split():
            cases.append({'id':family+'.'+operation,'family':family,'operation':operation,
                'fixture':fixture,'oracle':'Visible UI outcome and attributable native state; mutations must persist or be restored.',
                'availability':'verify_in_installed_build','automation':'pending_adapter'})
    data={'schema':'client442_interactions_v1','client_build':60895,
        'scope':'Player interaction families and every installed binding. Per-spell/item/quest/encounter variants are expanded by the native content census.',
        'limits':['An inventory entry never constitutes a pass.',
            'Account services and later-expansion UI need explicit unsupported/not-applicable contracts, not fabricated successes.',
            'Opening a panel does not qualify the actions or data inside it.',
            'New live bindings and UI controls must be reconciled; this is a versioned checklist, not a claim of proven exhaustive game compatibility.'],
        'families':dict(Counter(c['family'] for c in cases)),'cases':cases}
    return reconcile(data,load(lab.REPO),lab.REPO)


def render(data):
    lines=['# 4.4.2 player interaction checklist','',f"{len(data['cases'])} operation contracts across {len(data['families'])} families. {data.get('qualified_operations',0)} have a qualified fixture variant; the rest remain pending.",'',
        'A checked box means the linked evidence qualifies the stated fixture variant. It does not close other content, class, map, permission, persistence or failure variants. Opening a panel qualifies only opening that panel.','',data['scope'],'',
        'New trials use code-controlled ordinary keyboard/mouse inputs under the current AGENTS.md. Screenshots and normal addon-visible state are retained. Historical Laya receipts preserve their actual identities. Fixture setup, cleanup and outcome checks are recorded separately. Input, observer and protocol failures have distinct evidence.','',
        'Each successful mutation needs its native or local saved-state oracle and cleanup. Variants include class, race, faction, account versus character, solo versus group, combat versus idle, dead versus alive, zones, permissions and failure paths. Content IDs come from the existing content census.','']
    for family in data['families']:
        rows=[c for c in data['cases'] if c['family']==family]
        lines.extend(['## '+family.replace('_',' '),'','Fixture: `'+rows[0]['fixture']+'`.',''])
        for case in rows:
            key=case.get('qualification')
            lines.append('- ['+('x' if key else ' ')+'] `'+case['id']+'`'+(' (qualified variant; [evidence](#'+key+'))' if key else ''))
        lines.append('')
    lines.extend(['## Installed bindings','',
        'Run `pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_inventory capture-bindings --output <owned-evidence-directory>`. This reads all binding names, categories and current keys from build 60895. Every command is an additional parametrized test contract; headers are classified rather than counted as actions. The generated catalog and screenshots belong in DVC.',''])
    lines.extend(render_evidence(data.get('qualification_records',[])))
    return '\n'.join(lines)


def capture_bindings(output):
    from PIL import Image
    from tools.second_client import ctl
    ctl._launcher_env=lab.client_environment
    output.mkdir(parents=True,exist_ok=True);io=owned_input.Inputs();rows=[]
    def command(text):io.key('Return');io.type(text);io.key('Return');time.sleep(.65)
    try:
        page=1;total=None
        while total is None or page<=math.ceil(total/12):
            command('/tcui bindings '+str(page));path=output/f'bindings_{page:02}.png';ctl.shot(str(path))
            state=decode_image(Image.open(path));total=state['binding_count']
            expected_guid=f"Player-1-{actors.load()['guid']:08X}"
            if state['build']!=60895 or state['page']!=page or state['guid']!=expected_guid:
                raise RuntimeError('binding observation identity mismatch')
            rows.extend(state['rows']);(output/f'bindings_{page:02}.json').write_text(json.dumps(state))
            print(json.dumps({'page':page,'rows':len(rows)}),flush=True);page+=1
        if len(rows)!=total or [r['i'] for r in rows]!=list(range(1,total+1)):
            raise RuntimeError('incomplete binding catalog')
        result={'schema':'client442_live_bindings_v1','build':60895,'guid':state['guid'],'captured_at':time.time(),'rows':rows}
        (output/'binding_catalog.json').write_text(json.dumps(result,indent=2)+'\n')
    finally:command('/tcui state')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['write','capture-bindings'])
    p.add_argument('--output',type=__import__('pathlib').Path)
    args=p.parse_args()
    if args.action=='write':
        data=checklist();MANIFEST.write_text(json.dumps(data,indent=2)+'\n')
        (lab.REPO/'docs/client_harness/interaction_checklist_442.md').write_text(render(data))
        print(json.dumps({'cases':len(data['cases']),'families':data['families']}))
    else:
        if not args.output:p.error('--output is required')
        capture_bindings(args.output)


if __name__=='__main__':main()
