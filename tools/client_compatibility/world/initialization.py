"""Translate native character capabilities, without inventing learned abilities."""
from .buffer import Reader, Writer


def known_spells(body):
    r = Reader(body)
    initial, count = r.unpack("BH")
    if initial > 1 or count > 16000:
        raise ValueError("invalid native spell list")
    spells = [r.unpack("Ih")[0] for _ in range(count)]
    cooldowns, = r.unpack("H")
    history = [r.unpack("IIHii") for _ in range(cooldowns)]
    r.end()
    if history:
        raise ValueError("native initial cooldown translation is not implemented")
    return Writer().bits(initial, 1).pack("II", count, 0).pack("I" * count, *spells).finish()


def action_buttons(body):
    if len(body) != 144 * 4 + 1 or body[-1] > 2:
        raise ValueError("invalid native action buttons")
    r = Reader(body)
    buttons = list(r.unpack("I" * 144)) + [0] * 36
    return Writer().pack("Q" * 180, *buttons).pack("B", r.unpack("B")[0]).finish()


def proficiency(body):
    r = Reader(body)
    kind, mask = r.unpack("BI")
    r.end()
    return Writer().pack("IB", mask, kind).finish()


def translate(name, body):
    if name == "SMSG_SEND_KNOWN_SPELLS": return known_spells(body)
    if name == "SMSG_UPDATE_ACTION_BUTTONS": return action_buttons(body)
    if name == "SMSG_SET_PROFICIENCY": return proficiency(body)
    if name == "SMSG_SEND_UNLEARN_SPELLS":
        r = Reader(body)
        count, = r.unpack("I")
        if count > 16000: raise ValueError("invalid unlearned spell count")
        r.raw(count * 4); r.end()
        return body
    return None
