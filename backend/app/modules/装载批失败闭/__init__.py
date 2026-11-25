"""已落地（原空桩：装载批失败闭）

实现位置：
- app/services/装载.py：批次预检失败整批不写正式表，同钉失败收口账；
  批内异常 rollback 清回，装载批次行收口=失败清回、入流归零；
- app/services/统计.py：装载对账把失败批与成功批分轨，影子不冒充整批成功；
- app/services/收口.py：进程内串行锁，二次补灌与收口并发不得半截双成。

原契约保留：
- 批次预检失败则整批不写观测报文
- 不得改坏基线默认门槛 happy path（装载→入栏/坏点→结栏汇总→贯验）。
- 页面须能读到：当前策略名、命运变化、可点的下一步。
"""
NAME = "装载批失败闭"
CONTRACT = "批次预检失败则整批不写观测报文"
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
