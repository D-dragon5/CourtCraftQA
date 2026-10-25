"""Read-only source_PL_label.xlsx extraction and conservative name matching.
Uses only the Python standard library. No Excel file is written.
"""
from pathlib import Path
import posixpath
import re
import unicodedata
import xml.etree.ElementTree as ET
from zipfile import ZipFile

MAIN = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
REL = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'

EVENT_ZH = {'Dribble': '运球', 'PassBall': '传球', '3ptShot': '三分投篮',
            '2ptShot': '两分投篮', 'Layup': '上篮', 'Rebound': '篮板',
            'Dunk': '扣篮', 'Block': '封盖', 'Steal': '抢断',
            'Screen': '掩护', 'Turnover': '失误'}
RESULT_ZH = {'success': '成功', 'missed': '未命中', 'made': '命中',
             'offensive': '进攻篮板', 'defensive': '防守篮板'}


def _column_number(reference):
    letters = re.match(r'[A-Z]+', reference or '')
    if not letters:
        return 0
    result = 0
    for letter in letters[0]:
        result = result * 26 + ord(letter) - 64
    return result - 1


def _xml(archive, name):
    if archive.getinfo(name).file_size > 16 * 1024 * 1024:
        raise ValueError('Excel XML exceeds read limit')
    return ET.fromstring(archive.read(name))


def load_reference(path):
    """Returns raw row values plus their sheet/row provenance; keeps Time unchanged."""
    path = Path(path)
    records = []
    with ZipFile(path) as archive:
        shared = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            shared = [''.join(t.text or '' for t in item.iter(MAIN + 't'))
                      for item in _xml(archive, 'xl/sharedStrings.xml')]
        workbook = _xml(archive, 'xl/workbook.xml')
        relations = _xml(archive, 'xl/_rels/workbook.xml.rels')
        targets = {r.attrib['Id']: r.attrib['Target'] for r in relations}
        for sheet in workbook.find(MAIN + 'sheets'):
            target = targets[sheet.attrib[REL + 'id']]
            target = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/' + target)
            if not target.startswith('xl/worksheets/'):
                continue
            rows = _xml(archive, target).find(MAIN + 'sheetData')
            headers = None
            for row in rows:
                cells = {}
                for cell in row:
                    index = _column_number(cell.attrib.get('r'))
                    kind = cell.attrib.get('t')
                    if kind == 'inlineStr':
                        value = ''.join(t.text or '' for t in cell.iter(MAIN + 't'))
                    else:
                        v = cell.find(MAIN + 'v')
                        value = v.text if v is not None and v.text is not None else ''
                        if kind == 's' and value:
                            value = shared[int(value)]
                    cells[index] = value
                if headers is None:
                    if not any(cells.values()):
                        continue
                    headers = {i: value.strip() for i, value in cells.items() if value.strip()}
                    if 'Player Name' not in headers.values():
                        headers = None
                        continue
                    continue
                values = {key: cells.get(i, '') for i, key in headers.items()}
                if not values.get('Player Name'):
                    continue
                event, result = values.get('Event Classification', ''), values.get('Result', '')
                records.append({'source': path.name, 'sheet': sheet.attrib['name'],
                                'excel_row': int(row.attrib['r']),
                                'player': values['Player Name'], 'time': values.get('Time', ''),
                                'event': event, 'event_zh': EVENT_ZH.get(event, event),
                                'result': result, 'result_zh': RESULT_ZH.get(result, result),
                                'raw': values})
    return records


def normalize_name(text):
    text = unicodedata.normalize('NFKD', text).casefold()
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[a-z0-9]+', text))


def match_reference(records, text):
    """Match full names or a surname unique within this workbook.

    Does not guess person IDs or use first-name-only matching. The caller should
    combine the current question, answer, and original answer as desired.
    """
    norm_text = ' ' + normalize_name(text) + ' '
    roster = sorted({record['player'] for record in records})
    full = {name: normalize_name(name) for name in roster}
    surname = {}
    suffixes = {'jr', 'sr', 'ii', 'iii', 'iv'}
    for name, normalized in full.items():
        parts = normalized.split()
        while parts and parts[-1] in suffixes:
            parts.pop()
        if len(parts) > 1:
            surname[name] = parts[-1]
    surname_counts = {value: list(surname.values()).count(value) for value in set(surname.values())}
    matched = {}
    for name, normalized in full.items():
        if normalized and ' ' + normalized + ' ' in norm_text:
            matched[name] = 'full_name'
        elif name in surname and surname_counts[surname[name]] == 1 and ' ' + surname[name] + ' ' in norm_text:
            matched[name] = 'unique_surname'
    return [dict(record, matched_by=matched[record['player']]) for record in records if record['player'] in matched]


def read_references(path):
    path = Path(path)
    raw_records = load_reference(path)
    records = []
    for record in raw_records:
        values = record['raw']
        records.append({'sheet': record['sheet'], 'row': record['excel_row'],
                        'player': values.get('Player Name', ''), 'time': values.get('Time', ''),
                        'event': values.get('Event', ''), 'classification': values.get('Event Classification', ''),
                        'result': values.get('Result', ''), 'caption': values.get('Caption', ''),
                        'core_event': values.get('Core Event', ''), 'highlight': values.get('Highlight', ''),
                        'raw': values})
    with ZipFile(path) as archive:
        sheets = [sheet.attrib['name'] for sheet in _xml(archive, 'xl/workbook.xml').find(MAIN + 'sheets')]
    return {'file': path.name, 'sheets': sheets, 'records': records,
            'players': sorted({r['player'] for r in records}),
            'time_note': '时间保留 Excel 原始标记，未换算为视频秒数。'}


def match_players(text, players):
    dummy_records = [{'player': player} for player in dict.fromkeys(players)]
    return [{'player': r['player'], 'method': r['matched_by']} for r in match_reference(dummy_records, text)]
