# Gal Translator Spec

## 产品形态

Gal Translator 是一个面向 Galgame 的本地辅助翻译工具。它不直接嵌入游戏文本框，而是在外部显示双语字幕。核心策略是“预翻译为主，运行时匹配为主”。

工具不做线上服务。游戏、工具和翻译工程目录分离：用户提供本地游戏 `exe` 或目录，工具在单独的翻译工程目录中保存扫描报告、解包产物、脚本文本、翻译进度和匹配数据库，不写回游戏目录。

当前翻译方向只考虑日文到中文。The initial UI is CLI-first. Runtime subtitle display should show translated Chinese only by default because the game already displays the Japanese source. Translation prompts should preserve the original Galgame tone and style.

## 总体架构

```text
Game exe / folder
  -> GameScanner
  -> EngineDetector
  -> TranslationProject
  -> ExtractorProfileRegistry
  -> ExtractorRunner
  -> ExtractorAdapter
  -> ScriptParser
  -> StoryTextFilter
  -> TranslationProject DB
  -> CodexBatchTranslator
  -> ProgressTracker
  -> MatchIndex
  -> ClipboardRuntimeInput
  -> BilingualSubtitleWindow
```

## 模块

### GameScanner

输入：用户选择的 `exe` 或目录。

行为：

- 如果输入是 exe，使用 exe 所在目录作为游戏根目录。
- 扫描同级文件和常见子目录。
- 记录文件名、扩展名、大小、相对路径。
- 不读取大文件全文，先做轻量识别。

输出：`scanReport`。

### EngineDetector

根据文件特征判断候选引擎/格式，不仅依赖作品名。

初始规则：

- 出现 `.xp3`：候选 Kirikiri/KAG 系。
- 出现 `.rpa/.rpy/.rpyc`：候选 Ren'Py。
- 出现 `0.txt` 或 `nscript.dat`：候选 NScripter/ONScripter。
- 出现 `.ks`：候选 KAG 脚本。
- 出现 `scenario/`、`script/`：候选可直接解析脚本目录。

输出：候选列表和置信度，不做绝对承诺。

### TranslationProject

翻译工程是每个游戏的一份本地工作目录，和游戏目录分离。

建议默认根目录：

```text
%LOCALAPPDATA%\GalTranslator\projects\<project-id>\
  project.json
  scan-report.json
  extracted\
  scripts\
  db\
  logs\
```

`project.json` 记录：

- 工程 ID 和名称。
- 原始游戏路径。
- 源语言 `ja`。
- 目标语言 `zh-Hans`。
- 扫描摘要。
- 使用的 extractor profile。
- 当前阶段和进度摘要。

### ExtractorProfileRegistry

管理可复用的解包/导入配置。内置通用 profile 放在仓库中，本机积累的 profile 放在用户数据目录。

```text
profiles/extractors/
%LOCALAPPDATA%\GalTranslator\extractor-profiles\
```

profile 记录：

- `profileId`：如 `direct_script`、`kirikiri_xp3`、`renpy_rpa`。
- 检测规则：扩展名、目录名、文件名。
- 解包命令模板：外部 CLI 工具及参数。
- 解包产物 glob：在哪里找脚本。
- 编码：如 `utf-8`、`shift_jis`、`cp932`。
- 剧情文本过滤规则。
- 已验证样本说明。

### ExtractorRunner

根据扫描结果和 profile 执行导入或外部解包。

原则：

- 解包输出写入翻译工程的 `extracted/`，不写回游戏目录。
- 直接脚本可复制或索引到 `scripts/`。
- 外部工具失败时记录命令、退出码、stderr 和建议。
- 不处理 DRM 绕过，不承诺破解加密封包。

### ExtractorAdapter

负责从资源包或脚本目录得到可解析脚本。

MVP 适配策略：

- 直接脚本：`.ks/.rpy/.txt/.json/.csv` 可直接传给解析器。
- 封包脚本：优先集成外部 CLI 解包器，避免重写复杂解包算法。
- 加密或未知封包：输出 unsupported 诊断，不阻断后续剪贴板采集模式。

ExtractorAdapter 由 ExtractorProfileRegistry 和 ExtractorRunner 驱动；新类型 Gal 的处理经验应沉淀为 profile，方便下次复用。

### ScriptParser

把不同脚本格式转为统一条目：

```json
{
  "id": "relative/path/file.ks:120",
  "source": "……あんた、本気で言ってるの？",
  "speaker": "美咲",
  "file": "relative/path/file.ks",
  "line": 120,
  "contextBefore": ["前一句"],
  "contextAfter": ["后一句"],
  "metadata": {
    "engine": "kirikiri",
    "kind": "dialogue"
  }
}
```

解析器应保留文件路径和行号，方便诊断、去重、后续回写。

### StoryTextFilter

过滤 ScriptParser 产出的条目，只保留剧情文本。

默认保留：

- 角色对白。
- 旁白。
- 可在剧情中显示的选择项。

