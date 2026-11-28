import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from nexion.adaptive import AdaptiveEngine, Policy, HealthMonitor
from nexion.checkpoint import save_checkpoint, load_checkpoint


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'state.json'
        self.policy = Policy(window=3, min_samples=2)
        self.engine = AdaptiveEngine(self.policy)
        self.health = HealthMonitor(2)

    def save(self):
        save_checkpoint(self.path, self.engine, self.health, scope='app/model')

    def load(self, **kwargs):
        return load_checkpoint(self.path, policy=self.policy, limit=2,
                               scope='app/model', **kwargs)

    def test_roundtrip_window_and_open_circuit(self):
        for i in range(10):
            self.engine.observe(i, 0.8, 0.1)
        self.health.record(False)
        self.health.record(False)
        self.save()
        e, h = self.load()
        self.assertEqual(e.assess(), self.engine.assess())
        self.assertFalse(e.assess()['automatic_activation'])
        self.assertEqual(h.record(True), self.health.status())
        with self.assertRaises(ValueError):
            e.observe(9, 0, 0)
        e.observe(10, 0, 0)

    def test_reset_keeps_watermark(self):
        self.engine.observe(50, 0, 0)
        self.engine.reset()
        self.save()
        e, _ = self.load()
        self.assertEqual(e.assess()['samples'], 0)
        with self.assertRaises(ValueError):
            e.observe(50, 0, 0)
        e.observe(51, 0, 0)

    def test_scope_policy_and_rollback_guard(self):
        self.save()
        for kwargs in ({'scope': 'other'}, {'limit': 3}, {'policy': Policy()}):
            options = dict(scope='app/model', limit=2, policy=self.policy)
            options.update(kwargs)
            with self.assertRaises(ValueError):
                load_checkpoint(self.path, **options)
        with self.assertRaises(ValueError):
            self.load(min_sequence=0)

    def test_corrupt_or_oversized_file(self):
        self.save()
        original = self.path.read_bytes()
        for data in (original[:-1], b'{}', b'\xff', b'x' * (1024*1024+1)):
            self.path.write_bytes(data)
            with self.assertRaises(ValueError):
                self.load()
        obj = json.loads(original)
        obj['state']['health']['open'] = True
        self.path.write_text(json.dumps(obj))
        with self.assertRaises(ValueError):
            self.load()

    def test_failed_replace_keeps_previous_checkpoint(self):
        self.save()
        original = self.path.read_bytes()
        self.engine.observe(0, 0, 0)
        with patch('nexion.checkpoint.os.replace', side_effect=OSError('injected')):
            with self.assertRaises(OSError):
                self.save()
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_missing_file_is_not_silent_reset(self):
        with self.assertRaises(FileNotFoundError):
            self.load()
