"""质控分门槛入栏（已落地）

契约：
- 不同指标可用不同上下限，门槛表与入栏同票；裁决唯一出处 校验.分门槛裁决。
- 错指标阈值下，正式入栏不得增行：错阈点进只读影子归档（双写两轨）。
- 改门槛即推账册版本并钉指纹；旧指纹命运在结栏时拒回刷，转影子归档。
- 装载/改门槛/结栏同经 串行写 写锁，分指标批与结栏并发不半分流。
- 不改坏基线默认门槛 happy path（PM25 [0,75]、浊度 [0,5]）。
"""
from __future__ import annotations

from app.services import 校验, 目录

NAME = "质控分门槛入栏"
CONTRACT = "不同指标可用不同上下限，门槛表与入栏同票"
HOOKS = ("before_load", "after_load", "decide_gate", "before_close", "after_close", "extra_verify_checks")


def describe() -> dict:
    return {"空桩": NAME, "契约": CONTRACT, "钩子": list(HOOKS), "默认启用": True}


def before_load(batch: dict) -> dict:
    return batch


def after_load(report: dict) -> dict:
    return report


def decide_gate(event: dict, rules: dict) -> str:
    """按报文指标键取对应门槛，返回 入栏/坏点（与装载同出处）。"""
    d = 校验.分门槛裁决(event.get("读数"), rules or {}, event.get("指标键"))
    return d["裁决"]


def before_close(pen_id: str) -> None:
    return None


def after_close(report: dict) -> dict:
    return report


def extra_verify_checks(snapshot: dict) -> list[str]:
    错 = []
    if snapshot.get("影子笔数", 0) and snapshot.get("已汇总缓冲", 0) != snapshot.get("汇总报文", 0):
        错.append("影子与正式混读")
    return 错
