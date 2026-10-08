# BiliScribe

> Bilibili 视频转高质量可读文稿：可靠字幕优先，本地 Whisper 兜底。

[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-56%20passed-brightgreen)](#开发与测试)

BiliScribe 是一个本地运行的 Bilibili 文稿提取工具。输入视频链接或 BV 号，它会自动解析视频、查找字幕、检测字幕质量，并在字幕不可用时调用 faster-whisper 进行语音识别，最终生成 JSON、纯文本、Markdown、SRT 和可读文章。

项目同时提供简洁的命令行和本地 Web 图形界面。整个处理过程在自己的电脑上完成，不需要注册账号，也不会把视频、音频或文稿上传到第三方服务。

## 目录

- [为什么做 BiliScribe](#为什么做-biliscribe)
- [功能亮点](#功能亮点)
- [环境要求](#环境要求)
- [安装](#安装)
- [快速开始](#快速开始)
- [输出文件](#输出文件)
- [CLI 使用指南](#cli-使用指南)
- [字幕可靠性检测](#字幕可靠性检测)
- [可读文稿处理](#可读文稿处理)
- [下载与 ASR](#下载与-asr)
- [多 P 视频](#多-p-视频)
- [HTML 导出](#html-导出)
- [Web API](#web-api)
- [架构](#架构)
- [故障排查](#故障排查)
- [开发与测试](#开发与测试)
- [隐私与安全](#隐私与安全)
- [路线图](#路线图)
- [许可证](#许可证)

## 为什么做 BiliScribe

Bilibili 视频里的知识常常比标题和简介丰富，但视频并不适合快速检索、引用、归档或二次整理。直接依赖自动字幕又会遇到几个实际问题：部分视频没有字幕、登录后才能看到字幕、AI 字幕可能与内容不匹配，以及长视频下载容易因网络波动失败。

BiliScribe 把这些步骤组合成一条稳定的本地流水线：

- 有可靠字幕时直接使用，速度快且避免不必要的 ASR；
- 字幕缺失或明显异常时自动回退到本地 Whisper；
- 原始转写永远保存在 `transcript.json`，不会被整理层覆盖；
- 已完成的转写自动缓存，重复生成文稿时不再下载和识别；
- 长音频使用带校验的分片下载，降低中途断线导致的失败概率；
- CLI 和 Web 使用同一套处理能力，输出结果完全一致。

## 功能亮点

### 一条命令完成视频转文稿

```bash
bili "https://www.bilibili.com/video/BV..." --article
```

工具会自动完成视频解析、字幕获取、质量检测、必要时的音频下载与 ASR，以及多种格式的导出。

### 字幕优先，ASR 自动兜底

每个分 P 独立执行以下策略：

1. 获取 Bilibili 官方 CC 字幕；
2. 检测字幕是否为空、过短、重复或时间戳异常；
3. 按需尝试 yt-dlp 字幕；
4. 没有可靠字幕时下载音频并运行 faster-whisper。

也可以使用 `--force-asr` 跳过字幕，强制进行本地语音识别。

### 原始事实与可读文稿分离

```text
Bilibili URL / BV号
        │
        ▼
  字幕获取 / 本地 ASR
        │
        ▼
 transcript.json  ← 原始事实源，始终保留
        │
        ▼
 RuleBasedProcessor
        │
        ├── transcript.txt
        └── article.md
```

`transcript.json` 保留原始文本、时间戳、分 P 和来源信息。`article.md` 是从事实源派生的可读版本，两者职责清晰，后续无论接入搜索、知识库还是 LLM，都不需要牺牲原始数据。

### 本地 Web 工作台

运行 `bili-web` 后，浏览器中可以直接：

- 粘贴 Bilibili 链接或 BV 号；
- 选择 Whisper 模型和运行设备；
- 选择浏览器 Cookie 来源；
- 开启可读文稿、强制 ASR 或忽略缓存；
- 查看后台阶段、实时日志与错误信息；
- 浏览历史文稿和正文预览；
- 下载 JSON、TXT、Markdown、SRT 和 article 文件。

服务默认只监听 `127.0.0.1`，适合在个人电脑上安全使用。

## 环境要求

- Python 3.9 或更高版本，推荐 Python 3.10+
- ffmpeg：只有进入 ASR 音频处理流程时需要
- 网络连接：用于访问 Bilibili；首次运行 ASR 时还需要下载 Whisper 模型
- 可选的 NVIDIA CUDA：可显著加快长视频转写

检查环境：

```bash
python3 --version
ffmpeg -version
```

macOS 可以通过 Homebrew 安装 ffmpeg：

```bash
brew install ffmpeg
```

Ubuntu / Debian：

```bash
sudo apt update
sudo apt install ffmpeg
```

## 安装

克隆自己的仓库并进入项目目录：

```bash
git clone https://github.com/laylaaaaa777xtyc-crypto/bilibili-transcript.git
cd bilibili-transcript
```

推荐在虚拟环境中安装：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
```

Windows PowerShell 激活命令：

```powershell
.venv\Scripts\Activate.ps1
pip install -e .
```

安装完成后会提供三个入口：

| 命令 | 说明 |
|---|---|
| `bili` | 推荐的命令行入口 |
| `bilibili-transcript` | 完整名称入口，与 `bili` 等价 |
| `bili-web` | 启动本地 Web 图形界面 |

## 快速开始

### 使用命令行

```bash
bili "https://www.bilibili.com/video/BV1xxxxxxxxx"
```

也可以直接输入 BV 号：

```bash
bili "BV1xxxxxxxxx"
```

生成经过规则整理的可读文稿：

```bash
bili "BV1xxxxxxxxx" --article
```

如果终端暂时找不到 `bili`，可以使用完全等价的模块入口：

```bash
python -m bilibili_transcript "BV1xxxxxxxxx" --article
```

### 使用 Web 界面

```bash
bili-web
```

程序会自动打开浏览器。也可以手动访问：

```text
http://127.0.0.1:8765
```

停止服务时回到运行它的终端，按 `Control + C`。

常用 Web 启动参数：

```bash
# 启动后不自动打开浏览器
bili-web --no-open

# 修改端口
bili-web --port 9000

# 修改输出根目录
bili-web --output ./my-outputs

# 同时指定监听地址、端口和输出目录
bili-web --host 127.0.0.1 --port 9000 --output ./my-outputs
```

## 输出文件

默认情况下，每个视频使用独立目录：

```text
outputs/
└── BVxxxxxxxx/
    ├── metadata.json
    ├── transcript.json
    ├── transcript.txt
    ├── transcript.md
    ├── transcript.srt
    └── article.md          # 使用 --article 时生成
```

各文件用途：

| 文件 | 内容与用途 |
|---|---|
| `metadata.json` | 视频标题、UP 主、时长、aid、分 P 和简介等元数据 |
| `transcript.json` | 原始事实源，保存 segments、时间戳、来源及字幕检测结果 |
| `transcript.txt` | 去掉时间戳、清理空格、合并短字幕后的纯文本 |
| `transcript.md` | 按时间范围组织的 Markdown 草稿，便于定位视频内容 |
| `transcript.srt` | 标准字幕文件，可导入播放器和剪辑软件 |
| `article.md` | 无时间戳的规则化可读文稿，由 `--article` 生成 |

音频仅在需要 ASR 时下载到对应视频目录，`.gitignore` 已避免把音频和输出目录意外提交到 Git。

## CLI 使用指南

查看完整帮助：

```bash
bili --help
```

### 常用示例

```bash
# 默认流程：可靠字幕优先，必要时自动 ASR
bili "BV1xxxxxxxxx"

# 同时生成 article.md
bili "BV1xxxxxxxxx" --article

# 强制跳过字幕并进行 ASR
bili "BV1xxxxxxxxx" --force-asr

# 选择 Whisper 模型和运行设备
bili "BV1xxxxxxxxx" --force-asr --model small --device auto

# 读取 Chrome 登录 Cookie，尝试获取登录态字幕
bili "BV1xxxxxxxxx" --cookies-from-browser chrome

# 官方字幕不可用时，额外尝试 yt-dlp 字幕
bili "BV1xxxxxxxxx" --ytdlp-subs

# 强制使用 yt-dlp 下载音频
bili "BV1xxxxxxxxx" --force-asr --ytdlp

# 只保存 transcript.json
bili "BV1xxxxxxxxx" --json-only

# 忽略已有缓存并重新处理
bili "BV1xxxxxxxxx" --refresh

# 多 P 视频只处理第 2 P
bili "BV1xxxxxxxxx" --part 2

# 修改输出根目录，结果写入 my-outputs/BV1xxxxxxxxx/
bili "BV1xxxxxxxxx" --output ./my-outputs
```

### 参数说明

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--output DIR` | `outputs` | 输出根目录，内部自动创建 BV 号子目录 |
| `-o, --out-dir DIR` | 无 | 直接指定输出目录的兼容模式 |
| `--part N` | 全部分 P | 只处理第 N 个分 P |
| `--article` | 关闭 | 生成 `article.md` |
| `--json-only` | 关闭 | 只保存原始 JSON，不生成派生格式 |
| `--refresh` | 关闭 | 忽略 `transcript.json` 缓存并重新获取 |
| `--force-asr` | 关闭 | 跳过字幕，直接使用 faster-whisper |
| `--prefer-subtitles` | 开启 | 优先使用通过检测的字幕 |
| `--no-prefer-subtitles` | — | 不优先使用字幕 |
| `--model MODEL` | `medium` | Whisper 模型，例如 `small`、`medium`、`large-v3` |
| `--device DEVICE` | `auto` | `auto`、`cpu` 或 `cuda` |
| `--compute-type TYPE` | 自动 | 例如 `int8`、`float16`、`float32` |
| `--language CODE` | `zh` | Whisper 语言代码 |
| `--no-vad` | 关闭 | 禁用 Whisper VAD 静音过滤 |
| `--skip-download` | 关闭 | ASR 时复用目录中已有 MP3 |
| `--ytdlp` | 关闭 | 强制使用 yt-dlp 下载音频 |
| `--ytdlp-subs` | 关闭 | 尝试使用 yt-dlp 获取字幕 |
| `--cookies-from-browser` | 无 | 从指定浏览器读取 Cookie |
| `--chunk-span SEC` | `300` | `transcript.md` 每个时间块的最大跨度 |

Web 界面默认使用 `small` 模型，以兼顾普通电脑上的速度与准确率；CLI 默认使用 `medium`。

### 缓存行为

当目标目录中已经存在 `transcript.json` 时，再次运行相同视频会直接读取缓存：

```bash
bili "BV1xxxxxxxxx" --article
```

上面的命令可以基于已有事实源生成 `article.md`，不会重新访问 Bilibili、下载音频或运行 ASR。只有加入 `--refresh` 才会重新执行获取流程：

```bash
bili "BV1xxxxxxxxx" --article --refresh
```

Web 任务还会传入 `--skip-download`。如果转写阶段失败但 MP3 已完整下载，使用相同链接重试时可以直接复用音频。

### 浏览器 Cookie

部分字幕只在登录状态下返回。这种情况可以让工具读取本机浏览器 Cookie：

```bash
bili "BV1xxxxxxxxx" --cookies-from-browser chrome
```

可选来源包括 Chrome、Chromium、Brave、Edge、Firefox、Safari、Opera 和 Vivaldi。macOS 可能会提示钥匙串授权，或要求给终端“完全磁盘访问权限”。Cookie 只由本地依赖读取并用于当前请求，不会保存到文稿中。

## 字幕可靠性检测

获取到字幕不代表字幕一定可信。BiliScribe 在接受字幕前会通过 `SubtitleValidator` 检查：

- 字幕是否为空；
- 有效文字是否过少；
- 单条字幕长度是否异常；
- 是否包含大量重复句；
- 时间戳是否为负数、倒序或结束早于开始；
- 长视频的字幕字数是否明显不足。

检测结果包含 `valid`、`confidence` 和 `reason`，并记录在 `transcript.json` 的 `part_sources[].validation` 中。字幕明显异常时，流水线不会把它当作事实源，而是继续尝试其他来源或自动回退 ASR。

该检测层是保守的规则判断，不使用 Whisper 做语义比对，也不会修改字幕内容。

## 可读文稿处理

ASR/字幕获取与文本整理是两个独立阶段：

```python
class TranscriptProcessor:
    def process(self, transcript: Transcript) -> ProcessedTranscript:
        ...
```

当前的 `RuleBasedProcessor` 是确定性、无 LLM 的实现，负责：

- 清理连续空格和中文标点旁的多余空格；
- 合并过短的碎片字幕；
- 删除连续重复句；
- 根据句号、时间间隔、长度和分 P 合理分段；
- 归一明显重复的标点。

它不会总结、改写观点或补充原文中不存在的信息。

项目已经定义供应商无关的 LLM 扩展接口：

```python
class LLMClient(Protocol):
    def complete(self, prompt: str) -> str:
        ...

class LLMProcessor(TranscriptProcessor):
    ...
```

因此未来可以接入 OpenAI、Claude、Gemini 或 Ollama，而不需要修改字幕和 ASR 流水线。当前仓库不绑定任何 LLM 服务，只提供 `MockLLMClient` 用于测试和集成示例。

## 下载与 ASR

### 可靠音频下载

长视频的 DASH 音频可能因网络波动出现 `IncompleteRead`、`ChunkedEncodingError` 或连接中断。BiliScribe 的下载器会：

1. 确认远端文件大小；
2. 使用固定大小的 HTTP Range 分片下载；
3. 校验每个分片的 `Content-Range` 和实际字节数；
4. 连接中断时只重试当前分片；
5. 主 CDN 失败后尝试备用 CDN；
6. 完整下载后再交给 ffmpeg 转成 MP3。

这样既避免长连接失败后从零开始，也能防止错误拼接产生不完整音频。

### Whisper 模型选择

| 模型 | 速度 | 资源占用 | 适用场景 |
|---|---|---|---|
| `tiny` / `base` | 最快 | 最低 | 快速试跑、清晰普通话 |
| `small` | 较快 | 较低 | Web 默认，日常使用 |
| `medium` | 中等 | 中等 | CLI 默认，更注重准确率 |
| `large-v3` | 最慢 | 最高 | 高准确率、机器性能充足 |

`--device auto` 会在 PyTorch 可用且检测到 CUDA 时选择 `cuda`，否则使用 `cpu`。默认计算类型为 CUDA `float16`、CPU `int8`，也可以通过 `--compute-type` 手动指定。

## 多 P 视频

BiliScribe 会读取视频分 P 列表并逐 P 处理。每个 segment 会记录所属 `part`，合并后重新生成连续的 segment ID。只想处理其中一 P 时使用：

```bash
bili "BV1xxxxxxxxx" --part 2
```

字幕质量检测和 ASR 回退按分 P 独立执行，因此同一个视频中可以同时存在字幕来源和 ASR 来源。

## HTML 导出

项目支持把结构化成稿 Markdown 导出为单页 HTML：

```bash
bili export-html path/to/视频_transcript_成稿.md
```

传入包含 `*_transcript_成稿.md` 的目录也可以：

```bash
bili export-html path/to/output-directory
```

默认导出后自动在浏览器打开，使用 `--no-open` 可以关闭自动打开：

```bash
bili export-html path/to/成稿.md --no-open
```

`.cursor/skills/bilibili-transcript-finalize/` 中还提供了适合 AI 编程助手使用的深度成稿工作流。它与 `article.md` 互不冲突：`article.md` 是无 LLM、可重复生成的基础可读版，深度成稿则适合需要摘要、结构重组或人工审校的场景。

## Web API

Web 界面由 FastAPI 提供本地 API。启动 `bili-web` 后可访问交互式文档：

```text
http://127.0.0.1:8765/api/docs
```

主要端点：

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/health` | 健康检查 |
| `POST` | `/api/jobs` | 创建转写任务 |
| `GET` | `/api/jobs/{job_id}` | 查询任务状态与日志 |
| `GET` | `/api/results` | 列出本地历史结果 |
| `GET` | `/api/results/{video_id}` | 获取文稿详情与预览 |
| `GET` | `/api/results/{video_id}/files/{filename}` | 下载指定结果文件 |

任务在后台线程中调用同一个 Python CLI 模块，因此 Web 层不会复制或分叉核心转写逻辑。

## 架构

```text
bilibili_transcript/
├── cli.py              CLI 编排、Rich 状态和自动输出目录
├── web.py              FastAPI 本地服务、任务管理和文件下载
├── web_static/         原生 HTML / CSS / JavaScript Web 界面
├── providers/
│   ├── base.py         TranscriptProvider、VideoMeta、SourceRecord
│   └── bilibili.py     Bilibili 元数据、字幕和音频实现
├── bvid.py             BV 号识别与提取
├── meta.py             视频元数据与 HTTP 412 页面回退
├── wbi.py              Bilibili WBI 签名
├── subtitles.py        官方字幕和 yt-dlp 字幕解析
├── validation.py       SubtitleValidator 与基础可靠性检测
├── download.py         DASH 音频、校验式分片下载和 ffmpeg 转码
├── transcribe.py       faster-whisper ASR
├── models.py           Transcript / ProcessedTranscript 数据模型
├── processor.py        RuleBasedProcessor 和 LLM 扩展抽象
├── formatters.py       TXT、SRT 和 article 格式化
├── cache.py            transcript.json 缓存加载
├── draft_md.py         时间分块 Markdown
├── finalize_md.py      结构化成稿 Markdown
└── export_html.py      单页 HTML 导出
```

### Provider 扩展

视频来源能力由 `TranscriptProvider` 抽象。Provider 负责识别输入、获取元数据、选择分集、获取字幕和下载音频；缓存、处理器和 formatter 只依赖统一的数据结构。

新增视频来源时，实现 Provider 并在 `providers/__init__.py` 注册即可，无需重写下游处理逻辑。

## 故障排查

### Web 页面显示“处理失败”

展开页面中的运行日志，最后一条通常包含实际原因。修改代码或重新安装后，需要先停止旧服务，再运行：

```bash
bili-web
```

如果浏览器保留了旧页面，可以刷新页面后重新提交任务。

### `HTTP 412: Precondition Failed`

Bilibili 的 JSON 元数据接口偶尔会返回 412。工具会自动尝试从公开视频页内嵌数据恢复标题、aid、cid、时长和分 P 信息。

yt-dlp 仍可能独立遇到 412。默认 DASH 下载不依赖 yt-dlp；如果视频或字幕要求登录，可以尝试：

```bash
bili "BV1xxxxxxxxx" --cookies-from-browser chrome --refresh
```

### `yt-dlp returned non-zero exit status 1`

先不要强制使用 `--ytdlp`。默认下载器会从 Bilibili DASH 地址分片下载，并在主地址失败后尝试备用地址。若视频需要登录，再加入浏览器 Cookie。

### `IncompleteRead` / `ChunkedEncodingError`

下载器会自动按分片校验和重试。重新执行同一任务即可；Web 会尽量复用已经完整下载的 MP3。不要使用不完整的同名音频冒充成功结果。

### 没有获取到官方字幕

这可能表示视频确实没有字幕，也可能是字幕只对登录用户返回。尝试：

```bash
bili "BV1xxxxxxxxx" --cookies-from-browser chrome --refresh
```

仍然没有可靠字幕时，工具会自动进入 ASR，不需要手动切换。

### `ffmpeg` 不存在

确认命令可以在当前终端中执行：

```bash
ffmpeg -version
```

安装 ffmpeg 后重新打开终端、激活虚拟环境，再执行任务。

### `NotOpenSSLWarning`

这是部分 macOS 自带 Python 3.9 使用 LibreSSL 时，urllib3 发出的兼容性警告，通常不代表任务失败。推荐安装 Python 3.10+ 后重新创建虚拟环境。

### 长视频需要多久

有可靠字幕时，通常只需数秒到数分钟。没有字幕时，耗时取决于视频长度、模型和硬件：CPU 转写一小时以上的视频可能需要数十分钟，首次使用某个 Whisper 模型还要额外下载模型文件。

### 如何彻底重新处理

使用 `--refresh` 忽略 transcript 缓存：

```bash
bili "BV1xxxxxxxxx" --refresh --article
```

如果还需要重新下载音频，可先确认目标，再手动移走对应输出目录中的 MP3。

## 开发与测试

安装开发依赖：

```bash
pip install -e ".[dev]"
```

运行全部测试：

```bash
pytest
```

当前测试覆盖：

- Provider 识别、元数据与字幕路径；
- 缓存命中和 `--refresh`；
- 短字幕合并、重复句清理和自然分段；
- 字幕为空、过短、重复和时间戳异常；
- TXT、SRT、Markdown 与 article 输出；
- HTTP 412 元数据页面回退；
- 校验式音频分片下载与失败恢复；
- Web 任务、结果列表、预览和文件下载；
- CLI 向后兼容行为。

测试使用固定 fixture 和 mock，不会访问真实 Bilibili。

运行 CLI 帮助检查：

```bash
bili --help
bili-web --help
```

## 隐私与安全

- 默认 Web 服务只监听本机，不对局域网或公网开放；
- 视频音频、Cookie 和输出文稿不会上传到本项目维护的服务器；
- 浏览器 Cookie 仅在用户明确指定时读取；
- 下载接口只允许访问白名单中的结果文件名；
- BV 号和输出路径会经过校验，避免任意文件路径访问；
- `outputs/`、音频文件和本地环境文件默认不提交到 Git。

如果主动把 `--host` 改为 `0.0.0.0`，服务可能对局域网可见。请只在可信网络中这样做，并自行配置访问控制。

## 路线图

- 接入可选的 OpenAI、Claude、Gemini 和 Ollama 客户端；
- 增加更细致的字幕/音频一致性检测；
- 提供更丰富的文章模板与导出格式；
- 扩展更多视频和播客 Provider；
- 优化超长视频的断点续传与任务恢复。

## 许可证

本项目使用 MIT License。你可以自由使用、修改和分发，但请保留许可证与版权声明。

## 项目维护

BiliScribe 由 [Asuka](https://github.com/laylaaaaa777xtyc-crypto) 维护。

如果遇到问题或有功能建议，请在 [GitHub Issues](https://github.com/laylaaaaa777xtyc-crypto/bilibili-transcript/issues) 中提交，并尽量附上：

- 使用的操作系统和 Python 版本；
- 执行的完整命令（请隐藏个人 Cookie 信息）；
- 错误日志的最后一段；
- 视频是否需要登录或大会员权限；
- 问题能否通过 `--refresh` 重现。
