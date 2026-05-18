# Repository Instructions

本仓库是 Galgame 翻译器项目，和 `C:\Programming\translator` 的小说/EPUB 翻译项目分离。

## Scope

- 只添加 Gal 翻译相关文档、代码、测试和资源。
- 不复制小说翻译项目代码，除非用户明确要求迁移某个模块。
- 需求讨论和规格文档优先放在 `docs/`。
- 开发恢复信息维护在根目录：
  - `task_plan.md`
  - `findings.md`
  - `progress.md`

## Product Direction

- 主线是预提取脚本、Codex CLI 离线批量翻译、本地匹配、外置双语字幕窗口。
- 不把游戏内文本框回写作为 MVP。
- 不把 OCR/实时 Codex 翻译作为默认体验。
- 任何针对具体 Gal 引擎的判断都必须来自实际文件结构或可验证工具输出。

## Safety

- 不处理 DRM 绕过。
- 不承诺破解加密封包。
- 对无法提取的游戏输出诊断报告，并提供 Textractor/剪贴板采集模式作为兜底。
