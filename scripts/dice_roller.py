#!/usr/bin/env python3
"""
TRPG 骰子投掷器 — 使用 cryptographically secure 随机源。

支持:
    - 标准骰子: d20, 3d6, 2d10+5
    - 百分骰 (CoC): d100, 包含惩罚骰/奖励骰
    - 优势/劣势 (DND5e): d20 adv, d20 dis
    - 自定义: dX, NdX+Y
    - JSON 输出 (AI 友好)
    - 批量投掷

Usage:
    python dice_roller.py <dice_expr> [<dice_expr> ...]
    python dice_roller.py --json 3d6 d100 2d20+5
    python dice_roller.py --coc-check 55          # CoC 检定
    python dice_roller.py --coc-check 55 --bonus 1 # 奖励骰
    python dice_roller.py --dnd-check 15           # DND 难度检定
    python dice_roller.py --dnd-check 15 --advantage

Examples:
    python dice_roller.py d20                              # 单骰
    python dice_roller.py 3d6+2                             # 多骰+修正
    python dice_roller.py --json 2d20 d100 4d6              # JSON输出
    python dice_roller.py --coc-check 70                    # CoC常规检定
    python dice_roller.py --coc-check 70 --penalty 1       # CoC惩罚骰
    python dice_roller.py --dnd-check 15 --advantage       # DND优势
"""

import sys
import json
import re
import secrets
import argparse


# ============================================================================
# 真随机源 — 使用 secrets.SystemRandom (os.urandom)
# ============================================================================

_rng = secrets.SystemRandom()


def roll_die(sides: int) -> int:
    """Roll a single die with given number of sides."""
    return _rng.randint(1, sides)


def roll_multi(count: int, sides: int) -> list:
    """Roll multiple dice."""
    return [roll_die(sides) for _ in range(count)]


# ============================================================================
# 表达式解析
# ============================================================================

DICE_PATTERN = re.compile(
    r'^(\d+)?d(\d+|%)(?:\s*([+-])\s*(\d+))?$',
    re.IGNORECASE
)


def parse_dice_expr(expr: str) -> dict:
    """Parse a dice expression like '3d6+2', 'd20', '2d100-5'."""
    expr = expr.strip().replace(' ', '')

    # Handle % as d100
    if expr.endswith('%'):
        expr = expr.replace('%', 'd100')
    if expr == 'd%':
        expr = 'd100'

    # Handle plain number (non-dice)
    if expr.isdigit() or (expr.startswith('-') and expr[1:].isdigit()):
        return {"expr": expr, "interpreted": f"flat:{expr}", "result": int(expr),
                "rolls": [], "modifier": int(expr)}

    m = DICE_PATTERN.match(expr)
    if not m:
        # Fallback: try simpler pattern
        m2 = re.match(r'^(\d+)?d(\d+)$', expr, re.IGNORECASE)
        if m2:
            count = int(m2.group(1)) if m2.group(1) else 1
            sides = 100 if m2.group(2) == '%' else int(m2.group(2))
            rolls = roll_multi(count, sides)
            return {
                "expr": expr, "interpreted": f"{count}d{sides}",
                "result": sum(rolls), "rolls": rolls,
                "count": count, "sides": sides, "modifier": 0
            }
        return {"expr": expr, "error": f"Cannot parse: '{expr}'. Use format: NdX+Y"}

    count = int(m.group(1)) if m.group(1) else 1
    sides = 100 if m.group(2) == '%' else int(m.group(2))
    op = m.group(3) or '+'
    modifier = int(m.group(4)) if m.group(4) else 0

    rolls = roll_multi(count, sides)
    total = sum(rolls)
    adjusted = total + modifier if op == '+' else total - modifier

    return {
        "expr": expr,
        "interpreted": f"{count}d{sides}{op}{modifier}" if modifier else f"{count}d{sides}",
        "result": adjusted,
        "rolls": rolls,
        "base_sum": total,
        "count": count, "sides": sides, "modifier": modifier if op == '+' else -modifier
    }


# ============================================================================
# CoC 检定 (百分骰 + 奖励/惩罚骰)
# ============================================================================

def coc_check(skill_value: int, bonus: int = 0, penalty: int = 0):
    """
    CoC 7e skill check using percentile dice.

    bonus > 0: 奖励骰 (roll extra tens die, take best)
    penalty > 0: 惩罚骰 (roll extra tens die, take worst)

    Returns detailed result dict.
    """
    if skill_value < 1 or skill_value > 100:
        return {"error": f"Skill value {skill_value} out of range (1-100)"}

    tens_dice = 1 + max(bonus, penalty)
    tens = roll_multi(tens_dice, 10)  # 0-9 → 00-90
    units = roll_die(10) - 1           # 0-9

    # Convert to actual tens (0=00, 1=10, ..., 9=90)
    tens_values = [(t % 10) * 10 for t in tens]

    if bonus > 0:
        chosen_tens = min(tens_values)  # Best = lowest
    elif penalty > 0:
        chosen_tens = max(tens_values)  # Worst = highest
    else:
        chosen_tens = tens_values[0]

    # Special: 00+0 = 100
    roll = chosen_tens + units
    if roll == 0:
        roll = 100

    # Determine success level
    is_success = roll <= skill_value
    is_hard_success = roll <= skill_value // 2
    is_extreme_success = roll <= skill_value // 5
    is_fumble = roll >= 96 if skill_value < 50 else (roll == 100)

    # Success level string
    if is_fumble and not is_success:
        level = "FUMBLE"
    elif is_extreme_success:
        level = "EXTREME"
    elif is_hard_success:
        level = "HARD"
    elif is_success:
        level = "REGULAR"
    else:
        level = "FAILURE"

    return {
        "type": "coc_check",
        "skill": skill_value,
        "roll": roll,
        "tens_dice": tens,
        "units_die": units,
        "chosen_tens": chosen_tens,
        "bonus": bonus,
        "penalty": penalty,
        "level": level,
        "success": is_success,
        "is_hard": is_hard_success,
        "is_extreme": is_extreme_success,
        "is_fumble": is_fumble
    }


