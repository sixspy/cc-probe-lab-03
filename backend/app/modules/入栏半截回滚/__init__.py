"""已落地（原空桩：入栏半截回滚）

实现位置：
- app/services/装载.py：批内主边（观测报文/入栏缓冲/坏点匣）同事务，
  中途异常整批 rollback 清回批前，正式在栏零残留；
- app/services/收口.py：失败指纹 + 装载批收口账（影子明细只读）；
- app/services/贯验.py：失败批残留现行在栏即判收口撕裂。

原契约保留：
- 结栏/装载中途失败时入栏命运整批回滚，不留半汇总
- 不得改坏基线默认门槛 happy path（装载→入栏/坏点→结栏汇总→贯验）。
- 页面须能读到：当前策略名、命运变化、可点的下一步。
"""
NAME = "入栏半截回滚"
CONTRACT = "结栏中途失败时入栏命运整批回滚，不留半汇总"
HOOKS = ("before_load", "after_load", "decide_gate", "before_close", "after_close", "extra_verify_checks")


def describe() -> dict:
    return {"空桩": NAME, "契约": CONTRACT, "钩子": list(HOOKS), "默认启用": False}


def before_load(batch: dict) -> dict:
    return batch


def after_load(report: dict) -> dict:
    return report


def decide_gate(event: dict, rules: dict) -> str:
    return "入栏"


def before_close(pen_id: str) -> None:
    return None


def after_close(report: dict) -> dict:
    return report


def extra_verify_checks(snapshot: dict) -> list[str]:
    return []
