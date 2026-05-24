# Findings

## 2026-05-24 Pause Finding

- The current practical product route is confirmed: pre-extracted Artemis scripts provide the local translation-state base, while LunaHook/source-log capture drives scoped translation and an external subtitle window during play.
- Translating the whole imported archive is not necessary for the MVP loop and is token-expensive. At pause time the project is intentionally partial: `6950/32978` translated, `26028` pending, `0` failed.
- The latest active loop proves the desired closed loop without global archive translation:
  - LunaHook bridge captures runtime text into `lunahook-source.txt`.
  - The source-log watcher matches the line to an imported Artemis id.
  - The watcher translates only encountered source-log entries when needed.
  - The subtitle window displays the matched Chinese-only subtitle.
- Latest active report: `logs\source-log-session-20260524-225357-report.json`.
- Latest proof line: `窶補輔≠縺ゅ∝､ｱ謨励＠縺溘Ａ` matched `script/01_01繝励Ο繝ｭ繝ｼ繧ｰ_01.ast:143` and displayed `窶披泌賦蝠奇ｼ梧裾遐ｸ莠・Ａ`.
- LunaHook was used as a capture provider from the local LunaTranslator installation, not as a translation backend, not as OCR, and not as in-game text rewrite.
- Clipboard bridging should stay opt-in because it can capture unrelated clipboard noise; LunaHook/source-log is the cleaner path for the current `selectoblige.exe` sample.

## 2026-05-24 Persistent Source-Log Session Finding

- `scripts/source-log-session.ps1` can start the paused-full-archive runtime loop for the persistent Artemis project without touching unrelated pending entries.
- Current real session report: `logs\source-log-session-20260524-210406-report.json`.
- `session-info` confirms watcher pid 11584 and subtitle-window pid 43600 are active.
- The running session processed a real already-translated source-log append:
  - Appended source: `「これが最後の質問だ」`.
  - Matched id: `script/01_01プロローグ_01.ast:16`.
  - Watcher cycle: 349.
  - Result: `translation_ready`, `scopedTranslatedCount=1`, `plannedBatchCount=0`, `executedBatchCount=0`.
  - Subtitle event: `matchType=exact`, `visible=true`, `missLogged=false`.
  - Project progress remained 6,950 translated, 26,028 pending, 0 failed.
- The watcher is currently idle again with `reason=log_unchanged`; this is expected while waiting for more appended runtime text in `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\lunahook-source.txt`.
- The active watcher command is cost-controlled: `--only-new-log-entries`, `--size 1`, `--max-batches 1`, and no `--watch-require-ready`.
- A bounded startup report (`logs\source-log-session-20260524-210145-report.json`) showed the empty-log case exits cleanly with no stderr and `sessionSummary.status=no_new_log_entries`.
- On Windows, starting the hidden watcher can leave the parent PowerShell invocation with empty captured stdout even though the report file is written and the child processes start. Treat `sessionReportPath` plus `python -m gal_translator session-info <report>` as the authoritative recovery path.
- `session-info` now keeps `stdout.lastProcessedEvent` and `statusSummary.lastProcessed*` fields, so the most recent processed source-log result remains visible after many later idle watcher cycles.

## 2026-05-24 Source-Log Live Reload Finding

- The complete local feedback loop now works in a running subtitle window with a source log:
  - source-log append while subtitle-window is open;
  - subtitle-window records the line as unmatched and writes it to miss-log;
  - background scoped `translate-log --watch --only-new-log-entries` translates the log-referenced pending Artemis entry;
  - subtitle-window reloads `translation-state.json` and refreshes the previous unmatched source to exact visible Chinese.
- Real proof line:
  - Entry id: `script/01_06奏命編_01.ast:4545`
  - Source: `どれだけ心が荒れ狂っていたとしても、殺意を明確に抱いた瞬間、何もかもが冷え切っていく。`
  - Translation: `无论内心如何狂乱翻涌，在明确怀抱杀意的那一瞬间，一切都彻底冷却了。`
