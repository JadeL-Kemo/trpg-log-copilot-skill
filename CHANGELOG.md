# Changelog

All notable changes to this project will be documented in this file.

---

## [1.5.0 — 2026-07-21

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

