"""Create four disposable demo rounds from one original case, without changing it."""
import argparse
import json
from pathlib import Path
import shutil

PROJECT = Path(__file__).resolve().parents[1]
VIDEO_TYPES = {'.mp4', '.mov', '.webm', '.mkv', '.avi', '.m4v'}
COPY_TYPES = VIDEO_TYPES | {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.xlsx'}


def prepare(source, destination=None, config=None):
    source = Path(source).expanduser().resolve()
    destination = Path(destination or PROJECT / 'demo-data').expanduser().resolve()
    config = Path(config or PROJECT / 'demo-config.json').expanduser().resolve()
    if not source.is_dir():
        raise ValueError('请选择包含 qa.json 和视频的单个回合文件夹。')
    if destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError('演示目录与源回合目录不能相互包含。')
    if config.is_relative_to(source) or config.is_relative_to(destination):
        raise ValueError('演示配置应放在源回合与演示数据目录之外。')
    if destination.exists() or config.exists():
        raise ValueError('演示目录或配置已存在。请选择新的 --output 与 --config 路径，避免覆盖演示进度。')
    original = (source / 'qa.json').read_bytes()
    data = json.loads(original.decode('utf-8-sig'))
    questions = [qa for stage in data.get('prediction', []) for qa in stage.get('qa', [])] + data.get('review', [])
    first = next((qa for qa in questions if isinstance(qa.get('answer'), str)), None)
    if first is None:
        raise ValueError('源文件至少需要一道字符串答案的问答。')
    files = [p for p in source.iterdir() if p.is_file() and p.suffix.lower() in COPY_TYPES and not p.name.startswith('~$')]
    if not any(p.suffix.lower() in VIDEO_TYPES for p in files):
        raise ValueError('源回合文件夹没有可用视频。')
    destination.mkdir(parents=True)
    names = []
    for prefix, mode in [('01', 'edit'), ('02', 'clean'), ('03', 'duplicate'), ('04', 'saved')]:
        folder = destination / f'{prefix}-{source.name}-{mode}'
        folder.mkdir()
        names.append(folder.name)
        (folder / 'qa.json').write_bytes(original)
        for path in files:
            shutil.copy2(path, folder / path.name)
        if mode == 'duplicate':
            (folder / 'qa-new.json').write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        elif mode == 'saved':
            saved = json.loads(json.dumps(data))
            saved_questions = [qa for stage in saved.get('prediction', []) for qa in stage.get('qa', [])] + saved.get('review', [])
            next(qa for qa in saved_questions if isinstance(qa.get('answer'), str))['answer'] += '演示旧版修改'
            (folder / 'qa-new.json').write_text(json.dumps(saved, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    local = PROJECT / 'config.json'
    settings = json.loads(local.read_text(encoding='utf-8-sig')) if local.exists() else {}
    demo = {'data_root': str(destination), 'host': '127.0.0.1', 'port': 5016,
            'ffmpeg': settings.get('ffmpeg', 'ffmpeg'),
            'cache_dir': str(destination.parent / 'demo-cache'),
            'backups_dir': str(destination.parent / 'demo-backups')}
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps(demo, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {'rounds': names, 'data_root': str(destination), 'config': str(config),
            'url': 'http://127.0.0.1:5016', 'source_untouched': True}


def main():
    parser = argparse.ArgumentParser(description='复制一个源回合，准备四个独立演示场景。')
    parser.add_argument('source', help='包含 qa.json 和视频的单个源回合文件夹')
    parser.add_argument('--output', help='新的演示目录，默认项目 demo-data')
    parser.add_argument('--config', help='新的演示配置路径，默认项目 demo-config.json')
    args = parser.parse_args()
    try:
        result = prepare(args.source, args.output, args.config)
    except (ValueError, OSError, TypeError, KeyError) as error:
        parser.exit(1, f'准备失败：{error}\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print('启动演示：python token_viewer.py --config "' + result['config'] + '"')


if __name__ == '__main__':
    main()
