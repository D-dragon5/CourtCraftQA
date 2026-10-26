"""Unlimited recursive catalog and explicit refresh tests; disposable files only."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
spec = importlib.util.spec_from_file_location('basketball_catalog_tests', PROJECT / 'token_viewer.py')
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='basketball-catalog-')
        self.parent = Path(self.temporary.name)
        self.root = self.parent / 'data'
        self.root.mkdir()
        self.patches = [patch.object(backend, 'ROOT', self.root),
                        patch.object(backend, 'catalog', []),
                        patch.object(backend, 'catalog_at', 0),
                        patch.object(backend, 'catalog_root', None)]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temporary.cleanup()

    def video(self, relative, raw=b'catalog-only-not-playable'):
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        return target

    def get(self, path):
        handler = object.__new__(backend.Handler)
        handler.path = path
        captured = {}
        handler.reply = lambda data, content=None, status=200: captured.update(data=data, status=status)
        handler.do_GET()
        self.assertEqual(captured['status'], 200)
        return captured['data']

    def test_all_205_rounds_across_nested_groups_are_indexed(self):
        expected = set()
        for number in range(1, 206):
            group = f'C{((number - 1) // 50) * 50 + 1:03}-C{((number - 1) // 50 + 1) * 50:03}'
            relative = f'{group}/C{number:03}/original.mp4'
            self.video(relative)
            expected.add(relative)
        (self.root / 'empty-round').mkdir()
        (self.root / 'annotations-only').mkdir()
        (self.root / 'annotations-only' / 'qa.json').write_text('{}')
        rows = backend.videos()
        self.assertEqual(len(rows), 205)
        self.assertEqual({row['path'] for row in rows}, expected)
        self.assertEqual(len({row['path'].split('/')[0] for row in rows}), 5)
        self.assertTrue(all(row['bytes'] == len(b'catalog-only-not-playable') for row in rows))

    def test_refresh_immediately_reindexes_added_and_removed_files(self):
        first = self.video('C001/original.mp4')
        self.assertEqual(len(backend.videos()), 1)
        self.video('C002/original.mov')
        first.unlink()
        self.assertEqual([r['path'] for r in backend.videos()], ['C001/original.mp4'])
        self.assertEqual([r['path'] for r in backend.videos(refresh=True)], ['C002/original.mov'])

    def test_refresh_query_bypasses_cache(self):
        self.video('C001/original.mp4')
        self.assertEqual(len(self.get('/api/videos')), 1)
        self.video('C002/original.mp4')
        self.assertEqual(len(self.get('/api/videos?refresh=0')), 1)
        self.assertEqual(len(self.get('/api/videos?refresh=1')), 2)
        self.video('C003/original.mp4')
        self.assertEqual(len(self.get('/api/videos?refresh=true')), 3)

    def test_round_numbers_keep_natural_order(self):
        for number in [200, 10, 2, 1]:
            self.video(f'C{number}/original.mp4')
        self.assertEqual([row['path'] for row in backend.videos()],
                         ['C1/original.mp4', 'C2/original.mp4',
                          'C10/original.mp4', 'C200/original.mp4'])

    def test_expired_cache_reindexes_without_force(self):
        self.video('C001/original.mp4')
        backend.videos()
        self.video('C002/original.mp4')
        with patch.object(backend, 'catalog_at', backend.time.monotonic() - 16):
            self.assertEqual(len(backend.videos()), 2)

    def test_root_change_does_not_reuse_another_directory_catalog(self):
        self.video('C001/original.mp4')
        backend.videos()
        second = self.parent / 'second-data'
        second.mkdir()
        (second / 'different.mp4').write_bytes(b'second')
        with patch.object(backend, 'ROOT', second):
            self.assertEqual(backend.videos(), [{'path': 'different.mp4', 'bytes': 6}])

    def test_only_supported_video_files_are_indexed(self):
        expected = set()
        for index, extension in enumerate(sorted(backend.EXTS)):
            name = f'C001/clip-{index}{extension.upper()}'
            self.video(name)
            expected.add(name)
        self.video('C001/qa.json', b'{}')
        self.video('C001/source_PL_label.xlsx', b'excel')
        self.video('C001/action_boxes.jpg', b'image')
        self.video('C001/unrelated.mp3', b'audio')
        (self.root / 'directory-named.mp4').mkdir()
        self.assertEqual({r['path'] for r in backend.videos()}, expected)

    def test_root_missing_raises_instead_of_returning_stale_catalog(self):
        self.video('C001/original.mp4')
        backend.videos()
        with patch.object(backend, 'ROOT', self.parent / 'missing'):
            with self.assertRaisesRegex(ValueError, '目录不存在'):
                backend.videos()

    def test_outside_symlink_file_is_not_indexed(self):
        outside = self.parent / 'outside.mp4'
        outside.write_bytes(b'outside')
        link = self.root / 'outside-link.mp4'
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest('Symlink creation is unavailable on this OS')
        self.assertEqual(backend.videos(), [])


if __name__ == '__main__':
    unittest.main()
