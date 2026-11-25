"""报文校验与分指标质控门槛。"""
from __future__ import annotations

import hashlib
import json

必填 = ("报文编号", "站点键", "指标键", "读数", "观测时")

# 未配置门槛的指标：显式放行并打「无门槛」分流标，绝不套用他指标的默认阈。
默认门槛指标 = ("PM25", "浊度")


def 校验报文(ev: dict) -> list[str]:
    if not isinstance(ev, dict):
        return ["报文不是对象"]
    错 = []
    for k in 必填:
        if ev.get(k) in (None, ""):
            错.append(f"缺字段:{k}")
    try:
        float(ev.get("读数"))
    except (TypeError, ValueError):
        错.append("读数非数值")
    编号 = str(ev.get("报文编号") or "")
    if 编号 and (" " in 编号 or "\t" in 编号):
        错.append("报文编号含空白")
    return 错


def 校验批次(体: dict) -> list[str]:
    if not isinstance(体, dict):
        return ["体须为对象"]
    报文 = 体.get("报文")
    if not isinstance(报文, list) or not 报文:
        return ["报文列表为空"]
    错 = []
    见 = set()
    for i, ev in enumerate(报文):
        for e in 校验报文(ev or {}):
            错.append(f"[{i}]{e}")
        编号 = str((ev or {}).get("报文编号", ""))
        if 编号 and 编号 in 见:
            错.append(f"[{i}]报文编号重复")
        if 编号:
            见.add(编号)
    return 错


def 门键(指标键: str, 端: str) -> str:
    return f"门槛:{指标键}:{端}"


def 读门槛表(规: dict) -> dict[str, tuple[float, float]]:
    """从栏规里读分指标门槛表：{指标键: (下限, 上限)}。

    来源二选一（同一指标以显式门槛键为准）：
    - 分指标键 `门槛:<指标>:下限|上限`
    - 兼容基线 PM25 的 `PM25下限|PM25上限`
    未配置的指标不在表中，裁决时显式放行而非套默认阈。
    """
    规 = 规 or {}
    表: dict[str, list] = {}
    for k, v in 规.items():
        if not isinstance(k, str):
            continue
        if k.startswith("门槛:"):
            段 = k.split(":")
            if len(段) != 3 or not 段[1]:
                continue
            指标, 端 = 段[1], 段[2]
            if 端 not in ("下限", "上限"):
                continue
            try:
                值 = float(v)
            except (TypeError, ValueError):
                continue
            表.setdefault(指标, [None, None])[0 if 端 == "下限" else 1] = 值
    if "PM25" in 表:
        lo, hi = 表["PM25"]
        if lo is None:
            try:
                表["PM25"][0] = float(规.get("PM25下限", "0"))
            except (TypeError, ValueError):
                pass
        if hi is None:
            try:
                表["PM25"][1] = float(规.get("PM25上限", "75"))
            except (TypeError, ValueError):
                pass
    else:
        try:
            lo = float(规.get("PM25下限", "0"))
            hi = float(规.get("PM25上限", "75"))
            表["PM25"] = [lo, hi]
        except (TypeError, ValueError):
            pass
    out: dict[str, tuple[float, float]] = {}
    for 指标, (lo, hi) in 表.items():
        if lo is None:
            lo = 0.0
        if hi is None:
            hi = 75.0
        out[指标] = (float(lo), float(hi))
    return out


def 指标指纹(规: dict, 指标键: str) -> str:
    表 = 读门槛表(规)
    if 指标键 not in 表:
        return "无门槛"
    lo, hi = 表[指标键]
    return hashlib.sha256(f"{指标键}|{lo:.6f}|{hi:.6f}".encode("utf-8")).hexdigest()[:12]


