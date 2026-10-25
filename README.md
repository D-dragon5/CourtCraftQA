# CourtCraftQA

篮球视频问答的人工核对工具。视频、标注图片、当前问答和人物事件参考在同一页展示，支持逐题编辑、源 JSON 只读定位、逐字差异核对，以及确认后另存新版。

- [完整使用教程](docs/user-guide.md)：安装、日常核对、快捷键、保存规则和故障处理。
- [现场演示流程](docs/demo-guide.md)：8–10 分钟操作顺序、3 分钟简版和现场恢复方案。
- [JSON 示例](examples/qa.example.json) 与 [数据格式说明](examples/README.md)：使用虚构内容说明问答结构。

## 快速开始

需要 Python 3.10 或以上版本和桌面浏览器。Python 后端与 Excel 读取仅使用标准库，无额外 Python 包；MOV、MKV、AVI 转码需要 FFmpeg。MP4、WebM、M4V 直接交给浏览器播放，仍需编码兼容。

```powershell
git clone https://github.com/D-dragon5/CourtCraftQA.git
cd CourtCraftQA
Copy-Item config.example.json config.json
```

这是私有仓库，下载需使用有访问权限的 GitHub 账号。编辑 `config.json`，例如：

```json
{
  "data_root": "D:/basketball-data",
  "host": "127.0.0.1",
  "port": 5012,
  "ffmpeg": "",
  "cache_dir": "cache",
  "backups_dir": "backups"
}
```

`data_root` 必须存在。Windows 路径可用 `/` 或双反斜杠。`ffmpeg` 留空时自动查找项目的 `tools/ffmpeg.exe` 或系统 PATH，也可填完整路径。缓存、备份的相对路径按项目目录解析。

Windows 双击 `start.bat` 启动，访问 <http://127.0.0.1:5012>；双击 `stop.bat` 关闭本项目服务。也可在终端运行：

```sh
python token_viewer.py --config config.json
```

Linux 使用 `python3`。地址中的端口随实际配置变化，终端会显示运行地址和数据目录。

## 数据目录

每个回合独立一个文件夹，程序递归索引视频，并读取视频同目录的附件：

```text
basketball-data/
  C251/
    original.mp4
    action_boxes.jpg
    tactic_boxes.jpg
    outcome_boxes.jpg
    qa.json
    source_PL_label.xlsx
  C252/
    original.mov
    qa.json
    ...
```

问答支持 `prediction` 各阶段的 `qa` 和 `review` 复盘题，题数按文件内容显示。源文件示例见 [examples](examples/README.md)。仓库不包含比赛视频、真实标注、人物表或真实比赛截图，使用者自行准备有权使用的数据。

## 核对流程

1. 鼠标移到左边缘或点菜单选择回合；列表可固定。已有 `qa-new.json` 时优先读取新版。
2. 同屏查看视频与当前标注图，逐题核对选择题或开放答案；问题和答案都可编辑。
3. 人名参考自动匹配同目录 Excel，显示人物、原始时间、事件、结果及工作表行号；无匹配且表格正常时显示小龙与 `dddlong`。
4. 悬停“源 JSON”查看完整只读源文件，自动定位当前问题，也可固定侧栏。
5. 打开“对照并保存”，按题目查看红色删除、绿色新增和替换明细；点击改动卡片回题编辑，用“本题改动”再次核对。
6. 确认保存整个回合后进入下一回合；列表末尾完成核对。仅切题不会写盘。

答案编辑状态会高亮。单按 Shift 进入或退出；编辑中需按住 Shift 加快捷键。修改答案在结束编辑、切题或对照前清除空格、换行、制表符等空白，包括英文词语间空格。未修改和精确恢复的原答案保留原值。

## 保存和恢复规则

