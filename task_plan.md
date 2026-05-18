# Task Plan

## 当前目标

建立独立 Gal Translator 仓库，记录需求和规格，方便后续在有 Galgame 样本的本地电脑继续开发。

## 阶段 1：需求与规格

状态：complete

- [x] 独立于小说翻译项目创建仓库。
- [x] 记录产品方向。
- [x] 记录用户偏好。
- [x] 记录 MVP 范围。
- [x] 记录架构规格。

## 阶段 2：样本采集

状态：pending

- [ ] 在有 Galgame 的电脑上选择 1-2 个目标游戏。
- [ ] 导出游戏根目录顶层文件列表。
- [ ] 记录是否存在 `.xp3/.rpa/.rpy/.rpyc/.ks/0.txt/nscript.dat/scenario/script`。
- [ ] 根据文件结构确定第一批 ExtractorAdapter。

建议命令：

```powershell
Get-ChildItem "D:\Games\目标游戏" | Select-Object Name,Length,Mode
Get-ChildItem "D:\Games\目标游戏" -Recurse -File | Group-Object Extension | Sort-Object Count -Descending | Select-Object Count,Name
```

## 阶段 3：原型实现

状态：in_progress

- [x] 创建最小应用骨架。
- [x] 实现 GameScanner。
- [x] 实现 EngineDetector。
- [x] 实现一种直接脚本导入器。
- [x] 实现 CodexBatchTranslator core（batch prompt + result apply; external execution later）。
- [x] 实现本地 MatchIndex。
- [x] 实现剪贴板监听 abstraction（real OS provider later）。
- [ ] 实现外置双语窗口（CLI lookup is first UI path）。

## 阶段 4：真实游戏验证

状态：pending

- [ ] 在正式游戏电脑上 clone/pull 本仓库。
- [ ] 准备 1-2 个本地 Galgame 目录或 exe。
- [ ] 用目标游戏验证扫描结果。
- [ ] 用目标游戏验证 direct script import 或 extractor profile 命中。
- [ ] 验证文本提取覆盖率。
- [ ] 验证 Codex 批量翻译输出稳定性。
- [ ] 验证 Textractor 剪贴板输入。
- [ ] 验证匹配延迟和未匹配率。

## 当前决策

- 外置窗口优先，不做游戏内文本框回写。
- 预翻译优先，不做实时截图翻译。
- 运行时只做本地匹配，未命中不阻塞 UI。
- 用户不会手动解包，因此导入入口必须支持 exe/目录扫描和诊断。
- 当前电脑没有 Galgame 样本时，先推进可用 fixture 验证的扫描、识别、导入、匹配等核心模块。
- Local-only product: no hosted service. Game folders, tool source, and translation project workspaces stay separate.
- Current translation direction is Japanese to Simplified Chinese only (`ja` -> `zh-Hans`).
- Future spec/plan notes can be written in English for AI/tool readability.
- UI starts as CLI first.
- Translation should preserve the original Galgame style.
- Runtime subtitle display should show translated Chinese only; the game already shows the original Japanese.
- Verifiable fixture-based development is complete for direct script import, story filtering, progress, batch prompt, result apply, matching, clipboard abstraction, and CLI lookup. Real game validation is still required for engine-specific extraction profiles and real Textractor/clipboard behavior.
- Next work should resume on the formal game PC with real Galgame folders. Stop making assumptions about engine-specific extraction until scan reports from real games are available.
