"""Build a Windows x64 bundle from explicit source and vendor inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
ROOT_FILES = ['.gitignore', '.gitattributes', 'AGENTS.md', 'README.md', 'README.txt',
              'requirements.txt', 'config.example.json', 'remote.example.json',
              'token_viewer.py', 'excel_reference.py', 'viewer.html',
              'start.bat', 'stop.bat', 'start.ps1', 'stop.ps1',
              'status.bat', 'status.ps1', 'install-shortcuts.bat', 'install-shortcuts.ps1', 'VERSION',
              'start-demo.bat', 'stop-demo.bat', 'open-48g.bat', 'open-48g.ps1']


def sources():
    files = [PROJECT / name for name in ROOT_FILES]
    for folder in ['static', 'assets', 'docs', 'examples', 'scripts', 'tests']:
        files.extend(p for p in (PROJECT / folder).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
    return sorted(files)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(python_zip, ffmpeg, ffmpeg_source, output, overwrite=False):
    output = Path(output).resolve()
    version = (PROJECT / 'VERSION').read_text().strip()
    if f'v{version}' not in output.name:
        raise ValueError(f'文件名应包含版本号 v{version}，例如 CourtCraftQA-v{version}-Windows-x64.zip。')
    if output.exists() and not overwrite:
        raise FileExistsError('输出已存在，使用新文件名或 --overwrite。')
    python_zip, ffmpeg, ffmpeg_source = [Path(p).resolve() for p in (python_zip, ffmpeg, ffmpeg_source)]
    for path in [python_zip, ffmpeg, ffmpeg_source]:
        if not path.is_file():
            raise ValueError('缺少依赖文件：' + str(path))
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='courtcraft-portable-') as temporary:
        root = Path(temporary) / 'CourtCraftQA'
        root.mkdir()
        for source in sources():
            target = root / source.relative_to(PROJECT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        runtime = root / 'runtime'
        runtime.mkdir()
        with zipfile.ZipFile(python_zip) as archive:
            for member in archive.infolist():
                relative = Path(member.filename)
                if relative.is_absolute() or '..' in relative.parts:
                    raise ValueError('Python 压缩包包含无效路径。')
            archive.extractall(runtime)
        path_files = list(runtime.glob('python*._pth'))
        if len(path_files) != 1 or not (runtime / 'python.exe').is_file():
            raise ValueError('请使用官方 Windows x64 可嵌入 Python 包。')
        stdlib = list(runtime.glob('python3*.zip'))
        if len(stdlib) != 1:
            raise ValueError('Python 标准库文件不完整。')
        path_files[0].write_text(stdlib[0].name + '\n.\n..\n', encoding='utf-8')
        tools = root / 'tools'
        tools.mkdir()
        shutil.copy2(ffmpeg, tools / 'ffmpeg.exe')
        licenses = root / 'licenses'
        (licenses / 'Python').mkdir(parents=True)
        shutil.copy2(runtime / 'LICENSE.txt', licenses / 'Python/LICENSE.txt')
        (licenses / 'FFmpeg').mkdir()
        shutil.copy2(ffmpeg_source, licenses / 'FFmpeg' / ffmpeg_source.name)
        with tarfile.open(ffmpeg_source, 'r:xz') as archive:
            for member in archive.getmembers():
                if Path(member.name).name in {'COPYING.GPLv3', 'COPYING.GPLv2', 'COPYING.LGPLv3', 'COPYING.LGPLv2.1', 'LICENSE.md'} and member.isfile():
                    (licenses / 'FFmpeg' / Path(member.name).name).write_bytes(archive.extractfile(member).read())
        build_info = subprocess.check_output([str(ffmpeg), '-version'], text=True, encoding='utf-8', errors='replace')
        (licenses / 'FFmpeg/BUILD.txt').write_text(build_info, encoding='utf-8')
        (licenses / 'README.txt').write_text(
            'Python: official Windows embeddable distribution; original license retained.\n'
            'https://www.python.org/downloads/windows/\n'
            'FFmpeg: unmodified independent command-line tool from Gyan essentials build.\n'
            'This build enables GPLv3 features. Original license texts and FFmpeg source archive are included.\n'
            'Build configuration is recorded in FFmpeg/BUILD.txt.\n'
            'https://www.gyan.dev/ffmpeg/builds/\n'
            'https://ffmpeg.org/releases/\n'
            'Third-party library source repositories are listed by the upstream build provider.\n', encoding='utf-8')
        readme = (f'CourtCraftQA v{version} Windows 64位便携版\n\n'
                  '1. 将整个压缩包全部解压到一个可写文件夹。不要在压缩包里直接运行。\n'
                  '2. 可双击 install-shortcuts.bat 创建桌面启动、运行状态、停止快捷方式；无需管理员权限。\n'
                  '3. 双击 start.bat 或桌面“CourtCraftQA 启动”，浏览器打开 http://127.0.0.1:5012。\n'
                  '4. 左侧菜单顶部输入自己的数据目录，点击“读取”，选择回合开始核对。\n\n'
                  '内置 Python 和 FFmpeg，无须安装 Python、Conda、Excel 或额外包。\n'
                  'status.bat 查看是否运行，stop.bat 停止服务。换数据目录可直接在网页输入，无须重启。\n'
                  '动作、战术、结果各6题时配对显示1+4、2+5、3+6。Tab编辑第一个答案，Shift编辑第二个。\n'
                  '拖动左右、视频/图片或两组问答之间的分隔线；点击“全屏（F11）”增加可用空间。\n'
                  'MOV 等视频首次转换需等待；后续使用缓存。\n'
                  '若5012端口被占用，编辑自动生成的config.json，将port改为5018后再启动。\n'
                  '压缩包不含比赛数据。完整教程见 docs/quick-start.md 和 docs/user-guide.md。\n')
        (root / '先看这里.txt').write_text(readme, encoding='utf-8-sig')
        metadata = {'package': 'CourtCraftQA Windows x64', 'version': version, 'python_archive': python_zip.name,
                    'python_archive_sha256': digest(python_zip), 'ffmpeg_sha256': digest(ffmpeg),
                    'ffmpeg_source_archive': ffmpeg_source.name, 'ffmpeg_source_sha256': digest(ffmpeg_source),
                    'files': {p.relative_to(root).as_posix(): digest(p) for p in root.rglob('*') if p.is_file()}}
        (root / 'package-info.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temporary_zip = output.with_suffix(output.suffix + '.tmp')
        try:
            with zipfile.ZipFile(temporary_zip, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                for path in root.rglob('*'):
                    if path.is_file():archive.write(path, 'CourtCraftQA/' + path.relative_to(root).as_posix())
            with zipfile.ZipFile(temporary_zip) as archive:
                if archive.testzip():raise ValueError('压缩包校验失败。')
            temporary_zip.replace(output)
        finally:
            temporary_zip.unlink(missing_ok=True)
    return {'zip': str(output), 'bytes': output.stat().st_size, 'sha256': digest(output)}


def main():
    parser = argparse.ArgumentParser(description='构建含 Python 和 FFmpeg 的 Windows 便携包。')
    parser.add_argument('--python-zip', required=True)
    parser.add_argument('--ffmpeg', required=True)
    parser.add_argument('--ffmpeg-source', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--overwrite', action='store_true')
    args = parser.parse_args()
    print(json.dumps(build(args.python_zip, args.ffmpeg, args.ffmpeg_source, args.output, args.overwrite), ensure_ascii=False))


if __name__ == '__main__':
    main()
