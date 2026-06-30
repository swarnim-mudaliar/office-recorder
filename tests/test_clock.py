from recorder.clock import is_synced
class _R:
    def __init__(self, o): self.stdout = o
def test_yes(): assert is_synced(runner=lambda *a, **k: _R("yes\n")) is True
def test_no():  assert is_synced(runner=lambda *a, **k: _R("no\n")) is False
