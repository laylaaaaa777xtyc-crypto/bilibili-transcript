# bilibili-transcript

把 Bilibili URL 转成高质量、可阅读、可继续处理的本地文稿：**优先可靠字幕，异常或缺失时回退本机 faster-whisper ASR**。

项目保留原有 Provider 架构、字幕获取、音频下载、ASR、Markdown 草稿与 HTML 导出能力，并增加统一命令、自动输出目录、缓存、字幕可靠性检测、纯文本与规则化可读文稿。默认流程不调用任何 LLM API。

## 快速开始

要求 Python 3.9+（推荐 Python 3.10 或更新版本），ASR 路径还需要 PATH 中可用的 `ffmpeg`。建议使用虚拟环境安装：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

bili "https://www.bilibili.com/video/BV..."
# 完全等价：
python -m bilibili_transcript "https://www.bilibili.com/video/BV..."
```

安装后同时保留旧命令 `bilibili-transcript`。

## Web 图形界面

如果不想使用命令行，安装后运行：

```bash
bili-web
```

浏览器会自动打开：

```text
http://127.0.0.1:8765
```

Web 版直接复用同一套本地流水线，提供：

- Bilibili 链接 / BV 号输入；
- Whisper 模型、运行设备和浏览器 Cookie 选择；
- 可读文稿、强制 ASR、忽略缓存开关；
- 后台处理状态和运行日志；
- 历史文稿列表与正文预览；
- JSON、TXT、Markdown、SRT 和 article 文件下载；
- 桌面和手机响应式界面。

服务默认只监听本机 `127.0.0.1`。视频和文稿不会上传到 Web 前端或第三方存储。

Web 默认使用 `small` 模型，在普通 Mac 上速度和准确率更均衡。较长视频如果没有官方字幕，会下载音频并运行本地 ASR，首次运行还需要下载对应的 Whisper 模型，因此可能需要较长时间。

常用启动参数：

```bash
# 不自动打开浏览器
bili-web --no-open

# 指定端口和输出根目录
bili-web --port 9000 --output ./my-outputs
```

默认输出到 `outputs/<BV号>/`：

```text
outputs/
└── BVxxxxxxxx/
    ├── metadata.json
    ├── transcript.json
    ├── transcript.txt
    ├── transcript.md
    └── transcript.srt
```

加 `--article` 后还会生成 `article.md`：

```bash
bili "BV1xxxxxxxxx" --article
```

## 数据流与事实源

```text
Bilibili URL / BV号
  → Provider 获取元数据
  → 官方字幕 → 可靠性检测 ─┐
  → yt-dlp 字幕 → 可靠性检测 ├→ transcript.json（事实源，永不被处理层覆盖）
  → 音频下载 + faster-whisper ┘
  → RuleBasedProcessor
  → transcript.txt / article.md
```

`transcript.json` 保存原始分段、时间戳和来源信息。规则处理只生成派生文件，不会回写或润色事实源。

## 常用命令

```bash
# 默认：可靠字幕优先，缺失/异常时 ASR
bili "BV1xxxxxxxxx"

# 生成规则整理后的可读文稿
bili "BV1xxxxxxxxx" --article

# 忽略字幕，使用 faster-whisper
bili "BV1xxxxxxxxx" --force-asr --model small --device auto

# 登录态字幕
bili "BV1xxxxxxxxx" --cookies-from-browser chrome

# 只保存事实源 JSON
bili "BV1xxxxxxxxx" --json-only

# 更换输出根目录，仍自动创建 <BV号> 子目录
bili "BV1xxxxxxxxx" --output ./my-outputs

# 忽略缓存并重新获取字幕/ASR
bili "BV1xxxxxxxxx" --refresh

# 多 P 视频只处理第 2 P
bili "BV1xxxxxxxxx" --part 2
```

完整帮助：

```bash
bili --help
```

### 兼容旧 CLI

旧式直接输出目录仍然可用：

```bash
python -m bilibili_transcript "BV1xxxxxxxxx" -o case_outputs/BV1xxxxxxxxx
python -m bilibili_transcript transcript "BV1xxxxxxxxx" -o case_outputs/BV1xxxxxxxxx
```

`-o/--out-dir` 被解释为直接目录，并额外保留 `{BV号}_transcript.json`、`{BV号}_transcript.md` 和原结构化成稿 Markdown。新参数 `--output` 则表示输出根目录。

## 缓存

当目标目录已有 `transcript.json`（也兼容旧名 `{BV号}_transcript.json`）时，默认直接读取缓存，不访问 Bilibili、不下载音频、不运行 ASR。这样可以快速重复生成派生文件：

```bash
bili "BV1xxxxxxxxx" --article
```

只有显式传入 `--refresh` 才重新走字幕/ASR 链路。

Web 任务还会复用已经成功下载的音频。如果字幕或 ASR 阶段失败，再次提交同一视频时不会重复下载完整音频。

## 输出说明

| 文件 | 用途 |
|---|---|
| `metadata.json` | 标题、UP 主、时长、分 P 等元数据 |
| `transcript.json` | 不可覆盖的事实源：原始 segments、时间戳、来源和检测结果 |
| `transcript.txt` | 无时间戳的纯文本，清理空格、合并短字幕并自然分段 |
| `transcript.md` | 保留时间范围的原有 Markdown 草稿格式 |
| `transcript.srt` | 标准 SRT 字幕 |
| `article.md` | `--article` 生成的规则化可读文稿 |

## 字幕可靠性检测

官方字幕与 yt-dlp 字幕在被接受前会经过 `SubtitleValidator`。第一阶段的 `BasicSubtitleValidator` 检查：

- 字幕为空或有效文字过少；
- 单条字幕长度异常；
- 大量重复句；
- 负数、倒序或结束早于开始的时间戳；
- 长视频对应的字幕字数明显过少。

检测失败时不保存该字幕为事实源，而是继续尝试下一种字幕来源或回退 ASR。检测结果会写入 `part_sources[].validation`。

如果 Bilibili 的 JSON 元数据接口返回 HTTP 412，工具会自动从公开视频页内嵌数据恢复标题、aid、cid、时长和分 P 信息，不会因此直接终止任务。

## 可靠音频下载

长视频的 DASH 音频可能因为网络波动出现 `IncompleteRead` 或连接中断。下载器不会立即放弃并转向 yt-dlp，而是：

1. 读取服务器返回的完整文件大小；
2. 使用固定大小的 HTTP Range 分片下载；
3. 严格校验每片的 `Content-Range` 起止位置和字节数；
4. 连接中断时只重试当前分片；
5. 主 CDN 失败后继续尝试备用 CDN；
6. 所有分片完成后再交给 ffmpeg 转码。

这能避免长连接中断后从零下载，也能防止错误拼接产生时长不完整的音频。

## 可读文稿处理层

处理层与 ASR 完全分离：

```python
class TranscriptProcessor:
    def process(self, transcript: Transcript) -> ProcessedTranscript:
        ...
