# HP/SAN/资源变更原因 — 格式约定与参考词表

> **这不是必须遵守的词表。** 这是格式约定（推荐命名模式）+ 已有用法的枚举参考。
> `--reason` 字段的唯一硬性要求：**使用 snake_case 或 类别_细节 格式，确保 FTS5 可检索和可比对。**

## 格式约定

```
<类别>[_<子类别>]
字母：a-z, 0-9, _
长度：5-40 字符
```

| 正确 | 错误 | 原因 |
|------|------|------|
| `combat_fire` | `火焰伤害` | 中文难做 FTS5 精确区分 |
| `sanity_pass` | `SC通过` | 同上 |
| `rest_short` | `短休` | 同上 |
| `spell_3` | `消耗了一个3环法术位` | 太长，不可比对 |

> **不使用中文 reason 的主要理由**：SQLite FTS5 对"火焰伤害"和"火焰伤"看作两个词，统计时容易漏。
> 英文 snake_case 做 `SELECT reason, COUNT(*) GROUP BY reason` 时不会分裂。

## 已有用法的枚举参考

以下已在当前团本中使用过，可直接复用：

| 枚举值 | 含义 | 规则系统 |
|------|------|:--:|
| `combat_melee` | 拳脚/棍棒 | 通用 |
| `combat_weapon` | 利器/枪械 | 通用 |
| `combat_fire` | 火焰 | 通用 |
| `combat_fall` | 坠落 | 通用 |
| `env_cold` | 寒冷 | 通用 |
| `env_heat` | 高温 | 通用 |
| `env_poison` | 毒素 | 通用 |
| `sanity_pass` | SAN检定成功 | CoC |
| `sanity_fail` | SAN检定失败 | CoC |
| `spell_consume` | 施法消耗资源 | 通用 |
| `rest_short` | 短休恢复 | DND |
| `rest_long` | 长休恢复 | DND |
| `death_save` | 死亡豁免 | DND |
| `heal_natural` | 自然恢复 | 通用 |
| `heal_magic` | 法术/药物恢复 | 通用 |
| `attr_change` | 属性永久变更 | 通用 |
| `status_add` | 新增状态标记 | 通用 |
| `status_remove` | 状态标记移除 | 通用 |
| `init` | 首次注册角色 | 自动 |

## 自定义扩展

用户可随时添加新枚举值，只需遵守格式约定。添加后立即可用于 FTS5 统计。

```bash
# 示例：自定义资源消耗
python scripts/db_manager.py trpg_data.db state add 某角色 \
    --hp -5 --custom_pool -3 --reason "spell_consume" --clue CL-999
```

## 池命名约定

| 规则系统 | 常用池 key | 说明 |
|------|------|------|
| CoC | `hp` `san` `mp` `luck` | |
| DND | `hp` `ac` `spell_l<N>` `ki` `rage` | spell_l1~9 |
| 自定义 | **任意英文字母+下划线** | 建议对应规则书原文 |

```bash
# CoC
python scripts/db_manager.py trpg_data.db state init 角色 pc --hp 12 --san 60 --mp 14

# DND 法师
python scripts/db_manager.py trpg_data.db state init 角色 npc --hp 45 --ac 16 --spell_l3 3 --spell_l5 1

# 自定义(泛化)
python scripts/db_manager.py trpg_data.db state init 角色 pc --hp 10 --resource_a 20 --resource_b 100
```
