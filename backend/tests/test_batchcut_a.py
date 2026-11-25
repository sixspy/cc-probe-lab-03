"""失败测甲：装载批中途失败 → 切流账册清回，正式在栏不得残留前半截。

红条件（任一成立即红）：
- 装一批失败后报告没有「收口=失败清回」与失败指纹；
- 观测报文 / 入栏缓冲 / 坏点匣任一正式表仍留该批前半行；
- 批收口只读接口分不开「影子前半」与「现行在栏」；
- 贯验快照不能按批次区分在栏集合，或报收口撕裂。
"""
from app import db
from app.services import 装载, 结栏, 贯验, 目录, 收口, 夹具


def _成批(前缀: str, n: int = 4) -> dict:
    return {
        "批次编号": 前缀,
        "报文": [
            {
                "报文编号": f"{前缀}-{i}",
                "站点键": "站-河东",
                "指标键": "PM25",
                "读数": 20.0 + i,
                "观测时": f"2026-11-25T08:{i:02d}:00Z",
            }
            for i in range(n)
        ],
    }


def _计数(sql: str, 参数=()) -> int:
    conn = db.连接()
    try:
        return int(conn.execute(sql, 参数).fetchone()[0])
    finally:
        conn.close()


def _装中断(monkeypatch, 在第几条后: int) -> None:
    计数 = {"i": 0}

    def 钩子(阶段: str, ev: dict, 序号: int, 批次: str) -> None:
        if 阶段 == "报文落库后":
            计数["i"] += 1
            if 计数["i"] == 在第几条后:
                raise RuntimeError("模拟传感报文写入中断")

    monkeypatch.setattr(装载, "装载故障点", 钩子)


def test_批中断清回_正式在栏零行(monkeypatch):
    _装中断(monkeypatch, 2)
    报告 = 装载.装一批(_成批("甲批", 4))
    批次 = 报告["批次编号"]

    # 收口形态：失败清回 + 钉失败指纹，且前半截确实曾写入（不是假装没跑）
    assert 报告["收口"] == "失败清回"
    assert 报告["失败指纹"]
    assert 报告["入流"] == 2
    assert 报告["入栏"] == 2

    # 正式表三集合整批清回，不留前半
    assert _计数("SELECT COUNT(*) FROM 观测报文 WHERE 批次编号=?", (批次,)) == 0
    assert _计数("SELECT COUNT(*) FROM 入栏缓冲 WHERE 批次编号=?", (批次,)) == 0
    assert _计数("SELECT COUNT(*) FROM 坏点匣 WHERE 批次编号=?", (批次,)) == 0
    assert 目录.缓冲列表() == []

    # 只读收口接口：影子前半与现行零行必须能分开
    查 = 收口.批次收口查(批次)
    assert 查["收口"] == "失败清回"
    assert 查["失败指纹"] == 报告["失败指纹"]
    assert 查["现行观测"] == 0
    assert 查["现行在栏"] == 0
    assert len(查["影子明细"]) == 2
    assert {行["报文编号"] for 行 in 查["影子明细"]} == {"甲批-0", "甲批-1"}

    # 贯验读到的在栏集合按批次可分，失败批不在现行在栏，无撕裂
    快照 = 贯验.只读快照()
    assert 批次 not in 快照["批次在栏"]
    assert 快照["收口撕裂"] == []
    assert 批次 in 快照["失败收口批"]


def test_失败后纯成功成片仍主边同成():
    报告 = 装载.装一批(夹具.读取("入栏成汇总样例"))
    assert 报告["收口"] == "整批成功"
    assert 报告["失败指纹"] == ""
    assert 报告["入栏"] == 3
    结栏.结当前栏()
    assert 贯验.跑一次()["是否对齐"] is True


def test_批次预检失败亦收口不写正式表():
    报告 = 装载.装一批({"批次编号": "空批", "报文": []})
    assert 报告["收口"] == "失败清回"
    assert 报告["失败指纹"]
    assert "批次预检" in 报告["失败原因"]
    assert _计数("SELECT COUNT(*) FROM 观测报文") == 0
    assert _计数("SELECT COUNT(*) FROM 入栏缓冲") == 0
    账 = 收口.收口账列表()
    assert any(行["批次编号"] == 报告["批次编号"] and 行["收口"] == "失败清回" for 行 in 账)
