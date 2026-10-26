"""Root selection persistence and cross-tab guards; isolated files, no services."""
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

sys.dont_write_bytecode = True
PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
spec = importlib.util.spec_from_file_location('basketball_root_switch_tests', PROJECT / 'token_viewer.py')
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


class RootSwitchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='basketball-root-switch-')
        self.base = Path(self.temporary.name)
        self.first, self.second = self.base / 'first data', self.base / 'second data'
        self.raw = b'{"review":[{"question":"original question","answer":"original answer"}]}'
        for root in [self.first, self.second]:
            folder = root / 'C001'
            folder.mkdir(parents=True)
            (folder / 'qa.json').write_bytes(self.raw)
            (folder / 'original.mp4').write_bytes(b'catalog and prepare fixture')
            (folder / 'action_boxes.jpg').write_bytes(b'image fixture')
        self.config = self.base / 'custom.settings.json'
        self.settings = {'data_root': str(self.first), 'port': 5098, 'host': '127.0.0.1',
                         'ffmpeg': 'preserve-ffmpeg', 'cache_dir': 'preserve-cache',
                         'backups_dir': 'preserve-backups', 'other': {'custom': True}}
        self.original_config = json.dumps(self.settings, indent=2).encode('utf-8')
        self.config.write_bytes(self.original_config)
        values = {'ROOT': self.first, 'CONFIG_FILE': self.config, 'ROOT_SWITCHED': False,
                  'catalog': [], 'catalog_at': 0, 'catalog_root': None,
                  'BACKUPS': self.base / 'backups', 'CACHE': self.base / 'cache'}
        self.patches = [patch.object(backend, name, value) for name, value in values.items()]
        for item in self.patches:
            item.start()
        self.first_id = backend.root_identifier()
        self.first_rows = backend.videos()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temporary.cleanup()

    def request(self, root, **overrides):
        return {'data_root': str(root), 'root_id': backend.root_identifier(), **overrides}

    def snapshot(self):
        return backend.ROOT, backend.ROOT_SWITCHED, backend.catalog, backend.catalog_at, backend.catalog_root, self.config.read_bytes()

    def get(self, path):
        captured = {}
        handler = object.__new__(backend.Handler)
        handler.path = path
        handler.reply = lambda data, content=None, status=200: captured.update(data=data, status=status)
        handler.stream = lambda path: captured.update(data={'stream': str(path)}, status=200)
        handler.do_GET()
        return captured

    def post(self, path, payload, token=None):
        captured = {}
        raw = json.dumps(payload).encode()
        handler = object.__new__(backend.Handler)
        handler.path = path
        handler.headers = {'Content-Type': 'application/json', 'Content-Length': str(len(raw)),
                           'X-Viewer-Token': backend.CSRF if token is None else token}
        handler.rfile = io.BytesIO(raw)
        handler.connection = types.SimpleNamespace(settimeout=lambda value: None)
        handler.reply = lambda data, content=None, status=200: captured.update(data=data, status=status)
        handler.do_POST()
        return captured

    def test_switch_scans_every_round_and_only_changes_data_root_setting(self):
        for number in range(2, 206):
            folder = self.second / 'batch' / f'C{number:03}'
            folder.mkdir(parents=True)
            (folder / 'original.mp4').write_bytes(b'fixture')
        result = backend.switch_root(self.request(self.second))
        self.assertEqual(len(result['videos']), 205)
        self.assertEqual(result['data_root'], str(self.second))
        self.assertEqual(result['root_id'], backend.root_identifier(self.second))
        self.assertTrue(result['persisted'])
        expected = dict(self.settings, data_root=str(self.second))
        self.assertEqual(json.loads(self.config.read_text()), expected)
        self.assertEqual(backend.videos(), result['videos'])
        self.assertTrue(backend.ROOT_SWITCHED)
        self.assertEqual((self.first / 'C001' / 'qa.json').read_bytes(), self.raw)

    def test_empty_existing_directory_is_allowed(self):
        empty = self.base / 'empty'
        empty.mkdir()
        result = backend.switch_root(self.request(empty))
        self.assertEqual(result['videos'], [])
        self.assertEqual(backend.ROOT, empty)

    def test_rejects_missing_relative_or_file_candidates_before_state_changes(self):
        for candidate in [self.base / 'missing', Path('relative-data'), self.first / 'C001' / 'qa.json']:
            with self.subTest(candidate=candidate):
                before = self.snapshot()
                with self.assertRaises((ValueError, OSError)):
                    backend.switch_root(self.request(candidate))
                self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.base / 'missing').exists())

    def test_missing_or_stale_root_id_is_rejected(self):
        for payload in [{'data_root': str(self.second)}, self.request(self.second, root_id='stale')]:
            before = self.snapshot()
            with self.assertRaises(backend.Conflict):
                backend.switch_root(payload)
            self.assertEqual(self.snapshot(), before)

    def test_scan_failure_leaves_root_cache_and_config_unchanged(self):
        before = self.snapshot()
        with patch.object(backend, 'scan_videos', side_effect=PermissionError('fixture unreadable root')):
            with self.assertRaises(PermissionError):
                backend.switch_root(self.request(self.second))
        self.assertEqual(self.snapshot(), before)

    def test_candidate_removed_after_scan_does_not_replace_current_root(self):
        empty = self.base / 'temporary-candidate'
        empty.mkdir()
        before = self.snapshot()
        original_scan = backend.scan_videos
        def scan(root):
            result = original_scan(root)
            root.rmdir()
            return result
        with patch.object(backend, 'scan_videos', side_effect=scan):
            with self.assertRaises(ValueError):
                backend.switch_root(self.request(empty))
        self.assertEqual(self.snapshot(), before)

    def test_config_replace_failure_leaves_root_cache_and_config_unchanged(self):
        before = self.snapshot()
        with patch.object(backend.os, 'replace', side_effect=PermissionError('fixture read-only config')):
            with self.assertRaises(PermissionError):
                backend.switch_root(self.request(self.second))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(list(self.base.glob('.viewer-config-*.tmp')), [])

    def test_config_flush_failure_leaves_root_cache_and_config_unchanged(self):
        before = self.snapshot()
        with patch.object(backend.os, 'fsync', side_effect=OSError('fixture flush failure')):
            with self.assertRaises(OSError):
                backend.switch_root(self.request(self.second))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(list(self.base.glob('.viewer-config-*.tmp')), [])

    def test_invalid_config_is_not_overwritten(self):
        self.config.write_text('[]', encoding='utf-8')
        before = self.snapshot()
        with self.assertRaises(ValueError):
            backend.switch_root(self.request(self.second))
        self.assertEqual(self.snapshot(), before)

    def test_switch_during_candidate_scan_rejects_first_request(self):
        third = self.base / 'third'
        third.mkdir()
        original_scan = backend.scan_videos
        def scan(root):
            if root == self.second:
                backend.switch_root(self.request(third))
            return original_scan(root)
        with patch.object(backend, 'scan_videos', side_effect=scan):
            with self.assertRaises(backend.Conflict):
                backend.switch_root(self.request(self.second))
        self.assertEqual(backend.ROOT, third)
        self.assertEqual(json.loads(self.config.read_text())['data_root'], str(third))

    def test_same_root_keeps_legacy_write_compatibility(self):
        backend.switch_root(self.request(self.first))
        self.assertFalse(backend.ROOT_SWITCHED)
        candidate = backend.read_json('C001/qa.json')
        candidate.pop('root_id')
        self.assertTrue(backend.save_json(candidate)['skipped'])

    def test_old_tab_cannot_save_into_different_root_with_identical_qa_hash(self):
        old = backend.read_json('C001/qa.json')
        old['text'] = '{"review":[{"answer":"edited in old tab"}]}'
        backend.switch_root(self.request(self.second))
        self.assertEqual(backend.read_json('C001/qa.json')['version'], old['version'])
        with self.assertRaises(backend.Conflict):
            backend.save_json(old)
        self.assertFalse((self.second / 'C001' / 'qa-new.json').exists())

    def test_legacy_save_and_cleanup_missing_root_id_rejected_after_switch(self):
        for root in [self.first, self.second]:
            (root / 'C001' / 'qa-new.json').write_bytes(self.raw)
        old = backend.read_json('C001/qa.json')
        old.pop('root_id')
        backend.switch_root(self.request(self.second))
        with self.assertRaises(backend.Conflict):
            backend.save_json(old)
        with self.assertRaises(backend.Conflict):
            backend.cleanup_json(dict(old, confirm_delete=True))
        self.assertTrue((self.second / 'C001' / 'qa-new.json').exists())

    def test_fresh_document_can_save_and_cleanup_after_switch(self):
        backend.switch_root(self.request(self.second))
        fresh = backend.read_json('C001/qa.json')
        self.assertEqual(fresh['root_id'], backend.root_identifier())
        saved = backend.save_json(dict(fresh, text='{"review":[{"answer":"new root edit"}]}'))
        self.assertTrue(saved['written'])
        self.assertTrue((self.second / 'C001' / 'qa-new.json').exists())
        cleaned = backend.cleanup_json(dict(saved, confirm_delete=True, discard_saved_changes=True))
        self.assertTrue(cleaned['deleted'])
        self.assertFalse((self.second / 'C001' / 'qa-new.json').exists())

    def test_root_get_and_health_return_current_consistent_state(self):
        result = self.get('/api/root?refresh=1')
        self.assertEqual(result['status'], 200)
        self.assertEqual(result['data']['data_root'], str(self.first))
        self.assertEqual(result['data']['root_id'], self.first_id)
        self.assertEqual(result['data']['videos'], self.first_rows)
        health = self.get('/api/health')['data']
        self.assertEqual(health['root_id'], self.first_id)
        self.assertEqual(health['videos'], 1)

    def test_root_post_requires_page_token(self):
        result = self.post('/api/root', self.request(self.second), token='wrong-token')
        self.assertEqual(result['status'], 403)
        self.assertEqual(backend.ROOT, self.first)
        result = self.post('/api/root', self.request(self.second))
        self.assertEqual(result['status'], 200)
        self.assertEqual(result['data']['videos'], backend.videos())

    def test_protected_reads_reject_stale_root_id(self):
        backend.switch_root(self.request(self.second))
        for endpoint, path in [('/api/assets', 'C001/original.mp4'),
                               ('/api/references', 'C001/original.mp4'),
                               ('/api/json', 'C001/qa.json'),
                               ('/api/prepare', 'C001/original.mp4'),
                               ('/image', 'C001/action_boxes.jpg'),
                               ('/video', 'C001/original.mp4')]:
            with self.subTest(endpoint=endpoint):
                result = self.get(endpoint + '?path=' + path + '&root_id=' + self.first_id)
                self.assertEqual(result['status'], 409)
        result = self.get('/cached?file=' + '0' * 64 + '.mp4&root_id=' + self.first_id)
        self.assertEqual(result['status'], 409)
        self.assertEqual(self.get('/api/json?path=C001/qa.json')['status'], 200)

    def test_prepared_video_url_carries_current_root_id(self):
        result = self.get('/api/prepare?path=C001/original.mp4&root_id=' + self.first_id)
        self.assertEqual(result['status'], 200)
        query = parse_qs(urlsplit(result['data']['url']).query)
        self.assertEqual(query['root_id'], [self.first_id])

    def test_long_prepare_does_not_hold_save_lock_and_rejects_midflight_switch(self):
        def prepare(relative, root=None):
            self.assertEqual(root, self.first)
            self.assertTrue(backend.SAVE_LOCK.acquire(blocking=False))
            backend.SAVE_LOCK.release()
            backend.switch_root(self.request(self.second))
            return '/video?path=C001/original.mp4'
        with patch.object(backend, 'prepare', side_effect=prepare):
            result = self.get('/api/prepare?path=C001/original.mp4&root_id=' + self.first_id)
        self.assertEqual(result['status'], 409)

    def test_configure_remembers_the_actual_custom_config_for_persistence(self):
        extra_patches = [patch.object(backend, name, getattr(backend, name))
                         for name in ['FFMPEG', 'HOST', 'PORT']]
        for item in extra_patches:
            item.start()
        clean_environment = {k: v for k, v in os.environ.items() if not k.startswith('COURTCRAFT_')}
        try:
            with patch.dict(backend.os.environ, clean_environment, clear=True):
                backend.configure(self.config)
            self.assertEqual(backend.CONFIG_FILE, self.config)
            backend.switch_root(self.request(self.second))
            self.assertEqual(json.loads(self.config.read_text())['data_root'], str(self.second))
        finally:
            for item in reversed(extra_patches):
                item.stop()


if __name__ == '__main__':
    unittest.main()
