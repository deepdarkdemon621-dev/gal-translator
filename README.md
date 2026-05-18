# Gal Translator

独立的 Galgame 文本批量翻译与外置双语字幕项目。

本仓库只放 Gal 翻译相关文件，不复用小说/EPUB 翻译项目的代码。小说翻译项目可以作为架构参考，但本项目的目标、输入源、展示方式和兼容策略独立设计。

## 当前方向

- 用户选择 Galgame 的 `exe` 或游戏目录。
- 程序扫描 exe 所在目录，自动识别常见资源包和脚本文件。
- 能预提取脚本时，使用 Codex CLI / GPT-5.5 离线批量翻译。
- 游玩时通过 Textractor/剪贴板拿到当前原文。
- 本地数据库按原文匹配译文，外置窗口即时显示双语。
- 实时阶段默认不调用 Codex，避免读一句等一句。

## MVP 边界

第一版优先验证完整链路：

1. 游戏目录扫描与诊断报告。
2. 常见脚本/资源形态识别。
3. Codex CLI 批量翻译后端。
4. 原文到译文的本地匹配索引。
5. Textractor/剪贴板输入。
6. 外置双语字幕窗口。

暂不承诺：

- 100% 自动解包所有 Galgame。
- 游戏内文本框回写。
- 自研进程 hook。
- OCR 作为主输入源。
- 对加密封包做通用破解。

## 参考游戏类型

以常见日式 Windows 硬盘版 Galgame 为参考对象，例如 9-nine- 系列、柚子社作品这类“用户只看到 exe 和若干资源包”的使用场景。

注意：具体引擎和资源格式必须以实际目录文件特征为准，不能仅凭作品名假设。

## 当前可运行功能

### 扫描诊断

```powershell
python -m gal_translator scan "D:\Games\目标游戏\game.exe"
python -m gal_translator scan "D:\Games\目标游戏"
```

输出为 UTF-8 JSON，包含：

- 输入路径和识别出的游戏根目录。
- 文件数量、目录列表、扩展名计数。
- 轻量文件清单。
- 根据 `.xp3/.rpa/.rpy/.rpyc/.ks/0.txt/nscript.dat/scenario/script` 等特征得到的候选引擎。

### 创建翻译工程

```powershell
python -m gal_translator init "D:\Games\目标游戏\game.exe"
python -m gal_translator init "D:\Games\目标游戏" --workspace "$env:LOCALAPPDATA\GalTranslator"
```

The project workspace is separate from the game folder. It stores scan reports, extracted files, scripts, logs, and future translation state under the workspace directory. The current translation direction is Japanese to Simplified Chinese (`ja` -> `zh-Hans`).

### Direct Script Import And Translation State

```powershell
python -m gal_translator import "D:\Games\目标游戏" --workspace "$env:LOCALAPPDATA\GalTranslator"
python -m gal_translator progress "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>"
python -m gal_translator batch "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --size 40
python -m gal_translator apply-result "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" ".\result.json"
python -m gal_translator lookup "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" "おはよう、先輩"
```

The current CLI flow can import directly readable scripts (`.ks/.rpy/.txt/.json/.csv`), extract likely story text, initialize translation progress, print a Codex-ready prompt, apply a strict JSON result, and look up Chinese-only runtime display text.

### Extractor Profiles

User-specific extractor profiles can be stored as JSON files under a workspace-side `extractor-profiles` directory. Example:

```json
{
  "profileId": "custom_old_gal",
  "label": "Custom old Gal profile",
  "sourceLang": "ja",
  "targetLang": "zh-Hans",
  "extensions": [".dat"],
  "directories": ["scenario"],
  "scriptGlobs": ["scenario/**/*.txt"],
  "encoding": "cp932"
}
```

Profiles are local configuration. They are intended to accumulate engine/package handling knowledge without modifying game folders.

### 运行测试

```powershell
python -m unittest discover -v
```