# ============================================================================
# DND 检定 (d20 + 优势/劣势)
# ============================================================================

def dnd_check(dc: int, advantage: bool = False, disadvantage: bool = False):
    """
    DND 5e ability check with d20.

    Returns detailed result dict.
    """
    if advantage and disadvantage:
        advantage = disadvantage = False  # Cancel out

    count = 2 if (advantage or disadvantage) else 1
    rolls = roll_multi(count, 20)

    if advantage:
        result = max(rolls)
        mode = "advantage"
    elif disadvantage:
        result = min(rolls)
        mode = "disadvantage"
    else:
        result = rolls[0]
        mode = "normal"

    is_success = result >= dc
    is_crit = result == 20
    is_crit_fail = result == 1

    return {
        "type": "dnd_check",
        "dc": dc,
        "roll": result,
        "rolls": rolls,
        "mode": mode,
        "success": is_success,
        "crit": is_crit,
        "crit_fail": is_crit_fail
    }


# ============================================================================
# 输出格式化
# ============================================================================

def format_dice_result_text(result: dict) -> str:
    """Format a dice result as human-readable text."""
    if 'error' in result:
        return f"ERROR: {result['error']}"

    if result.get('type') == 'coc_check':
        emoji = {"EXTREME": "🌟", "HARD": "✨", "REGULAR": "✅",
                 "FAILURE": "❌", "FUMBLE": "💀"}
        bonus_str = ""
        if result['bonus'] > 0:
            bonus_str = f" [奖励骰×{result['bonus']}]"
        elif result['penalty'] > 0:
            bonus_str = f" [惩罚骰×{result['penalty']}]"

        return (f"{emoji.get(result['level'], '❓')} CoC检定: "
                f"技能{result['skill']} → 掷出{result['roll']}"
                f"{bonus_str} → {result['level']}")

    elif result.get('type') == 'dnd_check':
        emoji = "🌟" if result.get('crit') else ("💀" if result.get('crit_fail') else
                "✅" if result.get('success') else "❌")
        mode = f"[{result['mode']}] " if result['mode'] != 'normal' else ""
        return (f"{emoji} DND检定: DC{result['dc']} {mode}"
                f"→ 掷出{result['roll']} → "
                f"{'成功' if result['success'] else '失败'}"
                f"{' ★CRIT★' if result.get('crit') else ''}"
                f"{' CRIT FAIL' if result.get('crit_fail') else ''}")

    else:
        # Standard dice
        rolls_str = ', '.join(str(r) for r in result.get('rolls', []))
        base = f"🎲 {result['interpreted']}: [{rolls_str}]"
        if result.get('modifier', 0) != 0:
            base += f" = {result['base_sum']}{'+' if result['modifier']>0 else ''}{result['modifier']}"
        base += f" → {result['result']}"
        return base


# ============================================================================
# 主入口
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="TRPG Dice Roller — cryptographically secure randomness"
    )
    parser.add_argument("dice", nargs='*', help="Dice expressions (e.g., d20, 3d6, 2d10+5)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")

    # CoC-specific
    parser.add_argument("--coc-check", type=int, metavar="SKILL",
                        help="CoC 7e skill check (percentile)")
    parser.add_argument("--bonus", type=int, default=0, metavar="N",
                        help="Number of bonus dice (CoC)")
    parser.add_argument("--penalty", type=int, default=0, metavar="N",
                        help="Number of penalty dice (CoC)")

    # DND-specific
    parser.add_argument("--dnd-check", type=int, metavar="DC",
                        help="DND 5e ability check (d20 vs DC)")
    parser.add_argument("--advantage", action="store_true", help="Roll with advantage")
    parser.add_argument("--disadvantage", action="store_true", help="Roll with disadvantage")

    args = parser.parse_args()

    results = []

    # CoC check
    if args.coc_check is not None:
        r = coc_check(args.coc_check, args.bonus, args.penalty)
        results.append(r)

    # DND check
    if args.dnd_check is not None:
        r = dnd_check(args.dnd_check, args.advantage, args.disadvantage)
        results.append(r)

    # Generic dice
    for expr in args.dice:
        r = parse_dice_expr(expr)
        results.append(r)

    if not results:
        parser.print_help()
        sys.exit(1)

    # Output
    if args.json:
        indent = 2 if args.pretty else None
        print(json.dumps(results, ensure_ascii=False, indent=indent))
    else:
        for r in results:
            print(format_dice_result_text(r))


if __name__ == "__main__":
    main()
