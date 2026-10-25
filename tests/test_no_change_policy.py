#!/usr/bin/env python3
"""No-change save and explicit cleanup tests. Temporary fixtures only; no servers."""
import hashlib
import importlib.util
import io
import json
import errno
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
spec = importlib.util.spec_from_file_location('basketball_no_change_backend', PROJECT / 'token_viewer.py')
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


class NoChangePolicyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='basketball-no-change-')
        self.root = Path(self.temporary.name) / 'data'
        self.root.mkdir()
        self.original_root, self.original_backups = backend.ROOT, backend.BACKUPS
        backend.ROOT = self.root
        backend.BACKUPS = Path(self.temporary.name) / 'backups'
        self.folder = self.root / 'C251'
        self.folder.mkdir()
        self.source = self.folder / 'qa.json'
        self.target = self.folder / 'qa-new.json'
        self.raw_source = b'{\r\n  "prediction": [], "review": [{"answer": "original"}], "count": 1\r\n}'
        self.source.write_bytes(self.raw_source)

    def tearDown(self):
        backend.ROOT, backend.BACKUPS = self.original_root, self.original_backups
        self.temporary.cleanup()

    def document(self, filename='qa.json'):
        return backend.read_json('C251/' + filename)

    def source_candidate(self):
        return '{"count":1.0,"review":[{"answer":"original"}],"prediction":[]}'

    def cleanup_request(self, doc=None, **overrides):
        request = dict(doc or self.document())
        request.update(confirm_delete=True)
        request.update(overrides)
        return request

    def backup_files(self):
        return list(backend.BACKUPS.rglob('*.bak')) if backend.BACKUPS.exists() else []

    def post(self, endpoint, payload, *, token=None):
        raw = json.dumps(payload).encode('utf-8')
        handler = object.__new__(backend.Handler)
        handler.path = endpoint
        handler.headers = {'Content-Type': 'application/json', 'Content-Length': str(len(raw)),
                           'X-Viewer-Token': backend.CSRF if token is None else token}
        handler.rfile = io.BytesIO(raw)
        handler.connection = types.SimpleNamespace(settimeout=lambda value: None)
        captured = {}
        handler.reply = lambda data, **kwargs: captured.update(data=data, status=kwargs.get('status', 200))
        handler.do_POST()
        return captured['status'], captured['data']

    def test_unchanged_candidate_does_not_create_a_new_file(self):
        doc = self.document()
        result = backend.save_json(dict(doc, text=self.source_candidate()))
        self.assertTrue(result['skipped'])
        self.assertFalse(result['written'])
        self.assertTrue(result['unchanged'])
        self.assertFalse(result['cleanup_required'])
        self.assertFalse(result['target_exists'])
        self.assertIsNone(result['save_version'])
        self.assertIsNone(result['saved_text'])
        self.assertEqual(result['path'], 'C251/qa.json')
        self.assertEqual(result['version'], hashlib.sha256(self.raw_source).hexdigest())
        self.assertEqual(result['text'].encode(), self.raw_source)
        self.assertFalse(self.target.exists())
        self.assertEqual(self.source.read_bytes(), self.raw_source)
        self.assertEqual(self.backup_files(), [])

    def test_semantic_comparison_is_typed_order_independent_and_numeric(self):
        equivalent = backend.json_semantically_equal
        self.assertTrue(equivalent('{"a":1,"b":[1.0,null]}', '{"b":[1,null],"a":1.00}'))
        self.assertTrue(equivalent('1e999', '10e998'))
        self.assertFalse(equivalent('1e999', '2e999'))
        self.assertFalse(equivalent('true', '1'))
        self.assertFalse(equivalent('[false]', '[0]'))
        self.assertFalse(equivalent('{"x":true}', '{"x":1.0}'))
        self.assertFalse(equivalent('"1"', '1'))
        self.assertFalse(equivalent('[1,2]', '[2,1]'))
        self.assertFalse(equivalent('{broken}', '{}'))

    def test_boolean_numeric_change_is_a_real_save(self):
        self.source.write_text('{"answer":true}')
        result = backend.save_json(dict(self.document(), text='{"answer":1}'))
        self.assertFalse(result['skipped'])
        self.assertTrue(result['written'])
        self.assertEqual(self.target.read_text(), '{"answer":1}')
        self.assertEqual(self.source.read_text(), '{"answer":true}')

    def test_equivalent_existing_target_requires_explicit_confirmation(self):
        saved_raw = self.source_candidate().encode()
        self.target.write_bytes(saved_raw)
        doc = self.document('qa-new.json')
        self.assertTrue(doc['saved_matches_source'])
        self.assertTrue(doc['cleanup_required'])
        self.assertFalse(doc['cleanup_requires_discard'])
        result = backend.save_json(dict(doc, text=self.source_candidate()))
        self.assertTrue(result['skipped'])
        self.assertTrue(result['cleanup_required'])
        self.assertEqual(self.target.read_bytes(), saved_raw)
        for confirmation in (False, None, 'true', 1):
            with self.assertRaises(ValueError):
                backend.cleanup_json(self.cleanup_request(result, confirm_delete=confirmation))
        self.assertTrue(self.target.exists())
        self.assertEqual(self.backup_files(), [])
        cleaned = backend.cleanup_json(self.cleanup_request(result))
        self.assertTrue(cleaned['deleted'])
        self.assertFalse(cleaned['discarded_saved_changes'])
        self.assertEqual(Path(cleaned['backup']).read_bytes(), saved_raw)
        self.assertFalse(self.target.exists())
        self.assertEqual(self.source.read_bytes(), self.raw_source)
        self.assertEqual(cleaned['path'], 'C251/qa.json')
        self.assertEqual(cleaned['text'].encode(), self.raw_source)
        self.assertEqual(cleaned['version'], hashlib.sha256(self.raw_source).hexdigest())
        self.assertIsNone(cleaned['save_version'])
        self.assertIsNone(cleaned['saved_text'])
        self.assertFalse(cleaned['cleanup_required'])

    def test_restoring_source_candidate_preserves_different_saved_changes(self):
        different = '{"review":[{"answer":"saved changes"}]}'
        self.target.write_text(different)
        doc = self.document('qa-new.json')
        self.assertFalse(doc['saved_matches_source'])
        self.assertFalse(doc['cleanup_required'])  # No entry-time redundancy prompt.
        skipped = backend.save_json(dict(doc, text=self.source_candidate()))
        self.assertTrue(skipped['skipped'])
        self.assertTrue(skipped['cleanup_required'])  # Candidate now equals source.
        self.assertTrue(skipped['cleanup_requires_discard'])
        self.assertFalse(skipped['saved_matches_source'])
        self.assertEqual(skipped['saved_text'], different)
        self.assertEqual(self.target.read_text(), different)
        self.assertEqual(skipped['save_version'], hashlib.sha256(different.encode()).hexdigest())
        with self.assertRaises(backend.Conflict):
            backend.cleanup_json(self.cleanup_request(skipped))
        with self.assertRaises(backend.Conflict):
            backend.cleanup_json(self.cleanup_request(skipped, discard_saved_changes=1))
        self.assertEqual(self.target.read_text(), different)
        self.assertEqual(self.backup_files(), [])

    def test_explicit_discard_backs_up_different_target_before_removing(self):
        raw = b'{"answer":"saved changes"}'
        self.target.write_bytes(raw)
        cleaned = backend.cleanup_json(self.cleanup_request(discard_saved_changes=True))
        self.assertTrue(cleaned['deleted'])
        self.assertTrue(cleaned['discarded_saved_changes'])
        self.assertEqual(Path(cleaned['backup']).read_bytes(), raw)
        self.assertEqual(self.source.read_bytes(), self.raw_source)
        self.assertFalse(self.target.exists())

    def test_source_changed_after_prompt_prevents_deletion(self):
        self.target.write_text(self.source_candidate())
        request = self.cleanup_request()
        self.source.write_text('{"external":true}')
        with self.assertRaises(backend.Conflict):
            backend.cleanup_json(request)
        self.assertTrue(self.target.exists())
        self.assertEqual(self.backup_files(), [])

    def test_target_changed_after_prompt_prevents_deletion(self):
        self.target.write_text(self.source_candidate())
        request = self.cleanup_request()
        self.target.write_text('{"external":true}')
        with self.assertRaises(backend.Conflict):
            backend.cleanup_json(request)
        self.assertEqual(self.target.read_text(), '{"external":true}')
        self.assertEqual(self.backup_files(), [])

    def test_source_disappearing_after_prompt_is_a_conflict(self):
        self.target.write_text(self.source_candidate())
        request = self.cleanup_request()
        self.source.unlink()
        with self.assertRaises(backend.Conflict):
            backend.cleanup_json(request)
        self.assertTrue(self.target.exists())
        self.assertEqual(self.backup_files(), [])

    def test_target_disappearing_after_prompt_is_a_conflict(self):
        self.target.write_text(self.source_candidate())
        request = self.cleanup_request(self.document('qa-new.json'))
        self.target.unlink()
        with self.assertRaises(backend.Conflict):
            backend.cleanup_json(request)
        self.assertEqual(self.source.read_bytes(), self.raw_source)

    def test_changes_during_backup_are_not_deleted(self):
        for changed_file in (self.source, self.target):
            with self.subTest(changed_file=changed_file.name):
                self.source.write_bytes(self.raw_source)
                self.target.write_text(self.source_candidate())
                request = self.cleanup_request()
                real_backup = backend.backup_json
                def backup_and_modify(path, raw):
                    backup = real_backup(path, raw)
                    changed_file.write_text('{"external during backup":true}')
                    return backup
                with patch.object(backend, 'backup_json', side_effect=backup_and_modify):
                    with self.assertRaises(backend.Conflict):
                        backend.cleanup_json(request)
                self.assertTrue(self.target.exists())
                self.assertTrue(self.backup_files())

    def test_target_replaced_immediately_before_isolation_is_preserved(self):
        self.target.write_text(self.source_candidate())
        request = self.cleanup_request()
        real_replace = backend.os.replace
        def replace_after_external_edit(source, destination):
            if Path(source) == self.target:
                self.target.write_text('{"late external edit":true}')
            return real_replace(source, destination)
        with patch.object(backend.os, 'replace', side_effect=replace_after_external_edit):
            with self.assertRaises(backend.Conflict):
                backend.cleanup_json(request)
        self.assertEqual(self.target.read_text(), '{"late external edit":true}')
        self.assertEqual(self.source.read_bytes(), self.raw_source)

    def test_new_target_during_final_archive_is_not_overwritten(self):
        self.target.write_text(self.source_candidate())
        request = self.cleanup_request()
        captured = self.target.read_bytes()
        real_replace = backend.os.replace
        def replace_and_recreate_target(source, destination):
            if Path(source).name.startswith('.viewer-cleanup-'):
                self.target.write_text('{"newly recreated target":true}')
            return real_replace(source, destination)
        with patch.object(backend.os, 'replace', side_effect=replace_and_recreate_target):
            with self.assertRaises(backend.Conflict):
                backend.cleanup_json(request)
        self.assertEqual(self.target.read_text(), '{"newly recreated target":true}')
        self.assertTrue(any(p.read_bytes() == captured for p in self.backup_files()))

    def test_last_snapshot_race_preserves_new_target(self):
        self.target.write_text(self.source_candidate())
        request = self.cleanup_request()
        original_output_path = backend.output_path
        calls = 0
        def output_path_and_edit(source):
            nonlocal calls
            calls += 1
            if calls == 2:
                self.target.write_text('{"after last version check":true}')
            return original_output_path(source)
        with patch.object(backend, 'output_path', side_effect=output_path_and_edit):
            with self.assertRaises(backend.Conflict):
                backend.cleanup_json(request)
        self.assertEqual(self.target.read_text(), '{"after last version check":true}')
        self.assertEqual(self.source.read_bytes(), self.raw_source)

    def test_backup_sync_failure_restores_target(self):
        self.target.write_text(self.source_candidate())
        request = self.cleanup_request()
        captured = self.target.read_bytes()
        with patch.object(backend.os, 'fsync', side_effect=OSError('fixture sync failure')):
            with self.assertRaises(OSError):
                backend.cleanup_json(request)
        self.assertEqual(self.target.read_bytes(), captured)
        self.assertEqual(self.source.read_bytes(), self.raw_source)

    def test_cross_volume_archive_keeps_authoritative_recovery_file(self):
        self.target.write_text(self.source_candidate())
        request = self.cleanup_request()
        captured = self.target.read_bytes()
        real_replace = backend.os.replace
        def replace_with_cross_volume_archive(source, destination):
            if Path(source).name.startswith('.viewer-cleanup-'):
                raise OSError(errno.EXDEV, 'fixture cross-device archive')
            return real_replace(source, destination)
        with patch.object(backend.os, 'replace', side_effect=replace_with_cross_volume_archive):
            result = backend.cleanup_json(request)
        self.assertTrue(result['deleted'])
        self.assertFalse(self.target.exists())
        self.assertEqual(Path(result['backup']).parent, self.folder)
        self.assertEqual(Path(result['backup']).read_bytes(), captured)
        self.assertEqual(Path(result['backup_copy']).read_bytes(), captured)

    def test_final_archive_sync_failure_restores_target(self):
        self.target.write_text(self.source_candidate())
        request = self.cleanup_request()
        captured = self.target.read_bytes()
        real_sync = backend.os.fsync
        calls = 0
        def fail_second_sync(descriptor):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('fixture final archive sync failure')
            return real_sync(descriptor)
        with patch.object(backend.os, 'fsync', side_effect=fail_second_sync):
            with self.assertRaises(OSError):
                backend.cleanup_json(request)
        self.assertEqual(self.target.read_bytes(), captured)
        self.assertEqual(self.source.read_bytes(), self.raw_source)

    def test_no_source_cannot_be_cleaned(self):
        self.source.unlink()
        self.target.write_text('{"orphan":true}')
        doc = self.document('qa-new.json')
        self.assertFalse(doc['source_available'])
        self.assertFalse(doc['cleanup_required'])
        with self.assertRaises(ValueError):
            backend.cleanup_json(self.cleanup_request(doc, discard_saved_changes=True))
        self.assertEqual(self.target.read_text(), '{"orphan":true}')
        self.assertFalse(self.source.exists())

    def test_original_path_cannot_be_substituted_as_cleanup_target(self):
        self.target.write_text(self.source_candidate())
        request = self.cleanup_request(immutable_source_path='C251/qa-new.json')
        with self.assertRaises(ValueError):
            backend.cleanup_json(request)
        with self.assertRaises(ValueError):
            backend.cleanup_json(self.cleanup_request(path='../outside.json'))
        self.assertEqual(self.source.read_bytes(), self.raw_source)
        self.assertTrue(self.target.exists())

    def test_normal_saves_and_conflicts_keep_legacy_fields(self):
        doc = self.document()
        saved = backend.save_json(dict(doc, text='{"answer":"changed"}'))
        for field in ('path', 'version', 'save_path', 'save_version', 'unchanged', 'backup'):
            self.assertIn(field, saved)
        self.assertEqual(saved['path'], 'C251/qa-new.json')
        self.assertFalse((self.folder / 'qa-new-new.json').exists())
        again = backend.save_json(dict(self.document('qa-new.json'), text='{"answer":"changed"}'))
        self.assertTrue(again['unchanged'])
        self.assertFalse(again['skipped'])
        self.assertFalse(again['written'])
        with self.assertRaises(backend.Conflict):
            backend.save_json(dict(doc, text='{"answer":"stale"}'))

    def test_cleanup_route_token_confirmation_and_conflict_status(self):
        self.target.write_text(self.source_candidate())
        request = self.cleanup_request()
        self.assertEqual(self.post('/api/json/cleanup', request, token='wrong-token')[0], 403)
        self.assertTrue(self.target.exists())
        self.assertEqual(self.post('/api/json/cleanup', dict(request, confirm_delete=False))[0], 400)
        self.target.write_text('{"external":true}')
        self.assertEqual(self.post('/api/json/cleanup', request)[0], 409)
        self.assertTrue(self.target.exists())
        status, result = self.post('/api/json/cleanup', self.cleanup_request(discard_saved_changes=True))
        self.assertEqual(status, 200)
        self.assertTrue(result['deleted'])
        self.assertFalse(self.target.exists())
        self.assertEqual(self.source.read_bytes(), self.raw_source)


if __name__ == '__main__':
    unittest.main(verbosity=2)
