"""栏贯验：正式轨（已汇总）== 汇总账报文数；影子草稿单列，不并入正式对账。"""
from __future__ import annotations

from app.db import 连接
from app.seed import 此刻


def _读账(conn) -> dict:
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
    影子 = conn.execute("SELECT COUNT(*) AS c FROM 影子归档").fetchone()["c"]
    return {
        "在栏": int(在栏),
        "已汇总缓冲": int(已汇总缓冲),
        "汇总报文": int(汇总报文),
        "坏点": int(坏点),
        "影子笔数": int(影子),
        "是否对齐": int(已汇总缓冲) == int(汇总报文),
    }


def 跑一次() -> dict:
    conn = 连接()
    try:
        账 = _读账(conn)
        说明 = (
            "正式轨已汇总与站点汇总报文数一致；影子单列不计入"
            if 账["是否对齐"]
            else f"撕裂：已汇总缓冲={账['已汇总缓冲']} 汇总报文={账['汇总报文']}"
        )
        时刻 = 此刻()
        conn.execute(
            """INSERT INTO 栏贯验(时刻,在栏笔数,汇总报文数,坏点笔数,是否对齐,说明,影子笔数)
               VALUES (?,?,?,?,?,?,?)""",
            (时刻, 账["在栏"], 账["汇总报文"], 账["坏点"], int(账["是否对齐"]),
             说明, 账["影子笔数"]),
        )
        conn.commit()
        return {"时刻": 时刻, **账, "说明": 说明, "影子单列": True}
    finally:
        conn.close()


def 只读快照() -> dict:
    """不落库的贯验快照，供页面预览。"""
    conn = 连接()
    try:
        return _读账(conn)
    finally:
        conn.close()
