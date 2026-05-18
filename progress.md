# Progress

## 2026-05-18

- 创建独立仓库：`C:\Programming\gal-translator`。
- 初始化 git 仓库。
- 写入项目 README。
- 写入仓库协作说明 `AGENTS.md`。
- 写入需求文档 `docs/requirements.md`。
- 写入规格文档 `docs/spec.md`。
- 写入恢复用计划文件 `task_plan.md`。
- 写入调研记录 `findings.md`。

## 下一步

在有 Galgame 样本的本地电脑上收集目标游戏目录结构，不需要解包。

建议先收集：

```powershell
Get-ChildItem "D:\Games\目标游戏" | Select-Object Name,Length,Mode
Get-ChildItem "D:\Games\目标游戏" -Recurse -File | Group-Object Extension | Sort-Object Count -Descending | Select-Object Count,Name
```

拿到文件列表后，决定第一批实现 Ren'Py、Kirikiri、NScripter 还是直接脚本导入。

## 2026-05-18 原型开发

- 确认当前电脑没有 Galgame 样本时仍可推进无样本核心模块。
- 选择 Python 3 作为第一批核心扫描/识别库实现，暂不引入第三方依赖。
- 新增 `gal_translator.scanner.GameScanner`，支持 exe 输入时以 exe 所在目录作为游戏根目录，并生成轻量扫描报告。
- 新增 `gal_translator.detector.EngineDetector`，基于 `.xp3/.rpa/.rpy/.rpyc/.ks/0.txt/nscript.dat/scenario/script` 等特征输出候选引擎。
- 新增 `python -m gal_translator scan <exe-or-dir>` CLI，输出 UTF-8 JSON 诊断报告。
- 新增 `tests/test_scanner_detector.py` 和 `tests/test_cli.py`，用临时目录 fixture 验证扫描、识别和 CLI 输出。
- 更新 `README.md` 记录扫描诊断命令和测试命令。

### 测试结果

```powershell
python -m unittest discover -v
```

结果：3 个测试通过。

### 下一步

- 实现一种直接脚本导入器，优先支持 `.ks/.rpy/.txt` fixture。
- 然后实现基础 ScriptParser，把直接脚本文本转成统一台词条目。

## 2026-05-18 Local Project Workspace

- Updated requirements/spec for a local-only tool model.
- Recorded the fixed initial language pair: Japanese to Simplified Chinese (`ja` -> `zh-Hans`).
- Added `TranslationProjectManager` to create isolated per-game project workspaces under a caller-provided workspace root.
- Added `ExtractorProfileRegistry` with a built-in `direct_script` profile for `.ks/.rpy/.txt/.json/.csv` scripts and `scenario/` or `script/` directories.
- Added `python -m gal_translator init <exe-or-dir> [--workspace <dir>]`.
- Noted that future AI-facing specs and plans can be written in English.

### Test Result

```powershell
python -m unittest discover -v
```

Result: 6 tests passed.

## 2026-05-18 Verifiable CLI Pipeline

- Added `DirectScriptImporter` for directly readable script files.
- Added `ScriptParser` and `StoryTextFilter` for fixture-based `.ks/.rpy/.txt` story extraction and system-text filtering.
- Added `python -m gal_translator import <exe-or-dir> [--workspace <dir>]`, which creates `story-entries.json` and `translation-state.json`.
- Added `TranslationProgressTracker` and `python -m gal_translator progress <project-root>`.
- Added `CodexBatchTranslator` core for pending batch selection, Galgame-style Japanese-to-Simplified-Chinese prompt generation, and JSON result application.
- Added `python -m gal_translator batch <project-root> --size <n>` and `python -m gal_translator apply-result <project-root> <result.json>`.
- Added `MatchIndex`, `RuntimeSubtitleService`, and `python -m gal_translator lookup <project-root> <text>` for translated-Chinese-only runtime output.
- Added `ClipboardRuntimeInput` abstraction with duplicate/empty text suppression; real OS clipboard provider remains a later integration point.
- Added JSON extractor profile loading via `ExtractorProfileRegistry.from_directories(...)`, so local engine/import knowledge can be accumulated outside the game folder.
- Added `CodexCliInvocation` for local verification of the `codex exec --ephemeral -m gpt-5.5 --output-schema ... -o ... -` command shape and output schema generation.

### Test Result

```powershell
python -m unittest discover -v
```

Result: 22 tests passed.

## Next Session Goal

Resume on the formal game PC with actual Galgame files.

Concrete next steps:

1. Pull or clone the repository.
2. Run `python -m unittest discover -v` to confirm the environment.
3. Run `python -m gal_translator scan <game-exe-or-dir>` on 1-2 real games.
4. Save the scan JSON and inspect candidate engines/profiles.
5. Try `python -m gal_translator import <game-exe-or-dir> --workspace <workspace-dir>` for directly readable scripts.
6. If the game uses packaged resources, create or adjust an extractor profile based only on the actual file structure and tool output.
7. Validate Codex CLI batch size and JSON stability with real story entries.
8. Validate Textractor/clipboard output against imported story text.

Current stopping point: all fixture-verifiable development is complete; real game validation is now required.
