#!/usr/bin/env python3
"""CourtCraft video, image and JSON editor; no third-party Python dependencies."""
import hashlib
import json
import mimetypes
import os
import re
import subprocess
import threading
import time
import secrets
import tempfile
import argparse
import shutil
import sys
import errno
from decimal import Decimal
from zipfile import BadZipFile
from xml.etree.ElementTree import ParseError
from excel_reference import read_references
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, unquote

APP_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_ROOT = APP_DIR / 'data' / 'C251-C300'
ROOT = Path(os.environ.get('COURTCRAFT_ROOT', DEFAULT_DATA_ROOT)).expanduser().resolve()
FFMPEG = os.environ.get('COURTCRAFT_FFMPEG') or (
    str(APP_DIR / 'tools' / 'ffmpeg.exe') if os.name == 'nt' and (APP_DIR / 'tools' / 'ffmpeg.exe').is_file()
    else shutil.which('ffmpeg') or 'ffmpeg')
CACHE = APP_DIR / 'cache'
HOST = '127.0.0.1'
PORT = 5012
CONFIG_FILE = APP_DIR / 'config.json'
ROOT_SWITCHED = False

EXTS = {'.mp4', '.mov', '.webm', '.mkv', '.avi', '.m4v'}
LOCK = threading.Lock()
CONVERT = threading.Semaphore(1)
catalog = []
catalog_at = 0
catalog_root = None
CSRF = os.environ.get('COURTCRAFT_VIEWER_TOKEN') or secrets.token_urlsafe(32)
SAVE_LOCK = threading.Lock()
BACKUPS = APP_DIR / 'backups'
MAX_JSON = 8 * 1024 * 1024
IMAGES = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}



def source(rel, root=None):
    root = ROOT if root is None else root
    p = (root / rel).resolve()
    if not p.is_relative_to(root) or not p.is_file() or p.suffix.lower() not in EXTS:
        raise ValueError('无效的视频路径')
    return p


def scan_videos(root):
    """Scan one explicit directory without reading or modifying global state."""
    if not root.is_dir():
        raise ValueError('CourtCraft 目录不存在')
    # iterdir explicitly checks directory readability, including empty roots.
    next(root.iterdir(), None)
    return sorted([{'path': p.relative_to(root).as_posix(), 'bytes': p.stat().st_size}
                   for p in root.rglob('*') if p.suffix.lower() in EXTS
                   and p.is_file() and p.resolve().is_relative_to(root)],
                  key=lambda r: [int(part) if part.isdigit() else part for part in re.split(r'(\d+)', r['path'])])


def videos(refresh=False):
    """Index every supported video below the configured root, with no row limit."""
    global catalog, catalog_at, catalog_root
    with LOCK:
        if refresh or ROOT != catalog_root or time.monotonic() - catalog_at > 15 or not catalog_at:
            catalog = scan_videos(ROOT)
            catalog_at = time.monotonic()
            catalog_root = ROOT
        return catalog

