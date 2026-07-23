# Changelog

All notable changes to this project will be documented in this file.

---

## [1.7.0] — 2026-07-23

### Added

- **MD 表验证器** — `import_md.py` 自动检测列数不匹配（如 `医学|急救` 被误拆为多列）
- **完整执行流程 SOP** — 9 步清单 + 单场景示例（SKILL.md）
- 日志加载超时保护 — 3 秒后显示"加载失败"（非"无正文"）

### Removed

- **JSON storage layer** — 01/02/03/*.json, _index.json, 06_待办.json deprecated. JSON write-then-import workflow replaced by MD table append + auto-parse.
- **import_from_md.py** — replaced by `import_md.py` (MD table parser, ~100 lines).
- **01b_已关闭线索.md, 02a_人物档案.md, 03a_详细时间线.md** — data accessible via SQL queries.

### Added

- **MD table parser** — `import_md.py` reads `|...|` markdown tables, maps columns by header, INSERTs to SQL. One-line failure doesn't corrupt file (vs JSON all-or-nothing).
- **graph command** — `db_manager.py graph <entity>` returns complete relationship map in one CLI call: NPC info + related clues + timeline + state changes. Replaces 5 separate CLI calls.
- **tags column** in clues FTS5 — English/Pinyin keywords enable multi-word CJK search (FTS5 default tokenizer limitation).

### Changed

- **SKILL.md**: SOP table → MD file references. Clue format → MD table row. Query instructions → `graph` as primary command.
- **render_views.py**: reads SQL exclusively (zero JSON dependency).
- **md_schema_standard.md**: v2.0 — JSON deprecated, MD table as canonical write format.
- **evidence_standards.md**: v1.7.1 — added `tags` field and `verified`/`priority`/`source` tri-axis.

### Architecture

```
v1.6                           v1.7
────                           ────
AI writes JSON → import → SQL   AI appends MD table row (native)
JSON = canonical                import_md.py parses → SQL
SQL + JSON dual storage         SQL = single source of truth
5 CLI calls per query           1 graph call per entity
JSON all-or-nothing failure     One bad row = one skip
```

---

## [1.6.0] — 2026-07-22

### Added

- **角色状态追踪** — 事件溯源式 HP/SAN/资源变更记录。SQLite 新增 `char_base` + `char_state_log` 两张表。
- **JSON 键值池** — `state add` 接受任意 `--<池名> <delta>` 对（`--hp -3 --san -1 --spell_l3 -2 --custom_pool -1`）。兼容 CoC/DND/泛规则系统，无预定义字段限制。
- **db_manager 新增 `state` 子命令** — `state init`（`--<池名> <最大值>`注册角色）、`state add`（记录变更）、`state query`（变更历史）、`state current`（跨角色当前状态汇总表）
- **reason 固定用语词表 v2** — `references/state_reason_vocab.md`。通用+CoC+DND 三段 + 自定义池命名约定。确保变更原因可被 FTS5 检索和分类统计。
- **SKILL.md 六步新增步骤 4a** — 每次 HP/SAN/资源变更必须调用 `state add`，禁止只在叙事段落中描述。叙事段落和 SQLite 记录必须双写。

### Changed

- Rule 模板和项目 Rule 新增 HP/SAN 结构化记录指令（FATAL 级）
- Schema 从固定列（hp_delta/san_delta）重构为 JSON 键值池（deltas TEXT），兼容任意数量资源池

---

## [1.5.1] — 2026-07-22

### Changed

- **信息检索：SQLite 优先** — 移除"≤30条读markdown"阈值陷阱，所有线索/NPC/事件检索从 SQLite FTS5 开始。Markdown 降级为导出视图，不再作为检索入口。
- **SKILL.md 与 Rule 去重** — 移除角色注入段（身份定义移交项目级 Rule），新增 Rule 前置声明。SKILL 专注详细工作流/工具/规范。
- **线索格式对齐实际** — SKILL.md 明确数据文件中使用表格式（来源/可靠性列），不再是理论括号标注体。`evidence_standards.md` 新增"实际格式映射"节。
- **归档上限调整** — 新增 `04a_过往日志.md` 上限 500 行，超出压缩为摘要。对齐 Rule 级归档管理。
- **平台切换** — 参考源从 `07_跑团规范手册.md` 改为项目 Rule。
- **六步归档** — 新增 Step 0（扫 `00_当前局势.md`），不再要求首行 `📍归档进度` 格式。

---

## [1.5.0] — 2026-07-21

### Added

- **FTS5 全文搜索** — SQLite 虚拟表 + 自动同步触发器，2000 条线索查询 <10ms
- **双维证据标签** — `[来源: 场内/检定/场外/推测/铁证] [确信: 高/中/低/确定]`，替代三色标签
- **断点恢复** — `00_当前局势.md` 首行 `📍归档进度`，中断后直接跳到断点
- **信息熵控制** — 线索 > 30 条自动切 SQL 查询，文件 > 300 行自动压缩归档
- **`检定` 来源** — 骰子/技能检定结果独立溯源，大成功=高确信，失败=低确信
- **交叉引用** — `linked_ids` 字段 + `db_manager.py clue link` 命令
- **统计概览** — `db_manager.py stats` 一键查看线索/确信度/NPC/事件分布
- **Markdown 导出** — `db_manager.py export` 从 DB 生成"最近 N 条"视图
- **速查模板** — `rule_lib/_quickref_template.md`，新规则系统标准化
- **证据标准独立文档** — `references/evidence_standards.md`

### Changed

- **SKILL.md 精简** — 250 行 → 213 行（-15%），规范移至 `README.md` 和 `references/`
- **脚本分层** — `scripts/`（Agent 运行时）与 `tools/`（用户手动）分离
- **来源标签 4→5** — 新增 `检定`（骰子结果）
- **防超游规则外移** — 完整分层和跨越规则见 `evidence_standards.md`
- **README 重写** — GitHub 开发者友好格式，功能卡片，快速开始指南
- **LICENSE 恢复** — 修复合并冲突导致的文件损坏，确认为 Apache 2.0

### Security

- **内容脱敏** — 所有示例文本改为泛型 `<占位符>`，防止 AI 直接复制具体游戏内容

---

---

## [1.4.3] — 2026-07-21

See [Releases](https://github.com/JadeL-Kemo/trpg-log-copilot-skill/releases) for details.

---

## [1.0.0] — 2026-06

### Added

- 初始发布
- 六步归档工作流
- 角色注入模板
- 骰子投掷器（通用 / CoC / DND）
- 规则书导入器
- SQLite 数据库（基础版，无 FTS5）
- Player / GM 双模式
- 防超游分层
- 三级证据标签 🟢🟡🔴
- 平台迁移工具

