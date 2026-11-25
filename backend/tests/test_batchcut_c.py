"""争用失败测：收口路上二次补灌并发，互斥缺失则半截双成。

两线程同时装一批，其中一批在写入前半后炸：
- 装载须串行化，失败批整批清回，成功批整批留，不得各留半截；
- 两批的收口账指纹独立，贯验无撕裂，对账两轨分清。
"""
import threading

from app import db
from app.services import 装载, 统计, 贯验, 收口


def _成批(前缀: str, n: int) -> dict:
    return {
        "批次编号": 前缀,
        "报文": [
            {
                "报文编号": f"{前缀}-{i}",
                "站点键": "站-湖西",
                "指标键": "浊度",
                "读数": 1.0 + i * 0.1,
                "观测时": f"2026-11-25T10:{i:02d}:00Z",
            }
            for i in range(n)
        ],
    }


class _进半截再放并发:
    """失败线程进锁、写两条后抛错；成功线程在门上等，验证不与收口交错。"""

    def __init__(self):
        self.失败线程已入锁 = threading.Event()
        self.成功线程到门口 = threading.Event()

    def 失败钩(self, 阶段, ev, 序号, 批次):
        if 批次.startswith("丙-断") and 阶段 == "报文落库后" and 序号 == 1:
            self.失败线程已入锁.set()
            # 等成功线程真的来撞门，再抛错，逼出并发窗口
            assert self.成功线程到门口.wait(timeout=5)
            raise RuntimeError("收口路上炸")


def _计数(sql: str, 参数=()) -> int:
    conn = db.连接()
    try:
        return int(conn.execute(sql, 参数).fetchone()[0])
    finally:
        conn.close()


def test_收口与补灌并发不得半截双成(monkeypatch):
    门 = _进半截再放并发()
    原装 = 装载.装一批

    def 装失败批():
        # 故障钩只对失败批生效
        monkeypatch.setattr(装载, "装载故障点", 门.失败钩)
        return 原装(_成批("丙-断", 4))

    def 装成功批():
        门.成功线程到门口.set()
        return 原装(_成批("丙-好", 3))

    结果 = {}

    def 跑(名, fn):
        结果[名] = fn()

    t1 = threading.Thread(target=跑, args=("断", 装失败批))
    t2 = threading.Thread(target=跑, args=("好", 装成功批))
    t1.start()
    assert 门.失败线程已入锁.wait(timeout=5)
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)
    assert not t1.is_alive() and not t2.is_alive()

    断批 = 结果["断"]["批次编号"]
    好批 = 结果["好"]["批次编号"]
    assert 结果["断"]["收口"] == "失败清回"
    assert 结果["好"]["收口"] == "整批成功"

    # 失败批：正式表零残留
    assert _计数("SELECT COUNT(*) FROM 观测报文 WHERE 批次编号=?", (断批,)) == 0
    assert _计数("SELECT COUNT(*) FROM 入栏缓冲 WHERE 批次编号=?", (断批,)) == 0
    # 成功批：整批三行全在，未被回滚误伤
    assert _计数("SELECT COUNT(*) FROM 观测报文 WHERE 批次编号=?", (好批,)) == 3
    assert _计数("SELECT COUNT(*) FROM 入栏缓冲 WHERE 批次编号=?", (好批,)) == 3
    assert 结果["好"]["入栏"] == 3

    # 收口账两笔独立指纹
    断账 = 收口.批次收口查(断批)
    好账 = 收口.批次收口查(好批)
    assert 断账["收口"] == "失败清回" and 断账["失败指纹"]
    assert 好账["收口"] == "整批成功"
    assert len(断账["影子明细"]) == 2
    assert 好账["影子明细"] == []

    # 贯验不撕裂，按批次可分；对账两轨
    快照 = 贯验.只读快照()
    assert 快照["收口撕裂"] == []
    assert 快照["批次在栏"].get(好批) == 3
    assert 断批 not in 快照["批次在栏"]
    对账 = 统计.装载对账()
    assert 对账["成功批数"] == 1 and 对账["失败批数"] == 1
    assert 对账["现行入流总数"] == 3
