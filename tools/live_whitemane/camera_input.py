"""Relative mouselook through the owned Whitemane sender only."""
import json
from tools.client_compatibility.native_input_adapter import Input as NativeInput


class Input(NativeInput):
    def relative(self, dx, dy=0):
        if not isinstance(dx, int) or not isinstance(dy, int) or max(abs(dx), abs(dy)) > 256:
            raise ValueError('relative mouselook requires bounded integer deltas')
        self.sender.stdin.write(json.dumps({'kind': 'relative', 'dx': dx, 'dy': dy}) + '\n')
        self.sender.stdin.flush()
        if self.reply().get('ok') is not True:
            raise RuntimeError('owned camera input was not acknowledged')
