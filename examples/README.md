# CourtCraftQA 数据格式示例

本目录使用虚构题目和人物说明文件结构。将自己的视频、标注图、`qa.json` 和 `source_PL_label.xlsx` 放入同一个回合文件夹，配置 `data_root` 指向这些回合的父目录。

## 源 JSON

[`qa.example.json`](qa.example.json) 包含三个预测阶段和三道复盘题，共七道格式示例题。实际题数不限于这个例子，页面按文件内容显示。

| 字段 | 含义 |
| --- | --- |
| `prediction` | 阶段对象列表 |
| `prediction[].type` | 阶段名，常用 `action`、`tactic`、`outcome` |
| `prediction[].cutoff_seconds` | 该阶段的截断时间，单位为秒，使用数值 |
| `prediction[].image` | 同目录的标注图片文件名 |
| `prediction[].qa` | 当前阶段的问答列表 |
| `question`、`answer` | 问题和答案字符串 |
| `review` | 复盘问答列表 |

选择题选项按独立行写入 `question`，例如 `A. 传给队友`、`B. 直接投篮`。至少有两个可识别选项时，页面显示为可点击的选择题。开放题直接填写问题和答案。其他全局字段和阶段字段可在“更多”中核对。

把示例复制为某个自备回合里的 `qa.json` 后，记得将截断时间、图片名和题目改成与该回合相符的内容。程序保留源文件，修改另存为 `qa-new.json`。

## 人物事件表

文件名为 `source_PL_label.xlsx`。工作表的表头至少包含准确拼写的 `Player Name`（人物姓名），其他列按下表识别。可以有多个工作表，页面会保留原始工作表和行号。

| 列名 | 中文含义 | 虚构值 |
| --- | --- | --- |
| `Event` | 事件标记 | `E01` |
| `Event Classification` | 事件分类 | `Dribble`（运球） |
| `Player Name` | 人物姓名 | `Demo Guard` |
| `Time` | 原始时间标记 | `0:00/2:10` |
| `Result` | 结果 | `success`（成功） |
| `Core Event` | 核心事件 | 空值 |
| `Highlight` | 重点标记 | 空值 |
| `Caption` | 补充描述 | `虚构格式示例` |

[`source_PL_label.example.csv`](source_PL_label.example.csv) 提供两行虚构数据，便于查看列名。应用读取 `.xlsx`；如从此 CSV 开始，可在 Excel 或 WPS 中打开后另存为 `source_PL_label.xlsx`，放在回合目录。程序不要求本机安装 Excel。

时间字段按原表文本显示，不自动推断帧号或换算到视频时间。当前姓名匹配以拉丁字母姓名为主，支持完整姓名、同表唯一姓氏以及空格清理后的完整姓名；参考记录仍需人工确认。
