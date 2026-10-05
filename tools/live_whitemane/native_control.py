"""An isolated build of the owned libei sender with WoW side-button support."""
from tools.client_compatibility.native_input import control
from . import runtime


def configure():
    control.SOURCE = runtime.REPO / 'tools/live_whitemane/native_input'
    control.BUILD = runtime.ROOT / 'build/native_input'
    control.BINARY = control.BUILD / 'client442_input'
    control.RECEIPT = control.BUILD / 'build_receipt.json'
    return control


def verified():
    return configure().verified()


if __name__ == '__main__':
    configure().build()
