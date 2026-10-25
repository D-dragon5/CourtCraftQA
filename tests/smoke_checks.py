#!/usr/bin/env python3
"""Portable read/save smoke checks; all writes are disposable fixtures.
Usage: python smoke_checks.py /absolute/path/to/token_viewer.py
No source dataset files are read or changed. No third-party dependencies.
"""
from pathlib import Path
import argparse
import importlib.util
import json
import os
import sys
import tempfile
import zipfile
from xml.sax.saxutils import escape


def write_excel(path):
    headers = ['Event', 'Event Classification', 'Player Name', 'Time', 'Result', 'Core Event', 'Highlight', 'Caption']
    values = ['', 'Dribble', 'Luka Dončić', '0:00/2:10', 'success', '', '', '原始记录']
    def row_xml(index, row):
        return '<row r="%d">%s</row>' % (index, ''.join(
            '<c r="%s%d" t="inlineStr"><is><t>%s</t></is></c>' % (chr(65+i), index, escape(value))
            for i, value in enumerate(row)))
    main = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    rel = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('xl/workbook.xml', f'<workbook xmlns="{main}" xmlns:r="{rel}"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        archive.writestr('xl/worksheets/sheet1.xml', f'<worksheet xmlns="{main}"><sheetData>{row_xml(1,headers)}{row_xml(2,values)}</sheetData></worksheet>')


def run(backend_path):
    backend_path = backend_path.resolve()
    results = []
    with tempfile.TemporaryDirectory(prefix='basketball-qa-smoke-') as directory:
        scratch = Path(directory)
        root = scratch / 'data'
        root.mkdir()
        sys.path.insert(0, str(backend_path.parent))
        previous_root = os.environ.get('COURTCRAFT_ROOT')
        os.environ['COURTCRAFT_ROOT'] = str(root)
        try:
            spec = importlib.util.spec_from_file_location('basketball_qa_smoke_backend', backend_path)
            backend = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(backend)
        finally:
            if previous_root is None:
                os.environ.pop('COURTCRAFT_ROOT', None)
            else:
                os.environ['COURTCRAFT_ROOT'] = previous_root
        backend.ROOT = root
        backend.BACKUPS = scratch / 'backups'
        backend.CACHE = scratch / 'cache'
        case = root / 'C251'
        case.mkdir()
        source = case / 'qa.json'
        payload = {'prediction': [], 'review': [{'question': '请复盘', 'answer': '原答案'}]}
        source.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        original = source.read_bytes()
        (case / 'original.mp4').write_bytes(b'fixture-not-a-real-video')
        write_excel(case / 'source_PL_label.xlsx')

        doc = backend.read_json('C251/qa.json')
        assert doc['source_available'] is True
        assert doc['source_text'].encode('utf-8') == original
        assert doc['immutable_source_path'] == 'C251/qa.json'
        assert doc['save_path'] == 'C251/qa-new.json' and doc['save_version'] is None
        results.append('read/source baseline')

        unchanged_source = backend.save_json(dict(doc, text=json.dumps(payload, ensure_ascii=False, indent=2)))
        assert unchanged_source['skipped'] is True and unchanged_source['unchanged'] is True
        assert unchanged_source['cleanup_required'] is False
        assert unchanged_source['version'] == doc['version'] and unchanged_source['save_version'] is None
        assert not (case / 'qa-new.json').exists() and source.read_bytes() == original
        results.append('unchanged source/formatting only creates no sibling')

        payload['review'][0]['answer'] = '复盘修改'
        edited = json.dumps(payload, ensure_ascii=False)
        saved = backend.save_json(dict(doc, text=edited))
        sibling = case / 'qa-new.json'
        assert sibling.read_text(encoding='utf-8') == edited
        assert source.read_bytes() == original
        assert not (case / 'qa-new-new.json').exists()
        results.append('new sibling/original bytes preserved')

        saved_doc = backend.read_json(saved['path'])
        assert saved_doc['source_text'].encode('utf-8') == original
        assert saved_doc['immutable_source_path'] == 'C251/qa.json'
        previous = sibling.read_bytes()
        edited2 = edited + '\n'
        updated = backend.save_json(dict(saved_doc, text=edited2))
        assert Path(updated['backup']).read_bytes() == previous
        assert sibling.read_text(encoding='utf-8') == edited2 and source.read_bytes() == original
        assert not (case / 'qa-new-new.json').exists()
        results.append('repeat save/backup')

        current = backend.read_json('C251/qa-new.json')
        before = sibling.read_bytes()
        unchanged = backend.save_json(dict(current, text=current['text']))
        assert unchanged['unchanged'] is True and sibling.read_bytes() == before
        results.append('unchanged save')

        try:
            backend.save_json(dict(saved_doc, text='{}'))
        except backend.Conflict:
            pass
        else:
            raise AssertionError('stale sibling accepted')
        assert sibling.read_bytes() == before
        results.append('stale sibling rejected')

        source.write_text('{}', encoding='utf-8')
        try:
            backend.save_json(dict(current, text='{}'))
        except backend.Conflict:
            pass
        else:
            raise AssertionError('changed immutable source accepted')
        assert sibling.read_bytes() == before
        source.write_bytes(original)
        results.append('source-version conflict rejected')

        other = root / 'C252'
        other.mkdir()
        (other / 'qa.json').write_bytes(original)
        baseline = backend.read_json('C252/qa.json')
        (other / 'qa-new.json').write_text('{"external":true}', encoding='utf-8')
        external_bytes = (other / 'qa-new.json').read_bytes()
        try:
            backend.save_json(dict(baseline, text='{}'))
        except backend.Conflict:
            pass
        else:
            raise AssertionError('concurrently created sibling overwritten')
        assert (other / 'qa-new.json').read_bytes() == external_bytes
        results.append('newly created sibling conflict rejected')

        orphan = root / 'C253'
        orphan.mkdir()
        (orphan / 'qa-new.json').write_text('{"orphan":true}', encoding='utf-8')
        orphan_doc = backend.read_json('C253/qa-new.json')
        assert orphan_doc['source_available'] is False and orphan_doc['source_text'] is None and orphan_doc['source_version'] is None
        try:
            backend.save_json(dict(orphan_doc, text='{"orphan":false}'))
            orphan_mode = 'orphan save allowed with unavailable source'
        except (backend.Conflict, ValueError):
            orphan_mode = 'orphan save intentionally rejected'
        assert not (orphan / 'qa.json').exists() and not (orphan / 'qa-new-new.json').exists()
        results.append('missing source explicit; ' + orphan_mode)

        current = backend.read_json('C251/qa-new.json')
        try:
            backend.save_json(dict(current, text='{broken}'))
        except ValueError:
            pass
        else:
            raise AssertionError('invalid JSON accepted')
        assert sibling.read_bytes() == before
        results.append('invalid JSON rejected')

        outside = scratch / 'outside.json'
        outside.write_text('{}', encoding='utf-8')
        try:
            backend.read_json('../outside.json')
        except ValueError:
            pass
        else:
            raise AssertionError('root escape accepted')
        results.append('root confinement')

        links_supported = True
        try:
            (case / 'outside-link.json').symlink_to(outside)
        except (OSError, NotImplementedError):
            links_supported = False
        if links_supported:
            try:
                backend.read_json('C251/outside-link.json')
            except ValueError:
                pass
            else:
                raise AssertionError('symlink root escape accepted')
            results.append('outside symlink rejected')
        else:
            results.append('symlink check skipped: OS denied fixture symlink')

        refs = backend.excel_references('C251/original.mp4')
        assert refs['players'] == ['Luka Dončić'] and len(refs['records']) == 1
        record = refs['records'][0]
        assert record['time'] == '0:00/2:10' and record['classification'] == 'Dribble'
        assert record['row'] == 2 and record['sheet'] == 'Sheet1'
        assert backend.excel_references('C251/original.mp4') == refs
        (case / 'source_PL_label.xlsx').unlink()
        missing_refs = backend.excel_references('C251/original.mp4')
        assert missing_refs['records'] == [] and missing_refs.get('error')
        results.append('Excel read/time preserved/cache/missing file')
    for result in results:
        print('PASS:', result)
    print('ALL CHECKS PASSED:', len(results), '(temporary fixtures only)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backend', type=Path)
    args = parser.parse_args()
    run(args.backend)