默认排除：

- 系统设置。
- 菜单、按钮、存档/读档界面文本。
- 配置项、调试字符串。
- 纯脚本命令和控制标签。

无法确定的条目标记为 `unknown`，不默认批量翻译。

### CodexBatchTranslator

使用 Codex CLI / Claude Code 作为离线批量翻译后端，当前目标只做日译中。

推荐调用形态：

```powershell
codex exec --ephemeral -m gpt-5.5 --output-schema schema.json -o result.json -
```

原则：

- Codex 只负责翻译，不直接修改游戏文件。
- 应用控制批次、重试、缓存和 JSON 校验。
- 每批建议 20-80 条，实际按 token 和输出稳定性调优。
- 输出必须带回原始 `id`。
- 翻译未完成不影响游戏启动和字幕窗口启动。

输出 schema：

```json
{
  "type": "object",
  "required": ["items"],
  "properties": {
    "items": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "translation"],
        "properties": {
          "id": { "type": "string" },
          "translation": { "type": "string" },
          "notes": { "type": "string" }
        }
      }
    }
  }
}
```

### MatchIndex

运行时用于从当前原文找到译文。

匹配顺序：

1. 原文 hash 精确匹配。
2. normalized 原文匹配。
3. 最近上下文辅助匹配。
4. 模糊匹配。
5. 未匹配。

### ProgressTracker

记录翻译任务进度，支持中断后恢复。

基础统计：

- 总剧情条目数。
- 已翻译条目数。
- 失败条目数。
- 当前批次编号。
- 最近错误。
- 当前阶段：`scanned`、`extracted`、`parsed`、`translating`、`ready`、`partial`、`failed`。

Normalization 包含：

- 去除首尾空白。
- 合并多余换行。
- 统一全角/半角空格。
- 统一常见日文标点差异。
- 去掉脚本控制符和 Textractor 可能产生的重复片段。

### ClipboardRuntimeInput

第一版运行时输入依赖 Textractor 或类似工具把当前游戏文本复制到剪贴板。

行为：

- 监听剪贴板变化。
- 防抖，避免重复刷新。
- 记录上一句，用于上下文匹配。
- 不在主线程调用 Codex。

### BilingualSubtitleWindow

外置双语字幕窗口。

MVP 功能：

- 显示原文和译文。
- 可置顶。
- 可调字号、透明度、宽度。
- 可隐藏原文或译文。
- 显示匹配状态：命中、模糊命中、未匹配。
- 未匹配时显示原文，不等待翻译。

Default display mode should show Chinese translation only. Source Japanese can remain an optional debug view later.

实现可先用桌面壳或本地 Web UI 验证；如果普通浏览器无法满足置顶需求，后续考虑 Tauri/Electron。

## 数据模型草案

```text
projects
  id
  name
  gameRoot
  projectRoot
  sourceLang
  targetLang
  detectedEngine
  extractorProfileId
  status
  createdAt
  updatedAt

script_entries
  id
  projectId
  source
  normalizedSource
  sourceHash
  speaker
  file
  line
  contextBefore
  contextAfter
  metadata

translations
  id
  entryId
  targetLang
  text
  status
  provider
  model
  error
  updatedAt

runtime_events
  id
  projectId
  rawClipboardText
  normalizedText
  matchedEntryId
  matchType
  createdAt

extractor_profiles
  id
  profileId
  source
  matchRules
  commandTemplate
  scriptGlobs
  encoding
  storyFilterRules
  verifiedSamples

translation_batches
  id
  projectId
  batchNumber
  totalItems
  translatedItems
  failedItems
  status
  error
  updatedAt
```

## 失败策略

- 扫描不到脚本：给出扫描报告和可疑文件列表。
- 识别到封包但无法解包：说明候选引擎、资源包名、原因。
- Codex 输出 JSON 无效：重试该批，超过次数后标记失败。
- 翻译缺项：只重试缺失 ID。
- 运行时未匹配：立即显示原文和未匹配状态，可选加入待补翻队列。
- 翻译未完成：工程状态为 `partial`，已翻译部分仍可用于运行时匹配。

## MVP 验收

1. 能从用户选择的 exe/目录生成扫描诊断。
2. 能创建独立翻译工程目录，不修改游戏目录。
3. 能导入至少一种直接脚本格式。
4. 能过滤出剧情文本并跳过系统文本。
5. 能通过 Codex CLI / Claude Code 批量日译中导入条目。
6. 能显示并持久化翻译进度。
7. 能监听剪贴板并本地匹配译文。
8. 能在外置窗口双语显示命中结果。
9. 未匹配或未翻译时不阻塞显示。

## 后续扩展

- Ren'Py `.rpy/.rpyc/.rpa` 专用适配。
- Kirikiri `.xp3/.ks` 专用适配。
- NScripter 适配。
- 术语表、人名表和角色口吻配置。
- Qwen/Ollama 本地粗翻模式。
- 脚本回写/patch 生成，但仅作为高级功能。
