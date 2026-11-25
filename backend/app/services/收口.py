"""装载批收口：切流账册清回形态的编排中枢。

形态一（切流账册清回）：
- 批内主边（观测报文 / 入栏缓冲 / 坏点匣）同成同败，中途失败整批清回批前；
- 失败指纹与曾写入的前半影子进只读「装载批收口账」，正式表零残留；
- 装载、补灌、结栏共用同一把串行锁，收口路上再灌不得半截双成；
- 只暴露只读查询接口，写口只由装载编排内部调用。
"""
from __future__ import annotations
import hashlib
import json
import threading

from app.db import 连接

# 装载（含二次补灌）与结栏收口共用：进程内串行，杜绝收口与补灌交错半截双成
装载锁 = threading.RLock()

整批成功 = "整批成功"
失败清回 = "失败清回"


def 失败指纹(批次: str, 原因: str, 影子明细: list[dict]) -> str:
    """确定性指纹：批次 + 失败原因 + 曾写入影子编号序列，钉住同一次中断。"""
    编号序 = "|".join(行.get("报文编号", "") for 行 in 影子明细)
    坯 = f"{批次}\n{原因}\n{编号序}"
    return "断-" + hashlib.sha256(坯.encode("utf-8")).hexdigest()[:12]


def 记收口账(
    conn,
    批次: str,
    时刻: str,
    收口: str,
    原因: str,
    指纹: str,
    影子计数: dict,
    影子明细: list[dict],
) -> None:
    """写口：装载事务内部调用，与主边同事务提交。"""
    现行观测 = conn.execute(
        "SELECT COUNT(*) AS c FROM 观测报文 WHERE 批次编号=?", (批次,)
    ).fetchone()["c"]
    现行在栏 = conn.execute(
        "SELECT COUNT(*) AS c FROM 入栏缓冲 WHERE 批次编号=?", (批次,)
    ).fetchone()["c"]
    conn.execute(
        """INSERT INTO 装载批收口账
           (批次编号,时刻,收口,失败指纹,失败原因,影子入流,影子入栏,影子坏点,
            现行观测,现行在栏,影子明细)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            批次, 时刻, 收口, 指纹, 原因,
            影子计数.get("入流", 0), 影子计数.get("入栏", 0), 影子计数.get("坏点", 0),
            现行观测, 现行在栏,
            json.dumps(影子明细, ensure_ascii=False),
        ),
    )


def 收口账列表(限制: int = 50) -> list[dict]:
    """只读：批收口账册（含失败影子与成功批次）。"""
    conn = 连接()
    try:
        rows = conn.execute(
            """SELECT 编号,批次编号,时刻,收口,失败指纹,失败原因,
                      影子入流,影子入栏,影子坏点,现行观测,现行在栏
               FROM 装载批收口账 ORDER BY 编号 DESC LIMIT ?""",
            (限制,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def 批次收口查(批次: str) -> dict:
    """只读：单批收口视图——正式现行集合与失败影子集合分开读。"""
    conn = 连接()
    try:
        r = conn.execute(
            "SELECT * FROM 装载批收口账 WHERE 批次编号=? ORDER BY 编号 DESC LIMIT 1",
            (批次,),
        ).fetchone()
        if r is None:
            raise KeyError(f"无此批次收口记录: {批次}")
        out = dict(r)
        out["影子明细"] = json.loads(r["影子明细"] or "[]")
        return out
    finally:
        conn.close()