- Subtitle event sequence in `logs\live-reload-smoke-subtitle-events.jsonl`:
  - unmatched event: empty text, invisible, `missLogged=true`;
  - reload event: translated Chinese text, `matchType=exact`, `visible=true`, `missLogged=false`.
- Watcher event in `logs\live-reload-smoke-watcher-stdout.jsonl` shows `existingLogEntryIds=["script/01_06奏命編_01.ast:4545"]`, `appliedCount=1`, and scope progress ready.
- Persistent Artemis project state after this proof is 6,950 translated, 26,028 pending, 0 failed.

## 2026-05-24 Scoped Miss Closed-Loop Finding

- `translate-log --only-new-log-entries` must scope to log-referenced entries, not only newly appended entries. In an Artemis import project, most runtime miss text already exists in `translation-state.json` as pending script text, so append count can be 0 while there is still exactly one relevant pending entry to translate.
- The scoped behavior now reports `logEntryIds` and `existingLogEntryIds`; real verification translated existing pending id `script/01_06奏命編_01.ast:4529` without touching the rest of the 26,030 global pending entries.
- Real scoped line translated successfully:
  - Source: `本当の殺意とは……心が底冷えしていくものだと、誰かが言っていた。`
  - Translation: `真正的杀意……有人说过，是会让内心寒彻骨髓的东西。`
- Runtime verification passed through `lookup`, `replay-log`, `subtitle-window --dry-run`, and a real self-closing Tk subtitle window. The subtitle event log recorded Chinese text with `matchType=exact`, `visible=true`, and `missLogged=false`.
- Persistent Artemis project state after this proof is 6,949 translated, 26,029 pending, 0 failed.

## 2026-05-24 Cost-Control Translation Finding

- Current real Artemis script translation state is 6,948 translated, 26,030 pending, 0 failed, out of 32,978 total entries.
- Full pretranslation of the remaining 26,030 entries is possible but token-expensive and no longer the default recommendation for the MVP play loop.
- Important implementation finding: the older `translate-log` path appended miss/source log entries but then translated the project's global pending queue. On a large imported Artemis project this could spend tokens on arbitrary archive entries instead of the newly encountered play text.
- `translate-log --only-new-log-entries` now scopes Codex batches to entries referenced by that invocation. Generated miss-log and source-log watcher commands use this flag by default.
- Real-project dry-run confirmed the guard: an already-known line produced `addedEntryCount=0`, `sessionSummary.status=no_new_log_entries`, global pending still 26,030, scoped pending 0, and no first batch.
- Recommended operating model is now: keep translated entries as the local base, play through Hook/source-log/subtitle-window, collect encountered text into miss/source logs, and translate only log-referenced entries.

## 2026-05-24 Real Hook Findings

