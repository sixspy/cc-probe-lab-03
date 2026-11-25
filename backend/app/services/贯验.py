"""栏贯验：已汇总缓冲报文数 == 汇总账报文数之和；在栏集合按批次可分。

收口形态下另核两条：
- 失败清回批不得在现行入栏缓冲留行（收口撕裂）；
- 失败后贯验读到的在栏集合须能按批次分开，影子批不冒充整批成功。
"""
from __future__ import annotations
from app.db import 连接
from app.seed import 此刻
from app.services import 收口


def _批次视图(conn) -> tuple[dict, list[str], list[str]]:
    批次在栏 = {
        r["批次编号"]: r["c"]
        for r in conn.execute(
            "SELECT 批次编号, COUNT(*) AS c FROM 入栏缓冲 WHERE 命运='在栏' GROUP BY 批次编号"
        ).fetchall()
        if r["批次编号"]
    }
    失败收口批 = [
        r["批次编号"]
        for r in conn.execute(
            "SELECT DISTINCT 批次编号 FROM 装载批收口账 WHERE 收口=?",
            (收口.失败清回,),
        ).fetchall()
    ]
    # 失败批在现行在栏集合仍有行 = 清回没清干净
    收口撕裂 = [b for b in 失败收口批 if b in 批次在栏]
    return 批次在栏, 失败收口批, 收口撕裂


def 跑一次() -> dict:
    conn = 连接()
    try:
        在栏 = conn.execute(
            "SELECT COUNT(*) AS c FROM 入栏缓冲 WHERE 命运='在栏'"
        ).fetchone()["c"]
        已汇总缓冲 = conn.execute(
            "SELECT COUNT(*) AS c FROM 入栏缓冲 WHERE 命运='已汇总'"
        ).fetchone()["c"]
        汇总报文 = conn.execute(
            "SELECT COALESCE(SUM(报文数),0) AS c FROM 站点汇总账"
        ).fetchone()["c"]
        坏点 = conn.execute("SELECT COUNT(*) AS c FROM 坏点匣").fetchone()["c"]
        批次在栏, 失败收口批, 收口撕裂 = _批次视图(conn)
        对齐 = 1 if int(已汇总缓冲) == int(汇总报文) and not 收口撕裂 else 0
        if 收口撕裂:
            说明 = f"收口撕裂：失败批残留现行在栏 {收口撕裂}"
        elif 对齐:
            说明 = "入栏已汇总与站点汇总报文数一致；失败批已清回，在栏按批次可分"
        else:
            说明 = f"撕裂：已汇总缓冲={已汇总缓冲} 汇总报文={汇总报文}"
        时刻 = 此刻()
        conn.execute(
            """INSERT INTO 栏贯验(时刻,在栏笔数,汇总报文数,坏点笔数,是否对齐,说明)
               VALUES (?,?,?,?,?,?)""",
            (时刻, 在栏, int(汇总报文), 坏点, 对齐, 说明),
        )
        conn.commit()
        return {
            "时刻": 时刻,
            "在栏": 在栏,
            "已汇总缓冲": int(已汇总缓冲),
            "汇总报文": int(汇总报文),
            "坏点": 坏点,
            "是否对齐": bool(对齐),
            "说明": 说明,
            "批次在栏": 批次在栏,
            "失败收口批": 失败收口批,
            "收口撕裂": 收口撕裂,
        }
    finally:
        conn.close()


def 只读快照() -> dict:
    """不落库的贯验快照，供页面预览。"""
    conn = 连接()
    try:
        在栏 = conn.execute(
            "SELECT COUNT(*) AS c FROM 入栏缓冲 WHERE 命运='在栏'"
        ).fetchone()["c"]
        已汇总缓冲 = conn.execute(
            "SELECT COUNT(*) AS c FROM 入栏缓冲 WHERE 命运='已汇总'"
        ).fetchone()["c"]
        汇总报文 = conn.execute(
            "SELECT COALESCE(SUM(报文数),0) AS c FROM 站点汇总账"
        ).fetchone()["c"]
        坏点 = conn.execute("SELECT COUNT(*) AS c FROM 坏点匣").fetchone()["c"]
        批次在栏, 失败收口批, 收口撕裂 = _批次视图(conn)
        return {
            "在栏": 在栏,
            "已汇总缓冲": int(已汇总缓冲),
            "汇总报文": int(汇总报文),
            "坏点": 坏点,
            "是否对齐": int(已汇总缓冲) == int(汇总报文) and not 收口撕裂,
            "批次在栏": 批次在栏,
            "失败收口批": 失败收口批,
            "收口撕裂": 收口撕裂,
        }
    finally:
        conn.close()