def 门槛指纹(规: dict) -> str:
    """整张门槛表的稳定指纹；门槛一变，旧命运不得回刷。"""
    表 = 读门槛表(规)
    形 = [[k, round(表[k][0], 6), round(表[k][1], 6)] for k in sorted(表)]
    摘 = hashlib.sha256(json.dumps(形, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    return 摘.hexdigest()[:12]


def 分门槛裁决(读数: float, 规: dict, 指标键: str) -> dict:
    """按指标键取对应门槛，返回入栏/坏点裁决。

    裁决是「缓冲与坏点同票」的唯一出处：装载、结栏回刷、只读探针都用它。
    """
    表 = 读门槛表(规)
    try:
        读数 = float(读数)
    except (TypeError, ValueError):
        return {
            "指标键": 指标键, "读数": None, "下限": None, "上限": None,
            "过门槛": False, "裁决": "坏点", "受控": False,
            "原因": "读数非数值", "门槛指纹": 门槛指纹(规),
        }
    受控 = 指标键 in 表
    if not 受控:
        return {
            "指标键": 指标键, "读数": 读数, "下限": None, "上限": None,
            "过门槛": True, "裁决": "入栏", "受控": False,
            "原因": f"{指标键}未配置门槛-显式放行", "门槛指纹": 门槛指纹(规),
            "分流": "无门槛-放行",
        }
    lo, hi = 表[指标键]
    if lo > hi:
        return {
            "指标键": 指标键, "读数": 读数, "下限": lo, "上限": hi,
            "过门槛": False, "裁决": "坏点", "受控": True,
            "原因": f"{指标键}栏规阈值损坏[{lo},{hi}]", "门槛指纹": 门槛指纹(规),
        }
    if 读数 < lo or 读数 > hi:
        return {
            "指标键": 指标键, "读数": 读数, "下限": lo, "上限": hi,
            "过门槛": False, "裁决": "坏点", "受控": True,
            "原因": f"{指标键}越界[{lo},{hi}]", "门槛指纹": 门槛指纹(规),
        }
    return {
        "指标键": 指标键, "读数": 读数, "下限": lo, "上限": hi,
        "过门槛": True, "裁决": "入栏", "受控": True,
        "原因": "过门槛", "门槛指纹": 门槛指纹(规),
    }


def 过门槛(读数: float, 规: dict, 指标键: str) -> tuple[bool, str]:
    """兼容入口：返回 (是否过门槛, 原因)。按指标键取对应门槛。"""
    d = 分门槛裁决(读数, 规, 指标键)
    return bool(d["过门槛"]), d["原因"]


def 摘要错误(错: list[str], 上限: int = 8) -> str:
    if not 错:
        return ""
    head = 错[:上限]
    more = len(错) - len(head)
    text = "; ".join(head)
    if more > 0:
        text += f" …另有{more}条"
    return text


门槛键白名单 = ("下限", "上限")


def 校验栏规补丁(体: dict) -> list[str]:
    if not isinstance(体, dict):
        return ["栏规补丁须为对象"]
    错: list[str] = []
    for k in ("PM25上限", "PM25下限", "标定偏移上限", "账册版本", "期望账册版本"):
        if k in 体:
            try:
                float(体[k])
            except Exception:
                错.append(f"{k}非数值")
    if "PM25上限" in 体 and "PM25下限" in 体:
        try:
            if float(体["PM25下限"]) > float(体["PM25上限"]):
                错.append("PM25下限不得大于上限")
        except Exception:
            pass
    逐指标: dict[str, dict] = {}
    for k in 体:
        if not isinstance(k, str) or not k.startswith("门槛:"):
            continue
        段 = k.split(":")
        if len(段) != 3 or not 段[1] or 段[2] not in 门槛键白名单:
            错.append(f"门槛键格式错误:{k}")
            continue
        try:
            float(体[k])
        except Exception:
            错.append(f"{k}非数值")
            continue
        逐指标.setdefault(段[1], {})[段[2]] = float(体[k])
    for 指标, 门 in 逐指标.items():
        if 门.get("下限") is not None and 门.get("上限") is not None and 门["下限"] > 门["上限"]:
            错.append(f"{指标}下限不得大于上限")
    return 错


def 指标是否受控(指标键: str, 规: dict | None = None) -> bool:
    if 规 is not None:
        return 指标键 in 读门槛表(规)
    return 指标键 in 默认门槛指标
