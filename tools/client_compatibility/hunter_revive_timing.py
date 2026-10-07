"""Pure native Revive timing evidence with the conservative corpse deadline."""
from .world.native_objects import guid as native_guid
from .world.buffer import Reader


# Creature's default corpse delay is 60 seconds. Its expiry is set from integer
# GameTime seconds; reserve that first partial second. The clock is bound to
# ordinary CallPet chat setup BEFORE native handling, never packet receipt.
CORPSE_SECONDS = 59
MAX_SETUP_AGE = 25
MIN_SUBMISSION_REMAINING = 15  # 10-second Revive plus Return and scheduler margin.


def native_revive_timing(packets, request, lifetime_started_at):
    starts, completions = [], []
    for packet in packets:
        if packet.get('direction') != 'from_native' or packet.get('name') not in ('SMSG_SPELL_START', 'SMSG_SPELL_GO'):
            continue
        reader = Reader(bytes.fromhex(packet['body']))
        caster, unit = native_guid(reader), native_guid(reader)
        counter, spell = reader.unpack('Bi')
        if spell != 982 or counter != request['counter'] or caster != 6 or unit != 6: continue
        row = {'time': packet['time'], 'caster': caster, 'unit': unit, 'counter': counter, 'spell': spell}
        if packet['name'] == 'SMSG_SPELL_START':
            flags, flags_ex, cast_ms = reader.unpack('III')
            row.update(cast_time_ms=cast_ms, flags=flags, flags_ex=flags_ex)
            starts.append(row)
        else: completions.append(row)
    valid = len(starts) == len(completions) == 1
    result = {'starts': starts, 'completions': completions, 'one_matching_start_and_completion': valid}
    if valid:
        start, completion = starts[0], completions[0]
        result.update(actual_cast_seconds=completion['time'] - start['time'],
            native_start_remaining_seconds=lifetime_started_at + CORPSE_SECONDS - start['time'],
            completion_within_conservative_corpse_deadline=completion['time'] < lifetime_started_at + CORPSE_SECONDS,
            native_completion_ordered=completion['time'] >= start['time'],
            native_ten_second_cast=start['cast_time_ms'] == 10000)
    return result
