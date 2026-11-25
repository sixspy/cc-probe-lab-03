#!/usr/bin/env python3
"""并发双请求收口脚本（probe-03）。

场景：同一进程内两批装载并发——
- 断批：写入前半（2 条）后注入故障，须整批失败清回、钉失败指纹；
- 好批：断批占锁期间来撞门（二次补灌），须等锁后整批成功；
- 验收：不得半截双成；正式表只有好批整批；收口账两笔独立；贯验无撕裂。

用法（服务层，自带临时库，不碰正式数据）：
    python3 scripts/并发双请求收口.py
HTTP 模式（对正在跑的容器，仅能灌正常批，故障注入走测试钩故不适用）：
    python3 scripts/并发双请求收口.py --http http://127.0.0.1:8120
"""
from __future__ import annotations
import json
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(ROOT))


def _成批(前缀: str, n: int) -> dict:
    return {
        "批次编号": 前缀,
        "报文": [
            {
                "报文编号": f"{前缀}-{i}",
                "站点键": "站-湖西",
                "指标键": "浊度",
                "读数": 1.0 + i * 0.1,
                "观测时": f"2026-11-25T11:{i:02d}:00Z",
            }
            for i in range(n)
        ],
    }


def 跑服务层() -> int:
    临时 = Path(tempfile.mkdtemp(prefix="probe-并发-"))
    import os
    os.environ["数据目录"] = str(临时)
    os.environ["夹具目录"] = str(ROOT.parent / "fixtures")
    from app import db, seed
    db.数据目录 = 临时
    db.库路径 = 临时 / "探栏.db"
    seed.初始化库()
    from app.services import 装载, 统计, 贯验, 收口

    门 = {"断批入锁": threading.Event(), "好批撞门": threading.Event()}

    def 故障钩(阶段, ev, 序号, 批次):
        if 批次.startswith("并发-断") and 阶段 == "报文落库后" and 序号 == 1:
            门["断批入锁"].set()
            if not 门["好批撞门"].wait(timeout=5):
                raise RuntimeError("好批未在收口窗口内撞门")
            raise RuntimeError("收口路上注入故障")

    装载.装载故障点 = 故障钩
    结果: dict[str, dict] = {}

    def 断批():
        结果["断"] = 装载.装一批(_成批("并发-断", 4))

    def 好批():
        门["好批撞门"].set()
        结果["好"] = 装载.装一批(_成批("并发-好", 3))

    t1 = threading.Thread(target=断批)
    t2 = threading.Thread(target=好批)
    t1.start()
    assert 门["断批入锁"].wait(timeout=5), "断批未进锁"
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)
    assert not t1.is_alive() and not t2.is_alive(), "线程未结束，疑似死锁"

    断号, 好号 = 结果["断"]["批次编号"], 结果["好"]["批次编号"]
    conn = db.连接()
    try:
        断观测 = conn.execute("SELECT COUNT(*) c FROM 观测报文 WHERE 批次编号=?", (断号,)).fetchone()["c"]
        断在栏 = conn.execute("SELECT COUNT(*) c FROM 入栏缓冲 WHERE 批次编号=?", (断号,)).fetchone()["c"]
        好观测 = conn.execute("SELECT COUNT(*) c FROM 观测报文 WHERE 批次编号=?", (好号,)).fetchone()["c"]
        好在栏 = conn.execute("SELECT COUNT(*) c FROM 入栏缓冲 WHERE 批次编号=?", (好号,)).fetchone()["c"]
    finally:
        conn.close()

    对账 = 统计.装载对账()
    快照 = 贯验.只读快照()
    检查 = [
        ("断批收口=失败清回", 结果["断"]["收口"] == "失败清回"),
        ("好批收口=整批成功", 结果["好"]["收口"] == "整批成功"),
        ("断批正式观测零残留", 断观测 == 0),
        ("断批正式在栏零残留", 断在栏 == 0),
        ("好批整批观测3行", 好观测 == 3),
        ("好批整批在栏3行", 好在栏 == 3),
        ("对账成功1失败1", (对账["成功批数"], 对账["失败批数"]) == (1, 1)),
        ("现行入流=3", 对账["现行入流总数"] == 3),
        ("贯验无收口撕裂", 快照["收口撕裂"] == []),
        ("好批在栏集合可分", 快照["批次在栏"].get(好号) == 3 and 断号 not in 快照["批次在栏"]),
    ]
    print("== 并发双请求收口验收 ==")
    for 名, ok in 检查:
        print(f"[{'绿' if ok else '红'}] {名}")
    print("断批失败指纹:", 结果["断"]["失败指纹"])
    print("断批影子明细:", json.dumps(收口.批次收口查(断号)["影子明细"], ensure_ascii=False))
    return 0 if all(ok for _, ok in 检查) else 1


def 跑http(基址: str) -> int:
    import urllib.request
    import urllib.parse

    def post(路径: str, 体: dict) -> dict:
        转义路径 = urllib.parse.quote(路径)
        req = urllib.request.Request(
            基址.rstrip("/") + 转义路径,
            data=json.dumps(体).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))

    体 = _成批("并发HTTP", 3)
    结果 = [None, None]

    def 一(i: int):
        体i = json.loads(json.dumps(体))
        体i["批次编号"] = f"并发HTTP-{i}"
        for ev in 体i["报文"]:
            ev["报文编号"] = f"并发HTTP-{i}-" + ev["报文编号"]
        结果[i] = post("/api/观测报文/装载", 体i)

    ts = [threading.Thread(target=一, args=(i,)) for i in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=15)
    print("== HTTP 并发两批（正常批，验证串行不互毁）==")
    for r in 结果:
        print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--http":
        raise SystemExit(跑http(sys.argv[2]))
    raise SystemExit(跑服务层())