def prepare(rel, root=None):
    from urllib.parse import quote
    p = source(rel, root=root)
    if p.suffix.lower() in {'.mp4', '.webm', '.m4v'}:
        return '/video?path=' + quote(rel, safe='')
    key = hashlib.sha256(f'{p}:{p.stat().st_size}:{p.stat().st_mtime_ns}'.encode()).hexdigest()
    CACHE.mkdir(parents=True, exist_ok=True)
    out = CACHE / (key + '.mp4')
    with CONVERT:
        if not out.exists():
            tmp = CACHE / (key + '.tmp.mp4')
            if not shutil.which(FFMPEG):
                raise ValueError('MOV 转换需要 ffmpeg，请配置 ffmpeg 路径')
            cmd = [FFMPEG, '-nostdin', '-v', 'error', '-y', '-i', str(p), '-map', '0:v:0', '-map', '0:a:0?', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22', '-pix_fmt', 'yuv420p', '-c:a', 'aac']
            try:
                subprocess.run(cmd+['-movflags','+faststart',str(tmp)], check=True, timeout=300, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                tmp.replace(out)
            finally:
                tmp.unlink(missing_ok=True)
    return '/cached?file=' + out.name


def asset_source(rel, extensions):
    if not isinstance(rel, str):
        raise ValueError('文件路径必须是字符串')
    base = ROOT
    p = (ROOT / rel).resolve()
    if not p.is_relative_to(base) or not p.is_file() or p.suffix.lower() not in extensions:
        raise ValueError('只能访问所选数据目录内的指定类型文件')
    return p

def assets(rel):
    video = source(rel)
    result = {'images': [], 'json': []}
    for p in sorted(video.parent.iterdir()):
        if not p.is_file() or not p.resolve().is_relative_to(ROOT):
            continue
        key = 'images' if p.suffix.lower() in IMAGES else 'json' if p.suffix.lower() == '.json' else None
        if key:
            result[key].append({'name': p.name, 'path': p.relative_to(ROOT).as_posix()})
    return result

REFERENCE_CACHE = {}
REFERENCE_LOCK = threading.Lock()


def excel_references(rel):
    video = source(rel)
    candidate = video.parent / 'source_PL_label.xlsx'
    if not candidate.exists():
        return {'file': candidate.name, 'records': [], 'players': [], 'sheets': [],
                'error': '同目录未找到 source_PL_label.xlsx', 'time_note': ''}
    p = asset_source(candidate.relative_to(ROOT).as_posix(), {'.xlsx'})
    if p.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('Excel 文件超过读取限制')
    info = p.stat()
    key = (str(p), info.st_size, info.st_mtime_ns)
    with REFERENCE_LOCK:
        if key not in REFERENCE_CACHE:
            if len(REFERENCE_CACHE) > 100:
                REFERENCE_CACHE.clear()
            try:
                data = read_references(p)
            except (BadZipFile, ParseError, KeyError, IndexError, ValueError) as error:
                raise ValueError(f'无法读取 Excel 参考文件 {p.name}：{error}') from error
            data['path'] = str(p)
            REFERENCE_CACHE[key] = data
        return REFERENCE_CACHE[key]


def strict_json(text):
    def invalid(value):
        raise ValueError('JSON 不支持 ' + value)
    return json.loads(text, parse_constant=invalid)


def json_semantically_equal(left_text, right_text):
    """Compare JSON values without conflating booleans with numeric values."""
    def invalid(value):
        raise ValueError('JSON 不支持 ' + value)

    def equivalent(left, right):
        if type(left) is not type(right):
            return False
        if isinstance(left, dict):
            return left.keys() == right.keys() and all(
                equivalent(value, right[key]) for key, value in left.items())
        if isinstance(left, list):
            return len(left) == len(right) and all(
                equivalent(a, b) for a, b in zip(left, right))
        return left == right

    try:
        left = json.loads(left_text, parse_int=Decimal, parse_float=Decimal,
                          parse_constant=invalid)
        right = json.loads(right_text, parse_int=Decimal, parse_float=Decimal,
                           parse_constant=invalid)
    except (ValueError, TypeError):
        return False
    return equivalent(left, right)

def output_path(p):
    name = p.stem if p.stem.endswith('-new') else p.stem + '-new'
    target = p.with_name(name + '.json')
    if target.is_symlink() or not target.resolve().is_relative_to(ROOT):
        raise ValueError('保存目标必须位于数据目录内，且不能是链接文件')
    return target


def file_version(p):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def immutable_source_path(p):
    # A saved sibling always refers back to the original stem exactly once.
    candidate = p.with_name(p.stem[:-4] + p.suffix) if p.stem.endswith('-new') else p
    resolved = candidate.resolve()
    if not resolved.is_relative_to(ROOT):
        raise ValueError('源 JSON 必须位于数据目录内')
    return candidate


def immutable_source_snapshot(p):
    candidate = immutable_source_path(p)
    result = {'immutable_source_path': candidate.relative_to(ROOT).as_posix(),
              'source_available': False, 'source_text': None, 'source_version': None}
    if not candidate.exists():
        return result
    source_file = asset_source(candidate.relative_to(ROOT).as_posix(), {'.json'})
    if source_file.stat().st_size > MAX_JSON:
        raise ValueError('源 JSON 文件超过 8 MiB 限制')
    raw = source_file.read_bytes()
    if len(raw) > MAX_JSON:
        raise ValueError('源 JSON 文件超过 8 MiB 限制')
    return dict(result, source_available=True, source_text=raw.decode('utf-8-sig'),
                source_version=hashlib.sha256(raw).hexdigest())


def validate_immutable_source(p, data):
    if 'immutable_source_path' not in data and 'source_version' not in data:
        return
    candidate = immutable_source_path(p)
    relative = candidate.relative_to(ROOT).as_posix()
    if data.get('immutable_source_path') != relative:
        raise ValueError('源 JSON 路径与当前文件不对应')
    snapshot = immutable_source_snapshot(p)
    if snapshot['source_version'] != data.get('source_version'):
        raise Conflict('源 JSON 已改变，请先保留当前修改，再重新读取源文件进行对照。')


def read_json_bytes(p):
    if p.stat().st_size > MAX_JSON:
        raise ValueError('JSON 文件超过 8 MiB 限制')
    raw = p.read_bytes()
    if len(raw) > MAX_JSON:
        raise ValueError('JSON 文件超过 8 MiB 限制')
    return raw


def document_snapshot(p, raw=None):
    """Build a real on-disk document snapshot while SAVE_LOCK is held."""
    raw = read_json_bytes(p) if raw is None else raw
    target = output_path(p)
    source_info = immutable_source_snapshot(p)
    saved_raw = (raw if target == p else read_json_bytes(target)) if target.exists() else None
    saved_text = saved_raw.decode('utf-8-sig') if saved_raw is not None else None
    saved_version = hashlib.sha256(saved_raw).hexdigest() if saved_raw is not None else None
    matches = (source_info['source_available'] and saved_text is not None and
               json_semantically_equal(source_info['source_text'], saved_text))
    return dict(source_info,
                root_id=root_identifier(),
                path=p.relative_to(ROOT).as_posix(), text=raw.decode('utf-8-sig'),
                version=hashlib.sha256(raw).hexdigest(),
                save_path=target.relative_to(ROOT).as_posix(), save_version=saved_version,
                saved_path=target.relative_to(ROOT).as_posix(), saved_text=saved_text,
                saved_version=saved_version, saved_matches_source=bool(matches),
                target_exists=saved_raw is not None,
                cleanup_required=bool(matches),
                cleanup_requires_discard=source_info['source_available'] and saved_raw is not None and not matches)


def read_json(rel, expected_root_id=None):
    with SAVE_LOCK:
        validate_read_root(expected_root_id)
        return document_snapshot(asset_source(rel, {'.json'}))


class Conflict(ValueError):
    pass


def root_identifier(root=None):
    value = os.path.normcase(str((ROOT if root is None else root).resolve()))
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def validate_read_root(expected):
    if expected is not None and expected != root_identifier():
        raise Conflict('数据目录已在其他页面切换，请保留当前编辑并重新读取列表。')


def validate_write_root(data):
    expected = data.get('root_id')
    if expected is None and not ROOT_SWITCHED:
        return
    if expected != root_identifier():
        raise Conflict('数据目录已切换，当前页面的编辑不能写入新目录；请保留内容后重新读取。')


def persist_data_root(root):
    """Replace only data_root atomically; failures leave the old config intact."""
    path = CONFIG_FILE
    settings = strict_json(path.read_text(encoding='utf-8-sig')) if path.is_file() else {}
    if not isinstance(settings, dict):
        raise ValueError('配置文件必须是 JSON 对象，当前目录未切换。')
    settings['data_root'] = str(root)
    raw = (json.dumps(settings, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    fd, name = tempfile.mkstemp(prefix='.viewer-config-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def switch_root(data):
    """Validate, scan and remember an existing directory before publishing it."""
    global ROOT, ROOT_SWITCHED, catalog, catalog_at, catalog_root
    if not isinstance(data, dict) or not isinstance(data.get('data_root'), str) or not data['data_root'].strip():
        raise ValueError('请输入已存在的数据根目录。')
    requested = Path(data['data_root'].strip()).expanduser()
    if not requested.is_absolute():
        raise ValueError('数据根目录必须使用绝对路径。')
    requested = requested.resolve()
    with SAVE_LOCK:
        if data.get('root_id') != root_identifier():
            raise Conflict('数据目录已在其他页面切换，请先刷新列表后再选择目录。')
    candidates = scan_videos(requested)
    with SAVE_LOCK:
        with LOCK:
            if data.get('root_id') != root_identifier():
                raise Conflict('扫描期间数据目录已被其他页面切换，请重新读取列表。')
            if not requested.is_dir():
                raise ValueError('扫描后的数据目录已不存在，当前目录未切换。')
            next(requested.iterdir(), None)
            # Persist first. No live state changes if configuration cannot save.
            persist_data_root(requested)
            ROOT_SWITCHED = ROOT_SWITCHED or requested != ROOT
            ROOT = requested
            catalog = candidates
            catalog_root = requested
            catalog_at = time.monotonic()
            return {'data_root': str(ROOT), 'root_id': root_identifier(),
                    'videos': list(catalog), 'persisted': True}


def backup_json(p, raw):
    backup = BACKUPS / p.relative_to(ROOT) / (
        time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(6) + '.bak')
    backup.parent.mkdir(parents=True, exist_ok=True)
    with backup.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return backup


def restore_cleanup_file(archived, target):
    """Restore without replacing a file created by another editor."""
    try:
        # Linking preserves the recovery copy and atomically refuses an existing
        # destination on both platforms. Same-directory staging stays on-volume.
        os.link(archived, target)
        return True
    except FileExistsError:
        return False
    except OSError:
        if os.name != 'nt':
            return False
        try:
            # Windows rename also refuses an existing destination; POSIX rename
            # must not be used here because it would overwrite it.
            os.rename(archived, target)
            return True
        except OSError:
            return False


def save_json(data):
    if not isinstance(data, dict) or not isinstance(data.get('text'), str):
        raise ValueError('缺少 JSON 内容')
    raw = data['text'].encode('utf-8')
    if len(raw) > MAX_JSON:
        raise ValueError('JSON 文件超过 8 MiB 限制')
    strict_json(data['text'])
    with SAVE_LOCK:
        validate_write_root(data)
        source_file = asset_source(data.get('path'), {'.json'})
        if file_version(source_file) != data.get('version'):
            raise Conflict('读取的文件已改变，请先保留当前修改，再重新读取。')
        validate_immutable_source(source_file, data)
        target = output_path(source_file)
        expected = data.get('save_version')
        if file_version(target) != expected:
            raise Conflict('新版文件已被修改或创建，请先保留当前修改，再重新读取。')
        old = read_json_bytes(target) if target.exists() else None
        source_info = immutable_source_snapshot(source_file)
        if (source_info['source_available'] and
                json_semantically_equal(data['text'], source_info['source_text'])):
            # Candidate formatting alone must never create or overwrite a sibling.
            # Return actual source/target versions, not the unsaved candidate hash.
            origin = asset_source(source_info['immutable_source_path'], {'.json'})
            result = document_snapshot(origin)
            validate_immutable_source(source_file, data)
            if file_version(source_file) != data.get('version'):
                raise Conflict('读取的文件在检查期间改变，请重新读取。')
            if result['source_version'] != source_info['source_version']:
                raise Conflict('源 JSON 在检查期间改变，请重新读取。')
            if result['save_version'] != expected:
                raise Conflict('新版文件在检查期间改变，请重新读取。')
            result['cleanup_required'] = result['target_exists']
            return dict(result, status='skipped_unchanged', skipped=True, written=False,
                        unchanged=True, backup=None)
        if old == raw:
            return dict(document_snapshot(target, old), status='saved_unchanged',
                        skipped=False, written=False, unchanged=True, backup=None)
        backup = None
        if old is not None:
            backup = backup_json(target, old)
        fd, name = tempfile.mkstemp(prefix='.viewer-', suffix='.tmp', dir=target.parent)
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            validate_immutable_source(source_file, data)
            if file_version(source_file) != data.get('version') or file_version(target) != expected:
                raise Conflict('保存期间文件发生变化，当前内容未覆盖。')
            if old is None:
                # Exclusive creation preserves a concurrently created output file.
                try:
                    os.rename(name, target) if os.name == 'nt' else os.link(name, target)
                except FileExistsError:
                    raise Conflict('新版文件刚被创建，请重新读取后合并。')
            else:
                os.replace(name, target)
        finally:
            Path(name).unlink(missing_ok=True)
        return dict(document_snapshot(target, raw), status='saved', skipped=False,
                    written=True, backup=str(backup) if backup else None, unchanged=False)


def cleanup_json(data):
    """Delete a confirmed sibling only after validating its original snapshot."""
    if not isinstance(data, dict) or data.get('confirm_delete') is not True:
        raise ValueError('清理新版文件需要明确确认 confirm_delete=true')
    relative = data.get('path')
    if not isinstance(relative, str):
        raise ValueError('文件路径必须是字符串')
    with SAVE_LOCK:
        validate_write_root(data)
        requested = (ROOT / relative).resolve()
        if not requested.is_relative_to(ROOT) or requested.suffix.lower() != '.json':
            raise ValueError('只能清理数据目录内对应的新版 JSON')
        origin = immutable_source_path(requested)
        target = output_path(requested)
        if origin == target or not target.stem.endswith('-new'):
            raise ValueError('只能删除新版文件，原始 JSON 不可删除')
        if not origin.is_file():
            if isinstance(data.get('source_version'), str):
                raise Conflict('源 JSON 在提示后已不存在，未删除任何文件。')
            raise ValueError('缺少原始 JSON，无法清理新版文件')
        origin = asset_source(origin.relative_to(ROOT).as_posix(), {'.json'})
        if data.get('immutable_source_path') != origin.relative_to(ROOT).as_posix():
            raise ValueError('源 JSON 路径与当前文件不对应')
        if not isinstance(data.get('source_version'), str) or not isinstance(data.get('save_version'), str):
            raise ValueError('清理需要源文件和新版文件的版本')
        source_raw = read_json_bytes(origin)
        source_version = hashlib.sha256(source_raw).hexdigest()
        if source_version != data['source_version']:
            raise Conflict('源 JSON 在提示后改变，未删除任何文件。')
        if not target.is_file():
            raise Conflict('新版文件在提示后已不存在，未删除任何文件。')
        saved_raw = read_json_bytes(target)
        saved_version = hashlib.sha256(saved_raw).hexdigest()
        if saved_version != data['save_version']:
            raise Conflict('新版文件在提示后改变，未删除任何文件。')
        read_version = source_version if requested == origin else saved_version
        if data.get('version') != read_version:
            raise Conflict('读取的文件在提示后改变，未删除任何文件。')
        matches = json_semantically_equal(source_raw.decode('utf-8-sig'), saved_raw.decode('utf-8-sig'))
        if not matches and data.get('discard_saved_changes') is not True:
            raise Conflict('磁盘新版仍有修改；需要先查看差异并明确确认放弃这些修改。')
        fd, stage_name = tempfile.mkstemp(prefix='.viewer-cleanup-', suffix='.bak', dir=target.parent)
        os.close(fd)
        stage = Path(stage_name)
        recovery = None
        backup_copy = None
        try:
            try:
                # Capture the actual inode first. Never unlink a pathname that
                # another process could have replaced after a version check.
                os.replace(target, stage)
            except FileNotFoundError as error:
                raise Conflict('新版文件已被其他操作移除，未删除其他文件。') from error
            recovery = stage
            captured = read_json_bytes(stage)
            if (hashlib.sha256(captured).hexdigest() != saved_version or
                    file_version(origin) != source_version):
                raise Conflict('文件在隔离期间改变，清理已取消。')
            backup = backup_json(target, captured)
            if (file_version(origin) != source_version or file_version(stage) != saved_version or
                    target.exists() or target.is_symlink()):
                raise Conflict('文件在备份期间改变，清理已取消。')
            try:
                # Preserve the captured inode as the backup instead of unlinking
                # it: writes through an already-open external handle survive.
                os.replace(stage, backup)
                recovery = backup
            except OSError as error:
                if error.errno != errno.EXDEV:
                    raise
                # Cross-volume archives cannot be atomic. Keep the authoritative
                # inode in the hidden on-volume recovery file as an extra backup.
                backup_copy, backup = backup, stage
            with backup.open('r+b') as archived:
                os.fsync(archived.fileno())
            if (file_version(origin) != source_version or target.exists() or target.is_symlink()):
                raise Conflict('文件在归档期间改变，清理已取消。')
            result = document_snapshot(origin)
            if result['source_version'] != source_version or result['save_version'] is not None:
                raise Conflict('文件在完成清理前改变，清理已取消。')
            return dict(result, status='cleaned', deleted=True,
                        deleted_path=target.relative_to(ROOT).as_posix(),
                        discarded_saved_changes=not matches, skipped=False, written=False,
                        unchanged=True, backup=str(backup),
                        backup_copy=str(backup_copy) if backup_copy else None)
        except Exception as error:
            if recovery is not None and recovery.exists():
                if not restore_cleanup_file(recovery, target):
                    raise Conflict(f'{error} 已保留恢复副本：{recovery}') from error
            raise
        finally:
            # Only an unused empty reservation may be removed here. Captured
            # data is always restored or retained under a recovery/backup name.
            if recovery is None:
                stage.unlink(missing_ok=True)


class Handler(BaseHTTPRequestHandler):
    def reply(self, data, content='application/json; charset=utf-8', status=200):
        raw = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status); self.send_header('Cache-Control', 'no-store'); self.send_header('Content-Type', content)
        self.send_header('Content-Length', str(len(raw))); self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers()
        if self.command != 'HEAD': self.wfile.write(raw)

    def do_HEAD(self): self.do_GET()

    def do_GET(self):
        u = urlsplit(self.path); args = parse_qs(u.query)
        try:
            if u.path == '/': return self.reply((APP_DIR / 'viewer.html').read_text(encoding='utf-8').replace('__CSRF_TOKEN__', CSRF).encode(), 'text/html; charset=utf-8')
            if u.path.startswith(('/static/', '/assets/')):
                return self.static_asset(u.path)
            if u.path == '/api/health':
                with SAVE_LOCK:
                    return self.reply({'status': 'ok', 'data_root': str(ROOT), 'root_id': root_identifier(),
                                       'videos': len(videos()), 'python': sys.version.split()[0], 'ffmpeg': FFMPEG})
            if u.path == '/api/root':
                with SAVE_LOCK:
                    rows = videos(refresh=args.get('refresh', [''])[0].lower() in {'1', 'true'})
                    return self.reply({'data_root': str(ROOT), 'root_id': root_identifier(), 'videos': rows})
            expected_root_id = args.get('root_id', [None])[0]
            if u.path in {'/api/assets', '/api/references'}:
                with SAVE_LOCK:
                    validate_read_root(expected_root_id)
                    value = assets(args.get('path', [''])[0]) if u.path == '/api/assets' else excel_references(args.get('path', [''])[0])
                    return self.reply(value)
            if u.path == '/api/json': return self.reply(read_json(args.get('path',[''])[0], expected_root_id))
            if u.path == '/image':
                with SAVE_LOCK:
                    validate_read_root(expected_root_id)
                    p = asset_source(args.get('path',[''])[0], IMAGES)
                    return self.reply(p.read_bytes(), mimetypes.guess_type(p.name)[0] or 'application/octet-stream')
            if u.path == '/api/videos': return self.reply(videos(refresh=args.get('refresh', [''])[0].lower() in {'1', 'true'}))
            if u.path == '/api/prepare':
                with SAVE_LOCK:
                    validate_read_root(expected_root_id)
                    prepared_root, prepared_root_id = ROOT, root_identifier()
                url = prepare(args.get('path', [''])[0], root=prepared_root)
                with SAVE_LOCK:
                    validate_read_root(prepared_root_id)
                    return self.reply({'url': url + ('&' if '?' in url else '?') + 'root_id=' + prepared_root_id})
            with SAVE_LOCK:
                validate_read_root(expected_root_id)
                if u.path == '/video': p = source(args.get('path',[''])[0])
                elif u.path == '/cached':
                    name = args.get('file',[''])[0]
                    if not re.fullmatch(r'[a-f0-9]{64}\.mp4', name): raise ValueError('无效路径')
                    p = CACHE / name
                    if not p.is_file(): raise ValueError('缓存不存在')
                else: return self.reply({'error':'未找到'}, status=404)
            self.stream(p)
        except (BrokenPipeError, ConnectionResetError): pass
        except Conflict as e:
            self.reply({'error': str(e)}, status=409)
        except (ValueError, OSError, subprocess.SubprocessError) as e:
            self.reply({'error':str(e)}, status=400)

    def static_asset(self, url_path):
        relative = unquote(url_path).lstrip('/')
        candidate = (APP_DIR / relative).resolve()
        allowed = ((APP_DIR / 'static').resolve(), (APP_DIR / 'assets').resolve())
        if not any(candidate.is_relative_to(folder) for folder in allowed) or not candidate.is_file():
            return self.reply({'error': '未找到'}, status=404)
        types = {'.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
                 '.png': 'image/png', '.svg': 'image/svg+xml', '.ico': 'image/x-icon'}
        if candidate.suffix.lower() not in types:
            return self.reply({'error': '未找到'}, status=404)
        return self.reply(candidate.read_bytes(), types[candidate.suffix.lower()])

    def do_POST(self):
        endpoint = urlsplit(self.path).path
        if endpoint not in {'/api/json', '/api/json/cleanup', '/api/root'}:
            return self.reply({'error': '未找到'}, status=404)
        if not secrets.compare_digest(self.headers.get('X-Viewer-Token', ''), CSRF):
            return self.reply({'error': '页面验证已过期，请保留编辑内容后刷新页面'}, status=403)
        if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
            return self.reply({'error': '需要 application/json'}, status=415)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length <= 0 or length > MAX_JSON * 2:
                return self.reply({'error': '请求大小无效'}, status=413)
            self.connection.settimeout(30)
            data = strict_json(self.rfile.read(length).decode('utf-8'))
            self.reply(switch_root(data) if endpoint == '/api/root' else cleanup_json(data) if endpoint == '/api/json/cleanup' else save_json(data))
        except Conflict as e:
            self.reply({'error': str(e)}, status=409)
        except (ValueError, OSError, TypeError) as e:
            self.reply({'error': str(e)}, status=400)

    def stream(self, p):
        size=p.stat().st_size; start=0; end=size-1; partial=False
        value=self.headers.get('Range')
        if value:
            match=re.fullmatch(r'bytes=(\d*)-(\d*)',value)
            if not match or not any(match.groups()): return self.bad_range(size)
            a,b=match.groups()
            if a: start=int(a); end=min(int(b),size-1) if b else size-1
            else: start=max(0,size-int(b))
            if start>=size or start>end: return self.bad_range(size)
            partial=True
        self.send_response(206 if partial else 200)
        self.send_header('Content-Type','video/webm' if p.suffix.lower()=='.webm' else 'video/mp4')
        self.send_header('Accept-Ranges','bytes'); self.send_header('Content-Length',str(end-start+1))
        if partial: self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.end_headers()
        if self.command=='HEAD': return
        with p.open('rb') as f:
            f.seek(start); remaining=end-start+1
            while remaining>0:
                block=f.read(min(1024*1024,remaining))
                if not block: break
                self.wfile.write(block); remaining-=len(block)

    def bad_range(self,size):
        self.send_response(416); self.send_header('Content-Range',f'bytes */{size}')
        self.send_header('Content-Length','0'); self.end_headers()

def configure(config_path=None, **overrides):
    """Apply saved settings, environment variables, then explicit CLI overrides."""
    global ROOT, FFMPEG, CACHE, BACKUPS, HOST, PORT, CONFIG_FILE
    path = (Path(config_path).expanduser() if config_path else APP_DIR / 'config.json').resolve()
    settings = json.loads(path.read_text(encoding='utf-8-sig')) if path.is_file() else {}
    if not isinstance(settings, dict):
        raise ValueError('配置文件必须是 JSON 对象')
    def choose(key, environment, fallback):
        explicit = overrides.get(key)
        return explicit if explicit is not None else os.environ.get(environment, settings.get(key, fallback))
    def app_path(value):
        result = Path(value).expanduser()
        return (APP_DIR / result).resolve() if not result.is_absolute() else result.resolve()
    ROOT = app_path(choose('data_root', 'COURTCRAFT_ROOT', DEFAULT_DATA_ROOT))
    CACHE = app_path(choose('cache_dir', 'COURTCRAFT_CACHE', 'cache'))
    BACKUPS = app_path(choose('backups_dir', 'COURTCRAFT_BACKUPS', 'backups'))
    HOST = str(choose('host', 'COURTCRAFT_HOST', '127.0.0.1'))
    PORT = int(choose('port', 'COURTCRAFT_PORT', 5012))
    FFMPEG = str(choose('ffmpeg', 'COURTCRAFT_FFMPEG', FFMPEG) or FFMPEG)
    if not ROOT.is_dir():
        raise ValueError(f'数据目录不存在：{ROOT}')
    if not 1 <= PORT <= 65535:
        raise ValueError('端口必须为 1–65535')
    CONFIG_FILE = path


def main():
    parser = argparse.ArgumentParser(description='篮球视频与问答核对工具')
    parser.add_argument('--config', help='JSON 配置文件路径，默认读取项目 config.json')
    parser.add_argument('--data-root', help='视频、图片、JSON 与 Excel 所在的数据根目录')
    parser.add_argument('--host', help='监听地址，默认 127.0.0.1')
    parser.add_argument('--port', type=int, help='监听端口，默认 5012')
    parser.add_argument('--ffmpeg', help='ffmpeg 可执行文件路径')
    args = parser.parse_args()
    try:
        configure(args.config, data_root=args.data_root, host=args.host, port=args.port, ffmpeg=args.ffmpeg)
        server = ThreadingHTTPServer((HOST, PORT), Handler)
    except (ValueError, OSError) as error:
        parser.exit(1, f'启动失败：{error}\n')
    print(f'数据目录：{ROOT}\n网页：http://{HOST}:{PORT}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
