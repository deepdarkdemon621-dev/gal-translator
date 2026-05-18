# Findings

## 已确认

- 现有小说翻译项目可作为概念参考：离线切分、队列、LLM 翻译、状态管理。
- Gal 项目需要独立仓库，不应混入 EPUB/小说翻译实现。
- 用户当前主要可用后端是 Codex CLI。
- `codex exec` 支持非交互调用、`--ephemeral`、`-m <model>`、`--output-schema`、`-o <file>`。
- 用户倾向使用 `gpt-5.5`。
- 用户不会手动解包游戏。
- 用户接受 Textractor/剪贴板作为第一版运行时当前文本来源。
- 用户倾向外置双语窗口。

## 设计判断

- Galgame 文本文件位置和格式不统一，不能承诺一个通用路径。
- 游戏内文本框双语回写复用性低，放到后续高级功能。
- 窗口截图/OCR 实时翻译速度和准确性都不适合作为主流程。
- 预提取脚本 + 离线批量翻译 + 运行时本地匹配，能满足速度要求。
- 无法解包时应给诊断报告，并允许进入剪贴板采集/补库模式。
- 没有真实 Galgame 样本不是原型阻塞点；GameScanner、EngineDetector、直接脚本导入、MatchIndex、剪贴板输入都可以先用 fixture 驱动开发。
- Windows 用户目录可能包含非 ASCII 字符，CLI 输出诊断 JSON 时应固定 UTF-8，避免路径损坏。
- The app should remain local-only. Codex CLI / Claude Code may use the network, but Gal Translator should not require a hosted backend.
- Translation projects must be stored outside the game directory, with extracted files and translation state under a workspace such as `%LOCALAPPDATA%\GalTranslator`.
- The initial language pair is fixed to Japanese source and Simplified Chinese target.
- English docs/spec text is acceptable and preferred for future AI-facing implementation notes.
- Initial UI should be CLI-first.
- Translation style should preserve the original Galgame tone and writing style rather than flattening into generic prose.
- Subtitle output should display Chinese translation only by default because the game already shows the Japanese source text.

## 待验证

- 9-nine- 系列和柚子社目标样本的实际文件结构。
- 常见硬盘版中 `.xp3`、`.rpa`、`.ks` 等格式覆盖率。
- Codex CLI 在大批量台词 JSON 输出下的稳定性和最佳批大小。
- Textractor 输出与脚本原文之间的差异程度。
- 模糊匹配阈值与误匹配风险。
