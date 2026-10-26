CourtCraftQA 篮球问答人工核对工具

仓库：https://github.com/D-dragon5/CourtCraftQA（私有仓库，需访问权限）
项目说明：README.md
完整使用教程：docs/user-guide.md
现场演示顺序：docs/demo-guide.md
虚构 JSON 示例：examples/qa.example.json 与 examples/README.md

日常使用：
1. 完整Windows便携包已内置Python和视频转换程序，无须另装环境；源码版需自行准备Python 3.10或以上版本。
2. 将文件全部解压，双击 start.bat，首次自动生成空目录配置。
3. 在网页侧栏顶部输入实际数据目录并点击读取；默认端口5012。
4. 使用结束双击 stop.bat。最简教程见 docs/quick-start.md。

演示使用：
python scripts/prepare_demo.py "D:\basketball-data\C251"
python token_viewer.py --config demo-config.json
也可用 start-demo.bat / stop-demo.bat，演示端口 5016。
准备脚本不会覆盖已经存在的演示目录或配置。

源 qa.json 保留；有实际修改时写入唯一 qa-new.json。
无改动不生成新版；已有新版先对比，再选择保留或备份后删除。
先看清对照和清理按钮，再按 + 确认。

远程访问先复制 remote.example.json 为 remote.json 并填写配置，
验证常规 SSH 登录后使用 open-48g.bat。远程端口须与服务器一致。
本机与服务器使用独立数据副本，编辑结果不会自动互相同步。
