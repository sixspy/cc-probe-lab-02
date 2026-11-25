"""结栏：在栏缓冲按站点+指标汇总物化；改门槛后旧指纹命运拒回刷。"""
from __future__ import annotations

import json
import uuid
from collections import defaultdict

from app.db import 串行写
from app.db import 连接 as 连接器
from app.seed import 此刻
from app.services import 校验, 目录


def _汇总(conn, 栏号: str, 时刻: str) -> tuple[dict, list[dict]]:
    """用给定连接（已持写锁）的当前门槛表，对缓冲做分流物化。"""
    规 = {r["键"]: r["值"] for r in conn.execute("SELECT 键,值 FROM 栏规").fetchall()}
    当前指纹 = 校验.门槛指纹(规)
    批 = f"结栏-{uuid.uuid4().hex[:8]}"

    rows = conn.execute(
        "SELECT * FROM 入栏缓冲 WHERE 栏号=? AND 命运='在栏'", (栏号,)
    ).fetchall()

    groups: dict[tuple[str, str], list] = defaultdict(list)
    过时 = 0
    for r in rows:
        if r["门槛指纹"] != 当前指纹:
            # 旧门槛下的命运不得回刷进新门槛的正式汇总：转只读影子归档。
            conn.execute(
                """INSERT INTO 影子归档
                   (报文编号,站点键,指标键,读数,观测时,草稿命运,原因,门槛指纹,只读,归档时)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (r["报文编号"], r["站点键"], r["指标键"], r["读数"], r["观测时"],
                 "入栏(旧门槛)", f"门槛已改，旧指纹{r['门槛指纹']}拒回刷，转影子",
                 r["门槛指纹"], 1, 时刻),
            )
            conn.execute("UPDATE 入栏缓冲 SET 命运=? WHERE 报文编号=?", ("过时", r["报文编号"]))
            conn.execute("UPDATE 观测报文 SET 命运=? WHERE 报文编号=?", ("已过时", r["报文编号"]))
            过时 += 1
            continue
        groups[(r["站点键"], r["指标键"])].append(r)

    汇总 = 0
    明细 = []
    for (站点, 指标), evs in groups.items():
        均值 = sum(float(e["读数"]) for e in evs) / len(evs)
        编号 = f"汇-{栏号}-{站点}-{指标}-{uuid.uuid4().hex[:6]}"
        conn.execute(
            """INSERT INTO 站点汇总账
               (汇总编号,栏号,站点键,指标键,报文数,均值,物化时,命运,门槛指纹)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (编号, 栏号, 站点, 指标, len(evs), 均值, 时刻, "已汇总", 当前指纹),
        )
        for e in evs:
            # 保留缓冲行并转「已汇总」，供贯验互证；重复结栏按命运过滤不重计。
            conn.execute("UPDATE 入栏缓冲 SET 命运=? WHERE 报文编号=?", ("已汇总", e["报文编号"]))
            conn.execute("UPDATE 观测报文 SET 命运=? WHERE 报文编号=?", ("已汇总", e["报文编号"]))
        汇总 += 1
        明细.append({
            "汇总编号": 编号,
            "站点键": 站点,
            "指标键": 指标,
            "报文数": len(evs),
            "均值": round(均值, 4),
            "门槛指纹": 当前指纹,
        })

    报告 = {
        "批次编号": 批,
        "栏号": 栏号,
        "汇总数": 汇总,
        "缓冲消耗": sum(len(v) for v in groups.values()),
        "归档过时": 过时,
        "明细": 明细,
        "空栏": 汇总 == 0 and 过时 == 0,
        "门槛指纹": 当前指纹,
    }
    conn.execute(
        """INSERT INTO 结栏批次(编号,栏号,时刻,汇总数,报告) VALUES (?,?,?,?,?)""",
        (批, 栏号, 时刻, 汇总, json.dumps(报告, ensure_ascii=False)),
    )
    return 报告, 明细


def 结当前栏() -> dict:
    规 = 目录.栏规()
    栏号 = 规.get("当前栏号", "B-demo")
    with 串行写() as conn:
        报告, _ = _汇总(conn, 栏号, 此刻())
    return 报告


def 预览结栏() -> dict:
    """只读：当前栏在栏缓冲按站点指标分组，不写库。"""
    规 = 目录.栏规()
    栏号 = 规.get("当前栏号", "B-demo")
    当前指纹 = 校验.门槛指纹(规)
    连接 = 连接器()
    try:
        rows = 连接.execute(
            "SELECT * FROM 入栏缓冲 WHERE 栏号=? AND 命运 IN ('在栏','过时')", (栏号,)
        ).fetchall()
        groups: dict[tuple[str, str], list] = defaultdict(list)
        过时数 = 0
        for r in rows:
            if r["命运"] == "过时" or r["门槛指纹"] != 当前指纹:
                过时数 += 1
                continue
            groups[(r["站点键"], r["指标键"])].append(dict(r))
        预览 = []
        for (站点, 指标), evs in sorted(groups.items()):
            预览.append({
                "站点键": 站点,
                "指标键": 指标,
                "报文数": len(evs),
                "均值": round(sum(float(e["读数"]) for e in evs) / len(evs), 4),
                "门槛指纹": 当前指纹,
            })
        return {
            "栏号": 栏号,
            "在栏": len(rows),
            "将汇总组": 预览,
            "过时": 过时数,
            "门槛指纹": 当前指纹,
        }
    finally:
        连接.close()
