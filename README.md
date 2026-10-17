# 视频转换器（VideoTool）

一个 Windows 桌面视频格式转换工具。

- **界面**：Python + PySide6（Qt Widgets），深色 / 浅色双主题
- **转换**：调用 ffmpeg 命令行，随程序内置，用户不需要自己装
- **打包**：PyInstaller，产出免安装的 exe 目录

## 功能

| 功能            | 说明                                                    |
| --------------- | ------------------------------------------------------- |
| 加载视频信息    | 分辨率、时长、大小、码率、编码格式、帧率、音轨、流统计  |
| 批量转换队列    | 一次加多个文件，按顺序自动转换，可混用不同预设          |
| 队列进度        | 每个作业独立进度条，底部显示整体统计                    |
| 缩略图          | 自动抓取一帧显示；抓到黑帧会自动换时间点重试            |
| 格式转换        | 6 种预设，见下表                                        |
| 实时进度        | 解析 ffmpeg 输出，进度条真实反映处理进度                |
| 硬件加速        | 自动探测 NVENC / Quick Sync / AMF，编码速度可快 2～3 倍 |
| 深色 / 浅色主题 | 一键切换，配色由设计令牌驱动                            |
| 记住设置        | 预设、画质、主题、硬件开关下次打开还在                  |
| 可取消          | 取消或失败时自动清理半成品文件，不留坏文件              |
| 改设置重来      | 转换完成后改预设/画质再点开始，直接按新设置重跑         |
| 覆盖确认        | 输出文件已存在时先询问，可选覆盖 / 跳过已存在 / 取消    |
| 自动建目录      | 输出目录不存在时自动创建，不用先手动建好                |
| 拖拽加载        | 拖入多个文件时，第一个进预览，其余自动排队              |
| 转换日志        | 显示实际执行的 ffmpeg 命令和输出                        |

### 转换预设

| 预设               | 说明                               |
| ------------------ | ---------------------------------- |
| MP4（H.264 + AAC） | 兼容性最好，手机、网页、播放器通吃 |
| MKV（不重编码）    | 只换封装格式，几秒完成，画质零损失 |
| WebM（VP9 + Opus） | 网页友好，同画质体积更小           |
| GIF 动图           | 取前 5 秒生成动图                  |
| MP3 音频           | 只抽出声音                         |
| M4A 音频           | 只抽出声音，Apple 系常用格式       |

MP4 / WebM 支持三档画质（高质量 / 标准 / 小体积）。

## 下载使用

不想装环境的话，直接下打包好的程序：