```

当前 `RuleBasedProcessor` 是保守的确定性实现，只做空格清理、连续重复句移除、碎片合并、自然分段和明显标点归一，不改变事实含义。

项目也预留了与供应商无关的接口：

```python
class LLMClient(Protocol):
    def complete(self, prompt: str) -> str:
        ...

class LLMProcessor(TranscriptProcessor):
    ...
```

仓库只提供 `MockLLMClient` 供测试和集成示例使用，不绑定 OpenAI、Claude、Gemini 或 Ollama。

## 现有 Provider 与字幕策略

每个分 P 独立判断：

1. Bilibili 官方 CC（WBI `x/player/wbi/v2`）；
2. 使用 `--cookies-from-browser` 或 `--ytdlp-subs` 时尝试 yt-dlp 字幕；
3. 下载音轨并运行本机 faster-whisper。

部分字幕只在登录态返回。可使用 `--cookies-from-browser chrome`；macOS 可能需要给终端完全磁盘访问权限。

增加新来源时，实现并注册 `TranscriptProvider` 即可，下游缓存和 formatter 不依赖 Bilibili：

```text
bilibili_transcript/providers/
  base.py       TranscriptProvider、VideoMeta、SourceRecord
  bilibili.py   当前 Bilibili 实现
  __init__.py   Provider 注册表
```

## HTML 导出与旧成稿流程

原有莫兰迪 HTML 导出仍保留：

```bash
bili export-html path/to/成稿.md
```

AI 编程助手成稿流程仍记录在 `.cursor/skills/bilibili-transcript-finalize/SKILL.md`。它与新的本地 `article.md` 不冲突：前者适合人工/AI 深度成稿，后者是无 LLM、可重复生成的基础可读版。

## 故障排查

### 页面显示“处理失败”

展开页面中的“查看运行日志”。新版 Web 界面会直接显示后台最后一条错误，并提供“使用相同设置重试”。修改代码或升级安装后，需要停止并重新启动 `bili-web`。

### `HTTP 412: Precondition Failed`

- 元数据接口的 412 会自动切换到公开视频页数据；
- yt-dlp 仍可能被 Bilibili 返回 412，但默认 DASH 下载不依赖 yt-dlp；
- 登录后才显示的字幕可尝试 `--cookies-from-browser chrome`，或在 Web 页面选择浏览器 Cookie。

### `IncompleteRead` / `ChunkedEncodingError`

新版下载器会自动按校验分片重试。不要手动删除已完成的 MP3；Web 重试会优先复用它。

### `NotOpenSSLWarning`

这是 macOS 自带 Python 3.9 与新版 urllib3 的兼容性警告，不代表任务失败。推荐通过 Homebrew 或 pyenv 使用 Python 3.10+ 创建虚拟环境。

### 长视频需要多久

有官方字幕时通常只需数秒到数分钟。没有字幕时，耗时取决于视频长度、Whisper 模型和设备；CPU 转写长视频可能需要数十分钟。Web 默认使用 `small` 模型，并在任务日志中显示当前阶段。

## 开发与测试

所有单元测试使用固定数据，不访问真实 Bilibili：

```bash
pip install -e ".[dev]"
pytest
```

测试覆盖原有 Provider/formatter，以及缓存命中、`--refresh`、短字幕合并、重复句清理、字幕异常判断、HTTP 412 元数据 fallback、校验式音频分片续传、Web API、TXT/SRT 和 article 输出。

## 主要代码结构

```text
bilibili_transcript/
  cli.py              CLI 编排、缓存使用、自动输出目录、Rich UI
  web.py              本地 Web API、后台任务和安全文件下载
  web_static/         响应式 Web 前端
  providers/          来源 Provider 抽象与 Bilibili 实现
  subtitles.py        官方字幕与 yt-dlp 字幕
  validation.py       SubtitleValidator
  download.py         音频下载与 ffmpeg 转码
  transcribe.py       faster-whisper ASR
  models.py           Transcript / ProcessedTranscript
  processor.py        RuleBasedProcessor / LLMProcessor 抽象
  formatters.py       TXT / article / SRT formatter
  cache.py            transcript.json 缓存读取
  draft_md.py         原有时间分块 Markdown
  finalize_md.py      原有结构化成稿 Markdown
  export_html.py      原有莫兰迪 HTML 导出
```