- 2026-05-24 latest translation continuation: the persistent Artemis script project is now at 6,308 translated entries, 26,670 pending, and 0 failed after another `--size 40 --max-batches 16 --timeout 600` run.
- In this run the assistant shell wrapper timed out, but the background `translate-all` process continued, completed all 16 batches, and removed its translation lock. The original summary file is empty; `logs\translate-all-summary-20260524T192139-recovered.json` records the recovered final state and latest batch metadata.
- The newest verified `01_05過去編_05ah` sample, `「やめ、ばかっ、おぉい！！」`, speaker `凪`, matches locally to `「住手，笨蛋，喂！！」` through lookup, replay-log, and subtitle-window dry-run preview with source hidden.
- 2026-05-24 latest translation continuation: the persistent Artemis script project is now at 5,668 translated entries, 27,310 pending, and 0 failed after another stable `--size 40 --max-batches 16 --timeout 600` run.
- The newest verified `01_04イヴ編_10` sample, `「お、おう。分かった」`, speaker `凪`, matches locally to `「哦、哦。明白了」` through lookup, replay-log, and subtitle-window dry-run preview with source hidden.
- 2026-05-24 latest translation continuation: the persistent Artemis script project is now at 5,028 translated entries, 27,950 pending, and 0 failed after another stable `--size 40 --max-batches 16 --timeout 600` run.
- The newest verified `01_04イヴ編_06_2` narration sample, `こんなにも容易く、二人きりになれるとは思っていなかった。`, matches locally to `没想到竟然这么轻易就能变成两人独处。` through lookup, replay-log, and subtitle-window dry-run preview with source hidden.
- 2026-05-24 latest translation continuation: the persistent Artemis script project is now at 4,388 translated entries, 28,590 pending, and 0 failed after another stable `--size 40 --max-batches 16 --timeout 600` run.
- The newest verified `01_04イヴ編_03` sample, `「ならんわ！！」`, speaker `凪`, matches locally to `「才不会啊！！」` through lookup, replay-log, and subtitle-window dry-run preview with source hidden.
- 2026-05-24 latest translation continuation: the persistent Artemis script project is now at 3,748 translated entries, 29,230 pending, and 0 failed after another stable `--size 40 --max-batches 16 --timeout 600` run.
- The newest verified `01_03くくる編_06` sample, `「っ……」`, speaker `くくる`, matches locally to `「唔……」` through lookup, replay-log, and subtitle-window dry-run preview with source hidden.
- 2026-05-24 latest translation continuation: the persistent Artemis script project is now at 3,108 translated entries, 29,870 pending, and 0 failed after another stable `--size 40 --max-batches 16 --timeout 600` run.
- The latest run applied all 16 batches cleanly, and the last batch used `result_ready_process_stopped`, so the early complete-result detection path continues to work during real Codex translation.
- The newest verified `01_03くくる編_03_1` sample, `「妙案を思いついたぞ、くくる」`, speaker `凪`, matches locally to `「我想到个妙计了，库库露」` through lookup, replay-log, and subtitle-window dry-run preview with source hidden.
- 2026-05-24 latest translation continuation: the persistent Artemis script project is now at 2,468 translated entries, 30,510 pending, and 0 failed after retrying the two previously failed entries and translating 38 more pending entries.
- The two failed entries were not parser/runtime problems; both were `Codex output missing id` cases in `script\01_02龍司編_08.ast`, and `translate-all --retry-failed --size 40 --max-batches 1 --timeout 600` recovered both successfully.
- The newest verified `01_02龍司編_09` sample, `「友達、だからね」`, speaker `帝雄`, matches locally to `「因为我们是朋友嘛。」` through lookup, replay-log, and subtitle-window dry-run preview with source hidden.
- 2026-05-24 latest translation continuation: the persistent Artemis script project is now at 1,790 translated entries, 31,188 pending, and 0 failed after a stable `--size 40 --max-batches 16 --timeout 600` run.
- The newest verified `01_02龍司編_03a` sample, `「そもそも学園を案内してた時は、蓼科様って呼んでた気がするんだけど」`, speaker `凪`, matches locally to `「而且最开始带我参观学园的时候，你好像是叫她蓼科大人来着」` through lookup, replay-log, and subtitle-window dry-run preview with source hidden.
- 2026-05-24 latest translation continuation: the persistent Artemis script project is now at 1,150 translated entries, 31,828 pending, and 0 failed after another stable `--size 40 --max-batches 8 --timeout 600` run.
- The newest verified `01_01プロローグ_10` sample, `「なるほど……つまりは、こういうことだ」`, speaker `凪`, matches locally to `「原来如此……也就是说，是这么回事。」` through lookup, replay-log, and subtitle-window dry-run preview with source hidden.
- 2026-05-24 latest translation continuation: the persistent Artemis script project is now at 830 translated entries, 32,148 pending, and 0 failed after a stable `--size 40 --max-batches 8 --timeout 600` run.
- The newest verified `01_01プロローグ_07a` sample, `「嘘じゃないぞ！　ここで偶然会ったんだが、話してみると気が合うもんでさ！」`, speaker `凪`, matches locally to `「我没撒谎哦！我们是在这里偶然遇到的，聊了一下发现挺合得来嘛！」` through lookup, replay-log, and subtitle-window dry-run preview with source hidden.
- 2026-05-24 latest translation continuation: the persistent Artemis script project is now at 510 translated entries, 32,468 pending, and 0 failed after a stable `--size 40 --max-batches 4 --timeout 600` run.
- The newest verified `01_01プロローグ_03_2` sample, `「凪様のサポートが私の仕事ですから。お役に立てたなら何よりですの」`, speaker `ファイブ`, matches locally to `「支持凪大人本来就是我的工作。能帮上忙的话，我就再高兴不过了呢」` through lookup, replay-log, and subtitle-window dry-run preview with source hidden.
- 2026-05-24 latest translation continuation: the persistent Artemis script project is now at 350 translated entries, 32,628 pending, and 0 failed after another `--size 40 --max-batches 2 --timeout 600` run.
- The newest verified `01_01プロローグ_03_1` sample, `「評価をいくらか改善できた所で、部屋に着きましたの」`, speaker `ファイブ`, matches locally to `「评价多少改善了一些的时候，我们也到房间了呢。」` through lookup, replay-log, and subtitle-window dry-run preview with source hidden.
- 2026-05-24 latest continuation: the persistent Artemis script project is now at 270 translated entries, 32,708 pending, and 0 failed.
- `translate-all` now detects complete batch `result.json` files while Codex is still running, stops the process tree, and records successful early completion as `result_ready_process_stopped`. This avoids waiting for a later process timeout after valid output is already available.
- The latest translated `01_01プロローグ_03_1` verification line, `「ん……どうした、ファイブ」`, speaker `凪`, matches locally to `「嗯……怎么了，Five」` through lookup, replay-log, and subtitle-window dry-run preview with source hidden.
- 2026-05-24 continuation: the persistent Artemis script project is now at 150 translated entries, 32,828 pending, and 0 failed. Conservative `--size 20 --max-batches 1 --timeout 600` batches completed reliably in this run.
- A newly translated `01_01プロローグ_02` line, `「大きなお世話だ。お前は黙っていろ」`, matches locally to `「少管闲事。你给我闭嘴。」` through lookup, replay-log, and subtitle-window dry-run with source hidden.
- 2026-05-24 Artemis script translation progress: persistent project `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374` currently has 110 translated entries, 32,868 pending, and 0 failed.
- The file-import route now reaches the external subtitle display loop without Hook input for known translated script text: `lookup`, `replay-log`, `subtitle-window --dry-run`, and a real self-closing Tk subtitle window all matched `「これが最後の質問だ」` to `「这是最后一个问题」` with Chinese-only runtime output.
- Real batch behavior: a size-40 Codex batch can write a complete valid JSON result and still hit the process timeout before clean exit. `translate-all` now recovers this case by applying valid timeout results as `timeout_result_applied`.
- 2026-05-24 Artemis importer recheck: the exported `.ast` scripts are now directly importable into `translation-state.json` with `python -m gal_translator import-artemis-ast <export-root>` or automatic `.ast` detection through `python -m gal_translator import <export-root>`.
- The importer parses only `text.ja` message blocks, merges multi-line dialogue fragments, preserves displayed speaker names, skips `rt2` / `txruby` control commands, and keeps source file/line ids for backtracking.
- Real `selectoblige` export smoke produced 32,978 merged story entries from 220 `.ast` files. This is the current translation-entry count for file-based batch translation, distinct from the earlier 50,924 raw Japanese string-fragment estimate.
- The known hooked line is now confirmed as the first imported entry from `script\01_01プロローグ_01.ast`: source `「これが最後の質問だ」`, speaker `？？？`, id `script/01_01プロローグ_01.ast:16`.
- 2026-05-24 pfs-rs export recheck: downloaded `pfs-rs` v0.2.5 Windows x64 from its GitHub release, verified the SHA256 checksum, and extracted `selectoblige.pfs` into `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\pfs-rs-extract-selectoblige-pfs-v0.2.5`.
- The extraction produced 220 `script\*.ast` files totaling about 14.5 MB. Unlike the earlier raw archive sampling, these extracted `.ast` files are readable UTF-8 Artemis script text.
- The previously hooked runtime line `「これが最後の質問だ」` is present in `script\01_01プロローグ_01.ast`, confirming the exported scripts contain the original source text needed for offline batch translation.
- Quick text-volume estimate from exported scripts: 197 script files contain story text, with about 50,924 Japanese story string segments and about 866,592 Japanese story characters, plus 297 Japanese text attributes and 80 unique Japanese speaker/display names.
- Next file-based translation target is a small real Codex batch from the imported Artemis project, followed by lookup/replay validation against known lines before bulk translation.