- 原始 `qa.json` 保留，实际改动写入同目录唯一的 `qa-new.json`，后续继续更新它；更新前备份。
- 相对源文件没有内容改动时，不创建或覆盖新版。缩进、排版和对象字段顺序变化不算标注修改。
- 已有新版与源件相同，会提示是否保留或备份后删除。恢复源内容后若旧版仍有修改，先列出旧版差异，再由操作者选择。
- “恢复源 JSON”恢复整个回合的页面内容，确认前不改磁盘，并提供单步“撤销恢复”；继续编辑后该撤销入口结束。
- 保存、清理前核验文件版本；文件已被其他程序更新时停止操作，当前编辑保留。缺少源文件时无法做源件比较、恢复或源件依据的清理。
- 默认备份在 `backups/`；找回方法见 [使用教程](docs/user-guide.md#7-恢复源内容和找回备份)。局部查看“本题改动”时，保存仍作用于整个回合。

## 快捷键

| 按键 | 操作 |
| --- | --- |
| Enter | 下一题，最后一题打开对照 |
| Q / Backspace | 上一题 |
| 【 / 】，兼容 [ / ] | 上下回合 |
| 空格 | 视频播放 / 暂停 |
| J | 跳到当前阶段截断点并播放 |
| A / D | 跳到截断点前 / 后两秒并播放 |
| ← / →，小键盘 4 / 6 | 相对当前位置前后微调 0.3 秒 |
| ↑ / ↓，小键盘 8 / 2 | 音量增减 5% |
| X | 放大当前图片 |
| +，含小键盘加号 | 打开对照；再次按确认保存或跳过；清理提示中确认备份删除 |
| Shift 单按 | 切换答案编辑状态 |
| Esc | 关闭弹窗或返回编辑 |

答案编辑中使用 Shift 加相应快捷键；搜索框、其他输入框和弹窗遵循自己的输入规则。使用 `+` 前应先看清当前确认按钮的含义。

## 准备演示副本

从一个包含源 `qa.json` 和视频的回合生成四个独立场景，原回合及已有新版不改动：

```powershell
python scripts/prepare_demo.py "D:\basketball-data\C251"
python token_viewer.py --config demo-config.json
```

也可用 `start-demo.bat` / `stop-demo.bat` 启停，访问 <http://127.0.0.1:5016>。四个场景依次为 `01-C251-edit`、`02-C251-clean`、`03-C251-duplicate`、`04-C251-saved`，用于展示编辑、无改动、重复新版和旧版已有修改。

准备脚本拒绝覆盖已有演示目录或配置，重新准备时选择新的 `--output` 与 `--config`。现场按 [演示流程](docs/demo-guide.md) 操作。

## Linux 服务和远程访问

服务器代码放在 `~/CourtCraftQA`，配置好服务器自己的数据路径。服务模板默认使用 `/usr/bin/python3` 和 `%h/CourtCraftQA`；路径或解释器不同时，先修改模板再安装：

```sh
mkdir -p ~/.config/systemd/user
cp scripts/biao-basketball-qa.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now biao-basketball-qa.service
systemctl --user status biao-basketball-qa.service
```

本机复制 `remote.example.json` 为 `remote.json`，填写服务器地址、密钥路径和端口。先用常规 SSH 验证主机密钥和密钥登录，再双击 `open-48g.bat`。它通过 SSH（安全外壳协议）回环转发，让电脑浏览器访问服务器页面。

`remote_port` 必须与服务器 `config.json` 的 `port` 一致：远程配置示例为 5014，服务配置示例默认 5012，使用前统一设置。转发示例本机端口为 15014；服务器和本机服务均保持监听 `127.0.0.1`。

页面令牌用于请求校验，不提供多用户账号鉴权。服务按单人核对设计；需要远程访问时使用 SSH 转发。本机和服务器的数据副本不会自动同步，先确认入口和文件路径，再开始标注。

## 代码和验证

```text
token_viewer.py / excel_reference.py   后端 配置与只读人物表解析
viewer.html / static/                 页面 样式和交互
assets/                               小龙图标
docs/ / examples/                     教程 演示流程和虚构示例
scripts/ / tests/                     演示准备 服务模板和检查
```

```sh
python -m unittest discover -s tests -p "test_*.py"
python tests/smoke_checks.py token_viewer.py
python tests/runtime_checks.py http://127.0.0.1:5012
```

前两项使用临时夹具，不写正式数据；最后一项只读检查已运行服务。仓库不上传实际配置、演示数据、比赛数据、备份、缓存、日志、私人密钥或 `tools/` 下的外部程序。
