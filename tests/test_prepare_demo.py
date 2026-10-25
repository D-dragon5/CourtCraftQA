#!/usr/bin/env python3
"""Disposable prepare_demo fixtures; no real datasets, services or network calls."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('basketball_prepare_demo_tests', PROJECT / 'scripts' / 'prepare_demo.py')
prepare_demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare_demo)


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


class PrepareDemoTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='basketball-prepare-demo-')
        self.root = Path(self.temporary.name)
        self.project = self.root / 'isolated project'
        self.project.mkdir()
        (self.project / 'config.json').write_text('{"ffmpeg":"fixture-ffmpeg"}', encoding='utf-8')
        self.project_patch = patch.object(prepare_demo, 'PROJECT', self.project)
        self.project_patch.start()
        self.source = self.root / 'source with spaces' / 'C251'
        self.source.mkdir(parents=True)
        self.destination = self.root / 'new demo output'
        self.config = self.root / 'new config folder' / 'demo.json'
        self.payload = {'prediction': [{'type': 'action', 'qa': [
            {'question': '选择哪个动作？\nA. 传球\nB. 投篮', 'answer': 'A. Source Answer'},
            {'question': '第二题', 'answer': 'Source second answer'}]}],
            'review': [{'question': '请复盘', 'answer': 'Source review answer'}]}
        self.original = b'\xef\xbb\xbf' + json.dumps(self.payload, ensure_ascii=False, indent=2).replace('\n', '\r\n').encode('utf-8')
        (self.source / 'qa.json').write_bytes(self.original)
        self.existing_new = b'{"review":[{"answer":"do not copy or change existing new"}]}'
        (self.source / 'qa-new.json').write_bytes(self.existing_new)
        self.media = {'original.mp4': b'fixture-video-no-playback',
                      'action_boxes.jpg': b'fixture-image-no-render',
                      'source_PL_label.xlsx': b'fixture-excel-copy-only'}
        for name, raw in self.media.items():
            (self.source / name).write_bytes(raw)
        (self.source / '~$source_PL_label.xlsx').write_bytes(b'Excel temporary lock')
        (self.source / '~$other.XLSX').write_bytes(b'another Excel temporary lock')
        (self.source / 'other.json').write_bytes(b'{"private":"not for demo"}')
        (self.source / 'notes.JSON').write_bytes(b'{"private":"also excluded"}')
        (self.source / 'notes.txt').write_bytes(b'non-media content excluded')
        nested = self.source / 'nested-not-a-round'
        nested.mkdir()
        (nested / 'private.json').write_bytes(b'{"nested":true}')
        (nested / 'nested.mp4').write_bytes(b'nested video excluded')

    def tearDown(self):
        self.project_patch.stop()
        self.temporary.cleanup()

    def prepare(self, **overrides):
        return prepare_demo.prepare(overrides.get('source', self.source),
                                    overrides.get('destination', self.destination),
                                    overrides.get('config', self.config))

    def assert_refused_before_writes(self, exception=(ValueError, OSError), **overrides):
        before = snapshot(self.root)
        with self.assertRaises(exception):
            self.prepare(**overrides)
        self.assertEqual(snapshot(self.root), before)
        destination = Path(overrides.get('destination', self.destination))
        config = Path(overrides.get('config', self.config))
        if not any(name == destination.relative_to(self.root).as_posix() or
                   name.startswith(destination.relative_to(self.root).as_posix() + '/') for name in before):
            self.assertFalse(destination.exists())
        self.assertFalse(config.exists())
        self.assertFalse(self.config.parent.exists())

    def test_four_rounds_preserve_source_and_exclude_non_demo_files(self):
        before = snapshot(self.source)
        result = self.prepare()
        expected = ['01-C251-edit', '02-C251-clean', '03-C251-duplicate', '04-C251-saved']
        self.assertEqual(result['rounds'], expected)
        self.assertEqual(sorted(p.name for p in self.destination.iterdir()), expected)
        self.assertTrue(result['source_untouched'])
        self.assertEqual(snapshot(self.source), before)
        self.assertEqual((self.source / 'qa-new.json').read_bytes(), self.existing_new)
        for round_name in expected:
            folder = self.destination / round_name
            self.assertEqual((folder / 'qa.json').read_bytes(), self.original)
            for name, raw in self.media.items():
                self.assertEqual((folder / name).read_bytes(), raw)
            allowed = {'qa.json', *self.media}
            if round_name.endswith(('duplicate', 'saved')):
                allowed.add('qa-new.json')
            self.assertEqual({p.name for p in folder.iterdir()}, allowed)
        for name in expected[:2]:
            self.assertFalse((self.destination / name / 'qa-new.json').exists())
        duplicate = self.destination / expected[2] / 'qa-new.json'
        self.assertEqual(json.loads(duplicate.read_text(encoding='utf-8')), self.payload)
        self.assertNotEqual(duplicate.read_bytes(), self.existing_new)
        self.assertNotEqual(duplicate.read_bytes(), self.original)
        saved = json.loads((self.destination / expected[3] / 'qa-new.json').read_text(encoding='utf-8'))
        intended = copy.deepcopy(self.payload)
        intended['prediction'][0]['qa'][0]['answer'] += '演示旧版修改'
        self.assertEqual(saved, intended)
        self.assertNotEqual(saved, json.loads(self.existing_new))
        config = json.loads(self.config.read_text(encoding='utf-8'))
        self.assertEqual(config['data_root'], str(self.destination.resolve()))
        self.assertEqual(config['ffmpeg'], 'fixture-ffmpeg')
        self.assertEqual(config['host'], '127.0.0.1')
        self.assertEqual(config['port'], 5016)
        self.assertEqual(config['cache_dir'], str(self.destination.parent / 'demo-cache'))
        self.assertEqual(config['backups_dir'], str(self.destination.parent / 'demo-backups'))
        self.assertFalse((self.destination.parent / 'demo-cache').exists())
        self.assertFalse((self.destination.parent / 'demo-backups').exists())

    def test_existing_output_directory_is_preserved(self):
        self.destination.mkdir()
        sentinel = self.destination / 'progress.json'
        sentinel.write_bytes(b'{"existing demo progress":true}')
        before = snapshot(self.root)
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(snapshot(self.root), before)
        self.assertFalse(self.config.parent.exists())

    def test_existing_output_file_is_preserved(self):
        self.destination.write_bytes(b'do not replace existing output file')
        before = snapshot(self.root)
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(snapshot(self.root), before)
        self.assertFalse(self.config.parent.exists())

    def test_existing_config_file_is_preserved(self):
        self.config.parent.mkdir()
        self.config.write_bytes(b'{"keep existing configuration":true}')
        before = snapshot(self.root)
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(snapshot(self.root), before)
        self.assertFalse(self.destination.exists())

    def test_output_inside_source_is_refused_before_creation(self):
        self.assert_refused_before_writes(destination=self.source / 'nested new demo')

    def test_output_containing_source_is_refused_without_touching_source(self):
        before = snapshot(self.root)
        with self.assertRaises(ValueError):
            self.prepare(destination=self.source.parent)
        self.assertEqual(snapshot(self.root), before)
        self.assertFalse(self.config.parent.exists())

    def test_output_equal_to_source_is_refused(self):
        before = snapshot(self.root)
        with self.assertRaises(ValueError):
            self.prepare(destination=self.source)
        self.assertEqual(snapshot(self.root), before)
        self.assertFalse(self.config.parent.exists())

    def test_config_inside_source_is_refused_before_any_copy(self):
        before = snapshot(self.root)
        source_config = self.source / 'new-demo-config.json'
        with self.assertRaises(ValueError):
            self.prepare(config=source_config)
        self.assertEqual(snapshot(self.root), before)
        self.assertFalse(self.destination.exists())
        self.assertFalse(source_config.exists())

    def test_missing_qa_is_rejected_before_output_or_config_parent_creation(self):
        (self.source / 'qa.json').unlink()
        self.assert_refused_before_writes(exception=(FileNotFoundError, ValueError))

    def test_missing_video_is_rejected_before_output_or_config_parent_creation(self):
        (self.source / 'original.mp4').unlink()
        self.assert_refused_before_writes(exception=ValueError)

    def test_missing_string_answer_is_rejected_before_output_creation(self):
        cases = [
            {'prediction': [], 'review': []},
            {'prediction': [{'qa': [{'answer': None}, {'answer': 1}, {'answer': True}]}], 'review': [{'answer': ['x']}]},
            {'prediction': [{'qa': [{'question': 'answer missing'}]}]},
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                (self.source / 'qa.json').write_text(json.dumps(payload), encoding='utf-8')
                self.assert_refused_before_writes(exception=ValueError)

    def test_invalid_json_is_rejected_before_output_creation(self):
        (self.source / 'qa.json').write_text('{invalid}', encoding='utf-8')
        self.assert_refused_before_writes(exception=ValueError)

    def test_source_without_directory_is_rejected_before_output_creation(self):
        self.assert_refused_before_writes(source=self.root / 'does-not-exist')

    def test_review_only_source_uses_its_first_string_answer(self):
        payload = {'prediction': [], 'review': [{'question': 'review-only', 'answer': 'review first'}]}
        raw = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        (self.source / 'qa.json').write_bytes(raw)
        before = snapshot(self.source)
        result = self.prepare()
        saved = json.loads((self.destination / result['rounds'][-1] / 'qa-new.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['review'][0]['answer'], 'review first演示旧版修改')
        self.assertEqual(snapshot(self.source), before)
        for folder in self.destination.iterdir():
            self.assertEqual((folder / 'qa.json').read_bytes(), raw)


if __name__ == '__main__':
    unittest.main(verbosity=2)
