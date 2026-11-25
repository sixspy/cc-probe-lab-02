"""列表、栏规与分指标门槛账册。"""
from __future__ import annotations

from app.db import 串行写, 连接
from app.seed import 此刻
from app.services import 校验


def 栏规() -> dict:
    conn = 连接()
    try:
        return {r["键"]: r["值"] for r in conn.execute("SELECT 键,值 FROM 栏规").fetchall()}
    finally:
        conn.close()


def 改栏规(体: dict) -> dict:
    """改栏规/门槛：与装载、结栏同锁；每次改推账册版本，防双写。

    期望账册版本不匹配 → 显式拒绝（另一路会话已推进版本）。
    """
    错 = 校验.校验栏规补丁(体 or {})
    if 错:
        return {"错误": 校验.摘要错误(错), "栏规": 栏规()}
    体 = dict(体 or {})
    期望版 = 体.pop("期望账册版本", None)

    with 串行写() as conn:
        规 = {r["键"]: r["值"] for r in conn.execute("SELECT 键,值 FROM 栏规").fetchall()}
        当版 = int(规.get("账册版本", "1"))
        if 期望版 is not None:
            try:
                期望版 = int(期望版)
            except (TypeError, ValueError):
                return {"错误": f"期望账册版本非整数:{期望版!r}"}
            if 期望版 != 当版:
                return {
                    "错误": f"账册版本冲突：期望{期望版} 实际{当版}",
                    "拒因": "账册版本冲突",
                    "栏规": 规,
                }
        新版 = 当版 + 1
        变更 = {str(k): str(v) for k, v in 体.items() if k != "账册版本"}
        合并 = {**规, **变更}
        # 与存量合并后再校验一次：只改单边也不得把上下限拧成倒挂。
        for 指标, (lo, hi) in 校验.读门槛表(合并).items():
            if lo > hi:
                return {
                    "错误": f"{指标}下限不得大于上限（合并后 {lo}>{hi}）",
                    "栏规": 规,
                }
        for k, v in 变更.items():
            conn.execute(
                "INSERT INTO 栏规(键,值) VALUES (?,?) ON CONFLICT(键) DO UPDATE SET 值=excluded.值",
                (k, v),
            )
        conn.execute(
            "INSERT INTO 栏规(键,值) VALUES (?,?) ON CONFLICT(键) DO UPDATE SET 值=excluded.值",
            ("账册版本", str(新版)),
        )
        合并 = {**规, **变更}
        旧表 = 校验.读门槛表(规)
        新表 = 校验.读门槛表(合并)
        for 指标 in sorted(set(旧表) | set(新表)):
            if 旧表.get(指标) == 新表.get(指标):
                continue
            lo, hi = 新表.get(指标, (None, None))
            if lo is None or hi is None:
                continue
            conn.execute(
                """INSERT INTO 门槛账册(指标键,下限,上限,指纹,账册版本,时刻)
                   VALUES (?,?,?,?,?,?)""",
                (指标, f"{lo}", f"{hi}", 校验.指标指纹(合并, 指标), 新版, 此刻()),
            )
    return 栏规()


def 门槛账册(限制: int = 100) -> list[dict]:
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM 门槛账册 ORDER BY 序号 DESC LIMIT ?", (限制,)
            ).fetchall()
        ]
    finally:
        conn.close()


def 影子列表(限制: int = 200) -> list[dict]:
    """只读影子归档：错阈草稿在此，绝不并入正式过门槛集。"""
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM 影子归档 ORDER BY 编号 DESC LIMIT ?", (限制,)
            ).fetchall()
        ]
    finally:
        conn.close()


def 分门槛裁决探针(指标键: str, 读数: float) -> dict:
    """只读：按指标键取对应门槛给出裁决，不写库、不改版本。"""
    规 = 栏规()
    d = 校验.分门槛裁决(读数, 规, 指标键)
    return {
        "指标键": 指标键,
        "读数": 读数,
        "门槛表": {
            k: {"下限": v[0], "上限": v[1], "指纹": 校验.指标指纹(规, k)}
            for k, v in 校验.读门槛表(规).items()
        },
        "裁决": d,
        "账册版本": int(规.get("账册版本", "1")),
        "门槛指纹": 校验.门槛指纹(规),
        "写库": False,
    }


def 站点列表() -> list[dict]:
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 站点源 ORDER BY 源键").fetchall()]
    finally:
        conn.close()


def 报文列表(限制: int = 200) -> list[dict]:
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM 观测报文 ORDER BY 观测时 DESC LIMIT ?", (限制,)
            ).fetchall()
        ]
    finally:
        conn.close()


def 缓冲列表(命运: str | None = None) -> list[dict]:
    conn = 连接()
    try:
        if 命运:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM 入栏缓冲 WHERE 命运=? ORDER BY 观测时", (命运,)
                ).fetchall()
            ]
        return [dict(r) for r in conn.execute("SELECT * FROM 入栏缓冲 ORDER BY 观测时").fetchall()]
    finally:
        conn.close()


def 汇总列表(限制: int = 200) -> list[dict]:
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM 站点汇总账 ORDER BY 物化时 DESC LIMIT ?", (限制,)
            ).fetchall()
        ]
    finally:
        conn.close()


def 坏点列表(限制: int = 200) -> list[dict]:
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM 坏点匣 ORDER BY 编号 DESC LIMIT ?", (限制,)
            ).fetchall()
        ]
    finally:
        conn.close()


def 贯验列表(限制: int = 50) -> list[dict]:
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM 栏贯验 ORDER BY 编号 DESC LIMIT ?", (限制,)
            ).fetchall()
        ]
    finally:
        conn.close()


def 概览() -> dict:
    conn = 连接()
    try:
        return {
            "观测报文": conn.execute("SELECT COUNT(*) AS c FROM 观测报文").fetchone()["c"],
            "在栏": conn.execute("SELECT COUNT(*) AS c FROM 入栏缓冲 WHERE 命运='在栏'").fetchone()["c"],
            "站点汇总": conn.execute("SELECT COUNT(*) AS c FROM 站点汇总账").fetchone()["c"],
            "坏点": conn.execute("SELECT COUNT(*) AS c FROM 坏点匣").fetchone()["c"],
            "影子归档": conn.execute("SELECT COUNT(*) AS c FROM 影子归档").fetchone()["c"],
            "账册版本": int(栏规().get("账册版本", "1")),
            "门槛表": {k: {"下限": v[0], "上限": v[1], "指纹": 校验.指标指纹(栏规(), k)}
                      for k, v in 校验.读门槛表(栏规()).items()},
            "栏规": 栏规(),
        }
    finally:
        conn.close()


def 装载批次列表(限制: int = 50) -> list[dict]:
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT 编号,时刻,入流,入栏,坏点 FROM 装载批次 ORDER BY 时刻 DESC LIMIT ?",
                (限制,),
            ).fetchall()
        ]
    finally:
        conn.close()


def 结栏批次列表(限制: int = 50) -> list[dict]:
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT 编号,栏号,时刻,汇总数 FROM 结栏批次 ORDER BY 时刻 DESC LIMIT ?",
                (限制,),
            ).fetchall()
        ]
    finally:
        conn.close()


def 站点查(源键: str) -> dict | None:
    conn = 连接()
    try:
        r = conn.execute("SELECT * FROM 站点源 WHERE 源键=?", (源键,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()