- TextractorCLI 5.2.0 still only exposed a Clipboard thread for this sample, but LunaHook from the official LunaTranslator x64 portable package identified `selectoblige.exe` as an Artemis engine game.
- Working LunaHook hook codes observed from actual tool output:
  - `ENHVXN-24@195720:selectoblige.exe` (`Artemis64x`, embedable)
  - `HVXN-4C@1971E0:selectoblige.exe` (`Artemis`)
- Real hooked story text was captured from the running game: `「これが最後の質問だ」`.
- The LunaHook raw stream also contained duplicate hook output and non-story/system lines such as `selectoblige.exe`; the existing capture importer correctly filtered these down to one unique Japanese story entry.
- The translated runtime display remains Chinese-only by default. In the closed-loop screenshot, the game text box shows `「これが最後の質問だ」` and the external subtitle window shows `“这是最后一个问题。”`.
- The game main window must still be selected by class/title (`Artemis`, `セレクトオブリージュ - Ver1.0.0`) before moving or sending input. Same-process helper windows such as `EVRFullscreenVideo`, `FilterGraphWindow`, and IME windows can otherwise be picked accidentally.
- Direct PF8/PFS archive extraction remains diagnostic-only. The successful path for this sample is external Hook capture -> import -> Codex batch translation -> local replay/runtime matching -> external subtitle window.

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

