"""争用失败测：两路会话同改栏规门槛又灌报文，双成则红。

约束：
- 分指标批与结栏并发缺锁会半分流；不加锁会双成功。
- 以账册版本（写纪元）乐观并发：同读旧版、后提交者拒装/拒回刷。
- 争用不得双写（不得同时改门槛又清空/重写缓冲）。
"""
from __future__ import annotations

import threading

from app.db import 连接
from app.services import 目录, 装载, 贯验, 校验
from app.services import 结栏 as 结栏服务


def _版本() -> int:
    规 = 目录.栏规()
    assert "账册版本" in 规, 规
    return int(规["账册版本"])


def _缓冲数() -> int:
    conn = 连接()
    try:
        return conn.execute("SELECT COUNT(*) AS c FROM 入栏缓冲").fetchone()["c"]
    finally:
        conn.close()


def test_同版争用只成一个且不双写():
    起 = _版本()
    结果: dict[str, dict] = {}
    障 = threading.Barrier(2)

    def 改律():
        障.wait()
        结果["改"] = 目录.改栏规({"PM25上限": "90", "期望账册版本": str(起)})

    def 装报():
        障.wait()
        结果["装"] = 装载.装一批({
            "期望账册版本": str(起),
            "批次编号": "争用",
            "报文": [{
                "报文编号": "C-争-1",
                "站点键": "站-河东",
                "指标键": "PM25",
                "读数": 10.0,
                "观测时": "2026-11-24T10:01:00Z",
            }],
        })

    甲 = threading.Thread(target=改律)
    乙 = threading.Thread(target=装报)
    甲.start(); 乙.start()
    甲.join(); 乙.join()

    改成功 = "错误" not in 结果["改"]
    装成功 = not 结果["装"].get("拒绝")
    assert 改成功 + 装成功 == 1, {"改": 结果["改"], "装": 结果["装"]}

    毕 = _版本()
    assert 毕 == 起 + 1, (起, 毕)

    if 装成功:
        assert _缓冲数() == 1
        assert 目录.栏规()["PM25上限"] == "75"
    else:
        assert _缓冲数() == 0
        assert 目录.栏规()["PM25上限"] == "90"
        assert "账册版本" in 结果["装"].get("拒因", "")

    # 争用不得双写：不得既改门槛又留下影子
    assert len(目录.影子列表()) == 0
    assert len(目录.门槛账册()) >= 1


def test_装载与结栏并发不半分流():
    r0 = 装载.装一批({
        "报文": [
            {"报文编号": "C-半-1", "站点键": "站-河东", "指标键": "PM25",
             "读数": 20.0, "观测时": "2026-11-24T10:10:00Z"},
            {"报文编号": "C-半-2", "站点键": "站-河东", "指标键": "PM25",
             "读数": 30.0, "观测时": "2026-11-24T10:20:00Z"},
        ]
    })
    assert r0["入栏"] == 2, r0

    障 = threading.Barrier(2)
    收: dict[str, dict] = {}

    def 再装():
        障.wait()
        收["装"] = 装载.装一批({
            "报文": [{"报文编号": "C-半-3", "站点键": "站-北岭", "指标键": "PM25",
                      "读数": 25.0, "观测时": "2026-11-24T10:30:00Z"}],
        })

    def 结栏():
        障.wait()
        收["结"] = 结栏服务.结当前栏()

    甲 = threading.Thread(target=再装)
    乙 = threading.Thread(target=结栏)
    甲.start(); 乙.start()
    甲.join(); 乙.join()

    assert 收["装"]["入栏"] == 1, 收["装"]

    g = 贯验.跑一次()
    assert g["是否对齐"] is True, g

    conn = 连接()
    try:
        缓冲 = conn.execute("SELECT * FROM 入栏缓冲").fetchall()
        汇总 = conn.execute("SELECT COALESCE(SUM(报文数),0) AS c FROM 站点汇总账").fetchone()["c"]
    finally:
        conn.close()
    已汇总 = [r for r in 缓冲 if r["命运"] == "已汇总"]
    在栏 = [r for r in 缓冲 if r["命运"] == "在栏"]
    assert len(已汇总) + len(在栏) == len(缓冲), [dict(r) for r in 缓冲]
    assert len(已汇总) == int(汇总), (len(已汇总), 汇总)
    当前 = 校验.门槛指纹(目录.栏规())
    assert all(r["门槛指纹"] == 当前 for r in 在栏), [dict(r) for r in 在栏]
