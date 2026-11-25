from __future__ import annotations
from app.db import 连接
from app.services import 收口


def 报文命运() -> dict:
    conn = 连接()
    try:
        rows = conn.execute(
            "SELECT 命运, COUNT(*) AS c FROM 观测报文 GROUP BY 命运"
        ).fetchall()
        return {r["命运"]: r["c"] for r in rows}
    finally:
        conn.close()


def 缓冲命运() -> dict:
    conn = 连接()
    try:
        rows = conn.execute(
            "SELECT 命运, COUNT(*) AS c FROM 入栏缓冲 GROUP BY 命运"
        ).fetchall()
        return {r["命运"]: r["c"] for r in rows}
    finally:
        conn.close()


def 按站点报文() -> dict:
    conn = 连接()
    try:
        rows = conn.execute(
            "SELECT 站点键, COUNT(*) AS c FROM 观测报文 GROUP BY 站点键"
        ).fetchall()
        return {r["站点键"]: r["c"] for r in rows}
    finally:
        conn.close()


def 装载批次摘要(限制: int = 20) -> list[dict]:
    conn = 连接()
    try:
        rows = conn.execute(
            """SELECT 编号,时刻,入流,入栏,坏点,收口,失败指纹
               FROM 装载批次 ORDER BY 时刻 DESC LIMIT ?""",
            (限制,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def 装载对账() -> dict:
    """半截账实与批次对账分轨核：账册成败口径 vs 正式表现行口径。"""
    conn = 连接()
    try:
        成功批次 = [
            r["编号"]
            for r in conn.execute(
                "SELECT 编号 FROM 装载批次 WHERE 收口=? ORDER BY 时刻",
                (收口.整批成功,),
            ).fetchall()
        ]
        失败批次 = [
            r["编号"]
            for r in conn.execute(
                "SELECT 编号 FROM 装载批次 WHERE 收口=? ORDER BY 时刻",
                (收口.失败清回,),
            ).fetchall()
        ]
        现行入流 = conn.execute("SELECT COUNT(*) AS c FROM 观测报文").fetchone()["c"]
        现行在栏 = conn.execute(
            "SELECT COUNT(*) AS c FROM 入栏缓冲 WHERE 命运='在栏'"
        ).fetchone()["c"]
        影子行数 = conn.execute(
            "SELECT COALESCE(SUM(影子入流),0) AS c FROM 装载批收口账 WHERE 收口=?",
            (收口.失败清回,),
        ).fetchone()["c"]
        return {
            "成功批数": len(成功批次),
            "失败批数": len(失败批次),
            "成功批次": 成功批次,
            "失败批次": 失败批次,
            "现行入流总数": int(现行入流),
            "现行在栏总数": int(现行在栏),
            "失败影子总行数": int(影子行数),
        }
    finally:
        conn.close()


def 结栏批次摘要(限制: int = 20) -> list[dict]:
    conn = 连接()
    try:
        rows = conn.execute(
            "SELECT 编号,栏号,时刻,汇总数 FROM 结栏批次 ORDER BY 时刻 DESC LIMIT ?",
            (限制,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def 按指标汇总() -> dict:
    conn = 连接()
    try:
        rows = conn.execute(
            "SELECT 指标键, COUNT(*) AS c, COALESCE(AVG(均值),0) AS 均 FROM 站点汇总账 GROUP BY 指标键"
        ).fetchall()
        return {r["指标键"]: {"笔数": r["c"], "均值": r["均"]} for r in rows}
    finally:
        conn.close()