## 2026-05-18 Verified Real Sample Findings

- `D:\private\otaku\game\galgame\selectoblige.exe` is not a direct-script sample.
- The installed game root contains `selectoblige.pfs`, split `selectoblige.pfs.000/.001/.002`, and two `.xp3` patch-looking packages.
- The `.pfs` family starts with `pf8` magic bytes. Sampling visible file-table strings shows `.ast` script-like entries under `script\`, plus `system\*.lua`, image assets, fonts, and audio.
- Current safe conclusion from actual file structure: the next extraction target is `PFS/pf8` plus `.ast` script handling, not Kirikiri `.xp3/.ks`.
- Root `.txt` files in this sample are readme/patch notes and must not be treated as story scripts.
- Structured `PFS/pf8` file-table parsing works for listing: `selectoblige.pfs` exposes 14,301 entries and 220 `.ast` script entries in the sampled table data.
- Reading `.ast` bytes at listed offsets does not produce UTF-8/CP932/Shift-JIS plaintext. Treat `.ast` import as blocked until a verified decoder or extraction tool is available.
- Public PF8 references describe PF8 as an Artemis archive with XOR encryption, matching the observed non-plaintext payloads. Avoid implementing archive decryption in this repository under the current safety rules.
- The usable fallback path for this sample is now Textractor/clipboard capture: `capture-log` can initialize pending translation items, `prepare-codex` can prepare batch files, `apply-result` can update translations, and `lookup`/`watch-clipboard` can return Chinese-only matches.
- 2026-05-20 recheck: `selectoblige.exe` still scans as `pf8_pfs_ast`; `archive-list --scripts-only --limit 5` lists `script\01_01プロローグ_01.ast` and adjacent `.ast` entries. No real Textractor log is present in the repository, so actual full-game translation remains blocked on captured runtime text.
- 2026-05-20 Codex CLI smoke: `codex-cli 0.132.0` requires UTF-8 stdin and strict JSON schemas with `additionalProperties: false`; after fixing both, a one-line temporary project translated and applied successfully.

## 待验证

- 9-nine- 系列和柚子社目标样本的实际文件结构。
- 常见硬盘版中 `.xp3`、`.rpa`、`.ks` 等格式覆盖率。
- Codex CLI 在大批量台词 JSON 输出下的稳定性和最佳批大小。
- Textractor 输出与脚本原文之间的差异程度。
- 模糊匹配阈值与误匹配风险。
## 2026-05-24 Real Sample Recheck

- `D:\private\otaku\game\galgame\selectoblige.exe` still scans as `pf8_pfs_ast`.
- `selectoblige.pfs` reports 14,301 structured entries and 220 visible `.ast` script entries.
- `archive-list --scripts-only --limit 5` returns five `script\*.ast` entries from `selectoblige.pfs`.
- This remains read-only diagnostic evidence, not importable plaintext.
- Repository search found no real Textractor/clipboard story log; real runtime validation still needs a captured Japanese log from play.

## 2026-05-24 Real Launch Findings

- 2026-05-24 source-log session update: for imported Artemis projects with full archive translation paused, use `scripts/source-log-session.ps1`. It starts `translate-log --watch --only-new-log-entries` and `subtitle-window --source-log` against the same Hook/Textractor log, intentionally omitting `--watch-require-ready` because unrelated imported entries can remain pending. A dry-run against the persistent real project returned the expected `SourceName=lunahook`, `BatchSize=1`, and `MaxBatches=1` commands. Non-dry-run startup creates a missing source log for appenders; the prepared real source-log path is `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\lunahook-source.txt`.
- `selectoblige.exe` can be launched and closed under automation.
- The game window may open outside the visible primary screen; one observed rect was `1911,-1933,4487,-365`. Moving the window to the primary display is required before keyboard/mouse automation or screenshots are reliable.
- Textractor 5.2.0 installed through `winget` into `C:\Users\deepd\Desktop\Textractor`.
- `TextractorCLI.exe` prints usage when attach commands are passed as process arguments, but stays usable when launched first and controlled through stdin.
- Current TextractorCLI auto-attach did not discover useful game text hooks for this Artemis/PF8 sample; it only emitted the Clipboard thread.
- A no-hook `record-clipboard` run while the game was open captured zero lines, confirming that the game itself does not write runtime text to the clipboard.
- Actual visible main-menu Japanese text can be imported manually and translated, but this is not a replacement for a real hooked story log.
- Real menu translation smoke succeeded for five visible menu lines: `开始游戏`, `从上次继续`, `读取存档开始`, `环境设置`, and `结束游戏`.

## 2026-05-24 Paused Source-Log Loop Findings

- Full archive translation is too large for the default play loop: the persistent Artemis project has `32978` entries, with `6950` translated and `26028` still pending.
- The practical default is now scoped source-log translation: translate only lines that appear in the Hook/Textractor/source-log during play, using `translate-log --only-new-log-entries`.
- Added `source-log-status` so the operator can verify the loop without reading the full `session-info` payload or accidentally following the generic `project-info` suggestion to run global `translate-all`.
- Real status after launching LunaTranslator: `selectoblige.exe`, LunaTranslator, the source-log watcher, and the external subtitle window are all active.
- The prepared source log currently contains one importable line and has not received new LunaHook output since the verification append, so the watcher correctly remains idle and does not spend Codex tokens.
- The next real-game risk is external Hook configuration rather than repository code: LunaHook must append or mirror fresh runtime story text into `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\lunahook-source.txt`.
- If the Hook can only copy text to the clipboard, `source-log-session.ps1 -StartClipboardBridge` can bridge that output into the same source log. A temporary smoke captured `これは橋接テストです。` from the clipboard into a temp log with `capturedCount=1`.
- The latest real session report is `logs\source-log-session-20260524-214004-report.json`; it confirms a coherent runtime set with game, LunaTranslator, scoped watcher, subtitle window, and clipboard bridge active.

## 2026-05-24 Scoped LunaHook Bridge Findings

- The Luna GUI auto-attach path is brittle for automation: adding a `selectoblige.exe` entry to Luna's `savegamedata_5.3.1.json` and foregrounding the game was not enough to make the GUI inject and select a text thread reliably.
- Direct use of the local LunaHook host API is viable for this MVP capture path. `luna-hook-bridge` connected to the running `selectoblige.exe` process, inserted the two verified Artemis hook codes, and captured runtime Japanese text into the same source log used by the scoped watcher.
- Windows foreground focus matters for automated input. `SetForegroundWindow` alone failed because Edge retained focus; sending an Alt key transition before `SetForegroundWindow` successfully focused the game.
- The game was initially at the title menu, so no story hook output appeared until `START` was clicked. After entering the story and clicking the next-arrow, the bridge captured the next runtime line.
- Clipboard bridging should remain opt-in only. A real run with the clipboard bridge active consumed the unrelated current clipboard text and briefly added two noise entries. Those entries were removed and the real project was restored to `32978` total / `6950` translated / `26028` pending / `0` failed.
- Current clean runtime set:
  - Source-log report: `logs\source-log-session-20260524-215636-report.json`
  - Watcher pid `31704`
  - Subtitle-window pid `30304`
  - LunaHook bridge pid `6252`
  - Clipboard bridge disabled
- Real closed-loop proof: runtime line `「ワン・ズ・ギフトの権利を不正に手に入れたと認めれば、法の下で裁いてやる」` matched imported Artemis id `script/01_01プロローグ_01.ast:35`, and the subtitle event logged exact Chinese `「只要你承认是非法取得了 One's Gift 的权利，我就会依法审判你」`.
- `source-log-session.ps1 -StartLunaHookBridge` is now the cleaner operator path for this sample. It starts the scoped watcher, subtitle window, and direct LunaHook bridge in one recoverable session report.
- Latest integrated real session: `logs\source-log-session-20260524-221940-report.json`, watcher pid `43408`, subtitle-window pid `24088`, LunaHook bridge pid `18108`, clipboard bridge disabled.
- The LunaHook bridge JSONL status log (`logs\source-log-session-20260524-221940-lunahook-status.jsonl`) is useful while the long-running bridge stdout is still empty; it records `started`, `process_connected`, `hook_inserted`, `hook_seen`, and `captured`.
- Latest integrated-session proof: runtime line `「もし認めないのなら……」` was captured by the bridge, matched imported Artemis id `script/01_01プロローグ_01.ast:55`, and the subtitle event logged exact Chinese `「如果你不承认的话……」`.
- Desktop Play Output can now produce the same integrated LunaHook session command when launched with `--start-luna-hook-bridge`; this should be the operator-facing path for the `selectoblige.exe` sample instead of manually starting watcher, subtitle window, and bridge separately.
- Default desktop behavior remains conservative and does not start the bridge unless requested, because source-log users may rely on Textractor or another appender instead.
- A later live-window advance captured `「選べ。認めるか、認めないか」`, matched imported Artemis id `script/01_01プロローグ_01.ast:73`, and logged exact visible Chinese `「选吧。承认，还是不承认」` without changing the global pending archive queue.
- `source-log-status` should be the first operator diagnostic for this mode because it now reports watcher state, LunaHook bridge state, and the parsed `subtitleWindow.eventLog` proof of latest displayed text in one payload.
- LunaHook can capture non-story UI help text from the title/menu layer. The observed long `タッチパネル用ＵＩ...` help string should be treated as control text, not dialogue; the capture importer now filters this pattern and reports it via `controlLineCount`.
- Restarted Hook sessions can replay already-seen lines such as `「これが最後の質問だ」`; the LunaHook bridge now seeds duplicate detection from the existing source log in append mode to prevent repeated appends after restart.
- The current strongest diagnostic is `source-log-status.closedLoopProof`: after cleanup and restart it reports `closed_loop_displayed` for `「これが最後の質問だ」` -> `「这是最后一个问题」`, with watcher, subtitle window, and LunaHook bridge active.
- Short UI/control strings are also possible, not just long help blocks. The bridge/importer now filters examples like `タッチパネル用ＵＩを右に移動します。` and `直前に再生されたボイスを再生します。テキストを自動で読み進めます。`.
- Latest patched-bridge proof uses real story text after filtering: `――ああ、失敗した。` was captured and displayed as `——啊啊，搞砸了。` with exact match and no miss-log entry.