**[下载最新版](https://github.com/ultraplan-bit/VideoTool/releases/latest)**

解压后双击 `VideoTool.exe` 即可，**无需安装 Python 或 ffmpeg**，两者都已内置。
仅支持 Windows 64 位。

每个版本附带 `.sha256` 校验文件，可用它核对下载是否完整：

```powershell
(Get-FileHash VideoTool_v1.0.0_win64.zip -Algorithm SHA256).Hash
```

安装包由 GitHub Actions 在 windows-latest 上构建，见
[Actions 页面](https://github.com/ultraplan-bit/VideoTool/actions)。

## 从源码运行

需要 [uv](https://docs.astral.sh/uv/) 和 Python 3.10+（开发时用的是 3.14.7）。

```bash
# 1. 获取内置 ffmpeg（仓库不放二进制，约 190MB）
uv run python scripts/fetch_ffmpeg.py

# 2. 安装依赖
uv sync

# 3. 启动
uv run python -m videotool
```

## 打包

```bash
uv run python build.py
```

产物在 `dist/VideoTool/`，把整个目录一起分发，双击 `VideoTool.exe` 运行。
用 onedir 而不是 onefile：onefile 每次启动都要把几百 MB 解压到临时目录，启动要等十几秒。

## 测试

```bash
uv run python tests/make_samples.py   # 生成测试样本（首次需要）
uv run python tests/test_e2e.py       # 转换链路：探测 / 抓图 / 6 个预设真实转换
uv run python tests/test_gui.py       # 界面：加载、页面切换、批量队列、取消，并输出截图
uv run python tests/test_theme.py     # 两套主题的令牌对比度校验
uv run python tests/test_hardware.py  # 硬件编码：参数拼装 + 真实转换（无显卡则跳过）
uv run python tests/test_interaction.py  # 交互边界：竞态、取消、关窗、设置联动
uv run python tests/test_package.py   # 打包产物验证（需要先 build.py）
```

六个测试都是真跑完整流程，不是 mock（`make_samples.py` 是样本生成器、
`close_probe.py` 是子进程探针，都不算测试）。

## 代码结构

```
main.py         程序入口（打包用绝对导入，见下方说明）
src/videotool/
  app.py        主界面（导航栏、工具条、四个页面、交互逻辑）
  theme.py      设计令牌与样式表（三层令牌结构，见下）
  icons.py      矢量图标（内联 SVG + QSvgRenderer，任意颜色尺寸）
  widgets.py    可复用控件（面板、指标卡、导航项、预览区、信息行）
  jobs.py       转换作业与队列模型（状态流转、整体进度）
  ffmpeg.py     定位 ffmpeg/ffprobe，子进程调用封装
  probe.py      用 ffprobe 读取媒体信息
  thumbnail.py  抓取缩略图
  presets.py    转换预设：把"用户想干什么"翻译成 ffmpeg 参数
  worker.py     后台线程跑转换并解析进度
  util.py       数值格式化（体积、时长、码率、帧率）
build.py        打包脚本
scripts/
  fetch_ffmpeg.py  下载内置 ffmpeg
  make_icon.py     生成应用图标 assets/icon.ico
tests/
  make_samples.py  生成测试样本
  test_e2e.py      转换链路测试
  test_gui.py      界面测试（含批量队列、页面切换）
  test_theme.py    两套主题的令牌对比度校验（WCAG AA）
  test_hardware.py 硬件编码参数与真实转换
  test_interaction.py 交互边界（竞态、取消、关窗、设置联动）
  close_probe.py   关窗探针（子进程，验证不崩溃）
  test_package.py  打包产物验证（依赖是否进包、exe 能否真启动）
```

## 反复转换

转换完成后想换个格式或画质再来一遍，直接改设置点「开始转换」即可：
程序会把当前文件按新设置重新入队，不需要先清空队列。

输出文件已存在时不会静默覆盖，会先问一次。批量场景下不逐条询问
（转 20 个文件弹 20 次太烦），合并成一次提示，并提供三个选项：

- **覆盖**：全部重转
- **跳过已存在**：只转缺的，适合中断后续跑
- **取消**：什么都不做

## 硬件加速

程序启动时会在后台探测硬件编码器（NVIDIA NVENC、Intel Quick Sync、AMD AMF、
Windows Media Foundation），探测到就在输出设置里放开「硬件加速编码」勾选框。

**只检查 ffmpeg 支持哪些编码器是不够的**：构建里带了 nvenc 但机器没有 NVIDIA 显卡时，
编码器会列出却无法初始化。所以探测时会实际跑一次极短编码，能成功才认为可用。

实测对比（720p 源 → MP4 标准档，软件 CRF 23 / 硬件 CQ 27，取 ffmpeg 自报真实耗时）：

| 素材  | 软件 libx264 | 硬件 NVENC | 加速比 | 软件体积 | 硬件体积 |
| ----- | ------------ | ---------- | ------ | -------- | -------- |
| 60 秒 | 10.98s       | 3.58s      | 3.1×   | 20.0 MB  | 23.3 MB  |
| 5 秒  | 1.32s        | 0.67s      | 2.0×   | 1.65 MB  | 2.01 MB  |

硬件编码明显更快，代价是体积略大、同画质档位下画质略逊。短素材的加速比会被固定的
初始化开销摊薄，因此优势不如长素材明显。

只有 MP4 预设支持硬件加速：WebM 容器不接受 H.264，GIF / 音频 / MKV 换壳预设
不编码视频，对这些预设程序会自动忽略硬件编码器，不会拼出非法参数组合。

## 主题

深色与浅色两套主题，工具栏右上角一键切换，选择会被记住。

两套主题的配色都由同一套语义令牌驱动（见下），切换时只换令牌值，
图标和状态点会按新主题重新渲染。所有前景/背景组合的对比度都经
`tests/test_theme.py` 校验，正文不低于 4.5:1。

## 设计令牌

配色和尺寸集中在 `theme.py`，按三层组织：

```
原始值 primitive（#2563eb、12px）→ 语义 semantic（accent、fg-muted）→ 组件（按钮、表格）
```

界面代码只引用语义令牌，不出现裸色值，换主题只改一处。
所有前景/背景组合的对比度由 `tests/test_theme.py` 校验，正文不低于 4.5:1（WCAG AA）。

图标是内联 SVG 路径，用 `QSvgRenderer` 渲染，不依赖图片资源或图标字体，
可以按需取任意颜色和尺寸（例如状态列用绿色对勾、错误用红色警告）。

## 关于两个入口文件

`main.py` 和 `src/videotool/__main__.py` 都是入口，用途不同：

- 开发时用 `uv run python -m videotool`（走 `__main__.py`）
- 打包时用 `main.py`：PyInstaller 把入口文件当独立脚本执行，
  包内的 `__main__.py` 用的是相对导入（`from .app import run`），会直接报
  `ImportError: attempted relative import with no known parent package`，
  而且导入失败会让静态分析收不到 PySide6，打出一个跑不起来的包。

## ffmpeg 查找顺序

程序按以下顺序找 ffmpeg，第一个找到的生效：

1. 随程序打包的 `ffmpeg/bin/`（发布版走这条）
2. PyInstaller 解包目录
3. 系统 PATH
4. Windows 常见安装路径（`C:\ffmpeg\bin` 等）

都找不到会弹窗提示，而不是直接崩溃。

## 关于 ffmpeg 的许可证

内置的是 BtbN 的 **GPL** 构建（`ffmpeg-master-latest-win64-gpl`），
用 GPL 版是因为它含 libx264 / libx265；LGPL 版没有这两个编码器，
转 H.264 会退化成 libopenh264，画质和兼容性都更差。

程序只通过命令行调用 ffmpeg.exe，不链接它的库，属于聚合分发。
按 GPL 要求，分发时需要一起提供 ffmpeg 的许可证全文（`vendor/ffmpeg/LICENSE.txt`，
打包时会自动带上）和对应的源码获取途径（[https://github.com/BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds)）。
