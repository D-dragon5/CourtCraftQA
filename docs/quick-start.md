# CourtCraftQA Windows 快速使用

## 使用 Windows 便携包

适用于 Windows 10 或 Windows 11 的 64 位电脑。完整便携包内置 Python 运行环境和视频转换程序，无须安装 Python、pip、Conda 或 Microsoft Excel，也无须手动设置转换程序路径。

1. 收到 `CourtCraftQA-Windows-x64.zip` 后，右键选择“全部解压”。保留解压后的完整目录，直接打开文件夹操作，不要在压缩包预览窗口里运行。
2. 双击解压目录中的 `start.bat`。首次启动会自动生成配置和空数据目录，浏览器打开 <http://127.0.0.1:5012>。
3. 点击左上角菜单，展开侧栏。在“数据目录”中填写自己存放回合的文件夹完整路径，点击“读取”或按 Enter。
4. 选择一个回合，开始核对视频、标注图、问题、答案和人物记录。需要换数据时，直接在侧栏改目录，无须重启。
5. 核对修改后点击“对照并保存”。原始 `qa.json` 保留，实际改动写入同目录的 `qa-new.json`；无改动时跳过保存。
6. 使用结束后双击 `stop.bat`。仅关闭浏览器页面，后台服务仍可能继续运行。

便携包不包含比赛视频和真实标注。请使用自己的数据，每个回合单独一个文件夹，放入视频、`qa.json`、标注图片，以及可选的 `source_PL_label.xlsx`。缺少人物表时仍可核对问答。

```text
basketball-data/
  C001/
    original.mp4
    qa.json
    action_boxes.jpg
    tactic_boxes.jpg
    outcome_boxes.jpg
    source_PL_label.xlsx
  C002/
    ...
```

## 常见情况

- **第一次打开是空列表：** 在侧栏填入实际数据目录并点击“读取”。程序会递归查找其中的回合，没有 50 个目录的上限。
- **MOV 等视频首次打开稍慢：** 等待首次转换完成，后续会使用缓存。MP4 能否直接播放也取决于视频编码。
- **提示 5012 端口已使用：** 先确认之前的 CourtCraftQA 是否仍在运行。需要换端口时，关闭本项目，打开 `config.json`，将 `port` 改为例如 `5018`，保存后重新双击 `start.bat`，浏览器会打开对应地址。
- **新增回合没有立即出现：** 点击侧栏“刷新列表”。每页显示 40 个视频，列表到底后连续向下滚轮两次可进入下一页。

依赖和随附工具的许可说明放在便携包的 `licenses/` 目录。

## 使用 GitHub 源码版

源码版需自行安装 Python 3.10 或以上版本；Python 代码只使用标准库，无须运行 pip 或安装 Conda、Excel。Windows 下载并完整解压源码后，双击 `start.bat`；首次也会自动生成配置和空数据目录，再到侧栏填写实际数据路径。

源码仓库不附带 Python 运行环境和 FFmpeg。需要播放 MOV、MKV、AVI 时，另行提供 FFmpeg，可放在项目的 `tools/ffmpeg.exe`，或在配置中填写路径。命令行启动和其他设置见 [完整使用教程](user-guide.md)。

日常核对操作见 [使用教程](user-guide.md)，现场介绍可按 [演示流程](demo-guide.md) 操作。
