"""失败测甲：错指标阈值下正式入栏仍增则红。

场景：水质（浊度）读数被大气（PM25）阈值误放。
- PM25 门槛 [0, 75]；浊度门槛 [0, 5]。
- 浊度 6.0 在 PM25 阈值下会过、在本指标阈值下必坏点。
- 若正式入栏（入栏缓冲）因此增行，说明仍按错指标/默认阈值分流 → 红。
"""
from __future__ import annotations

import pytest

from app.db import 连接
from app.services import 校验, 装载, 目录


浊度门 = {"门槛:浊度:下限": "0", "门槛:浊度:上限": "5"}


def _置浊度门() -> dict:
    out = 目录.改栏规(dict(浊度门))
    assert "错误" not in out, out
    return out


def _在栏(编号: str):
    conn = 连接()
    try:
        return conn.execute(
            "SELECT * FROM 入栏缓冲 WHERE 报文编号=?", (编号,)
        ).fetchone()
    finally:
        conn.close()


def _坏点(编号: str):
    conn = 连接()
    try:
        return conn.execute(
            "SELECT * FROM 坏点匣 WHERE 报文编号=?", (编号,)
        ).fetchone()
    finally:
        conn.close()


def test_错指标阈值不增现行入栏():
    _置浊度门()
    报告 = 装载.装一批({
        "报文": [{
            "报文编号": "A-浊-6",
            "站点键": "站-湖西",
            "指标键": "浊度",
            "读数": 6.0,
            "观测时": "2026-11-24T08:05:00Z",
        }]
    })
    assert 报告["入栏"] == 0, 报告
    assert 报告["坏点"] == 1, 报告
    assert _在栏("A-浊-6") is None
    bp = _坏点("A-浊-6")
    assert bp is not None
    assert "浊度" in bp["原因"]


def test_同一读数分指标分流():
    """同一个读数 6.0：PM25 过门槛，浊度不过门槛。"""
    _置浊度门()
    r浊 = 装载.装一批({
        "报文": [{
            "报文编号": "A-浊-1.2",
            "站点键": "站-湖西",
            "指标键": "浊度",
            "读数": 1.2,
            "观测时": "2026-11-24T08:06:00Z",
        }, {
            "报文编号": "A-浊-6b",
            "站点键": "站-湖西",
            "指标键": "浊度",
            "读数": 6.0,
            "观测时": "2026-11-24T08:07:00Z",
        }]
    })
    assert r浊["入栏"] == 1, r浊
    assert r浊["坏点"] == 1, r浊
    r气 = 装载.装一批({
        "报文": [{
            "报文编号": "A-PM-6",
            "站点键": "站-河东",
            "指标键": "PM25",
            "读数": 6.0,
            "观测时": "2026-11-24T08:08:00Z",
        }]
    })
    assert r气["入栏"] == 1, r气
    assert _在栏("A-浊-1.2") is not None
    assert _在栏("A-浊-6b") is None
    assert _在栏("A-PM-6") is not None


def test_分门槛裁决按指标取阈():
    _置浊度门()
    规 = 目录.栏规()
    d浊 = 校验.分门槛裁决(6.0, 规, "浊度")
    assert d浊["过门槛"] is False
    assert d浊["裁决"] == "坏点"
    assert float(d浊["上限"]) == 5.0
    d气 = 校验.分门槛裁决(6.0, 规, "PM25")
    assert d气["过门槛"] is True
    assert d气["裁决"] == "入栏"
    assert float(d气["上限"]) == 75.0


@pytest.mark.asyncio
async def test_分门槛裁决只读接口不写库():
    _置浊度门()
    n0 = len(目录.缓冲列表())
    from app.main import app

    async with app.test_client() as c:
        r = await c.get("/api/分门槛裁决", query_string={"指标键": "浊度", "读数": 6})
        assert r.status_code == 200, r.status_code
        d = await r.get_json()
        assert d["裁决"]["裁决"] == "坏点", d
        assert d["裁决"]["指标键"] == "浊度", d
    assert len(目录.缓冲列表()) == n0
