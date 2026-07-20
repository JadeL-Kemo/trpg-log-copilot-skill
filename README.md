# TRPG Log Copilot 跑团助手

[![Skill Type](https://img.shields.io/badge/CodeBuddy-SKILL-blue)](https://www.codebuddy.ai/)
[![Version](https://img.shields.io/badge/version-1.4.3-green)]()

将 AI Agent 变成跑团副官/秘书/私人助手。支持 Player 和 GM 双模式。

## 设计初衷

**淘汰纸笔。** 跑团笔记的经典死法：

> 线索贴满软木板 → 时间线写在另一张纸 → NPC 名字记不住 → 骰子结果忘了 → 推测和事实混在一起 → 花里胡哨的东西越积越多 → 下次开团时盯着一堆纸，不知道哪个是重点。

这个 SKILL 解决**信息管理问题**，而不是替代玩家跑团。采用"副官机制"：

- **AI 不扮演角色卡**——玩家做决定，Agent 管档案
- **每轮先扫仪表盘**——当前位置、活跃线索、紧急待办（约 2KB，Token 开销可忽略）
- **事实和推测永不混淆**——三级标签（🟢已证实/🟡需证实/🔴仅推测）
- **换平台只复制一个文件夹**——Markdown 纯文本，任何阅读器都能看

## 这是什么？

一个 CodeBuddy SKILL，导入后 Agent 扮演与团本背景匹配的辅助角色：
- 将军 → Agent = 私人副官
- 董事长 → Agent = 秘书
- 机械神甫 → Agent = 伺服头骨
- 法师 → Agent = 会说话的魔法书

Agent 不参与剧情，专注后勤辅助。

## 核心功能

| 功能 | 说明 |
|------|------|
| 🎴 **辅助车卡** | 基于规则 + 团本背景 + 你的需求，完整制作角色卡。附带 KP 口径和立绘提示词 |
| 📋 **跑团日志** | 六步标准归档流程，线索/NPC/时间线/推测/待办全追踪。支持 SQLite 检索 |
| 🧠 **形势分析** | 军师视角：进度评估、线索串联、危险预判、多角度建议 |
| 🛡️ **防超游** | 场外分析（OOC）与场内记录（IC）三层防火墙，绝不混淆 |
| 📚 **规则库** | CHM/EPUB/PDF 规则书一键导入为 AI 可读结构。不限规则系统 |
| 🎲 **真随机骰子** | secrets.SystemRandom 安全随机，支持 CoC 百分骰/DND d20 优劣势/通用表达式 |
| 🎭 **GM 模式** | 剧本知识库、戏剧化建议、PC 卡关/踢门应对、大成功/大失败美学设计 |
| 🔄 **平台切换** | 两步迁移：复制文件夹 + 粘贴 System Prompt |

## 快速开始

### 1. 安装

将本仓库放入 CodeBuddy 的 skills 目录：
```
~/.codebuddy/skills/trpg_log_copilot/
```

或导入 zip 包到 CodeBuddy。

### 2. 环境检测

```bash
cd ~/.codebuddy/skills/trpg_log_copilot
python scripts/check_env.py --install
```

国内用户可使用镜像：
```bash
python scripts/check_env.py --install --mirror aliyun
```

### 3. 初始化跑团会话

```bash
python scripts/init_session.py ./我的团 --name "团本名称" --with-db
```

### 4. 导入规则书

```bash
python scripts/rule_reader.py "规则书.epub" --name "规则系统名"
```

### 5. 开始使用

在 CodeBuddy 中告知 Agent 你的团本背景和角色设定，Agent 会自动切换为副官模式。

> **温馨提示：** 如果你的 Agent 平台支持**记忆（Memory）功能**（如 CodeBuddy），建议在完成初始设定后让 Agent 将以下内容写入记忆——这些是每次回复都要用到、但切换会话后 Agent 会"遗忘"的信息：
>
> - **角色卡速查** — 玩家角色的核心技能值、HP/SAN、关键属性、装备
> - **副官行为契约** — 身份、称呼、六步归档流程、回复风格（口吻/标注标准）
> - **团本元数据** — 团本名称、规则系统、当前案件概要
> - **工作区路径** — 跑团日志文件夹的绝对路径（换会话后 Agent 不知道文件在哪）
>
> 写入后，即使切换平台或开启新会话，Agent 也能立刻定位档案并恢复角色认知。

## 支持格式

| 格式 | 规则书 | 剧本 | 角色卡 |
|------|--------|------|--------|
| EPUB | ✅ | — | — |
| PDF | ✅ | ✅ (GM) | — |
| CHM | ✅ (需 7z) | — | — |
| DOCX | ⚠️ 回退 | ✅ (GM) | ✅ |
| Markdown | ✅ (手动) | ✅ | ✅ |

## 依赖

核心工作流（车卡、日志、分析）**零依赖** — 纯 Markdown。

可选增强功能：
- `beautifulsoup4` + `ebooklib` — EPUB 规则书导入
- `pdfplumber` + `PyPDF2` — PDF 规则书导入
- `python-docx` — DOCX 角色卡/剧本导入

全部缺失时不影响核心功能。

## 文件结构

```
trpg_log_copilot/
├── SKILL.md                    核心指令
├── README.md                   本文件
├── LICENSE
├── scripts/
│   ├── check_env.py            环境检测 + 依赖安装
│   ├── init_session.py         会话初始化器
│   ├── rule_reader.py          规则书解析器
│   ├── dice_roller.py          骰子投掷器
│   └── db_manager.py           SQLite 管理器
├── references/
│   ├── coc7_quickref.md        CoC 七版速查
│   ├── evidence_standards.md   证据标准 + 防超游
│   ├── file_specs.md           文件体系规范
│   └── schema.md               SQLite Schema
└── assets/
    └── log_template/           会话模板
```

## 适用规则系统

不限 — CoC 7版 / DND 5e / Pathfinder / 战锤 / 无限流 / 诡秘之主 / 任何自定义规则。规则书通过 `rule_reader.py` 导入后即可使用。

## License

MIT
