"""并发双请求脚本：两路会话同改栏规门槛又灌报文，验证只成一路、不双写。

用法（对本仓真实服务，非 pytest）：
    python tests/并发双请求脚本.py http://127.0.0.1:8120
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

import httpx

基址 = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PROBE_BASE", "http://127.0.0.1:8120")


async def 取版本(c: httpx.AsyncClient) -> str:
    r = await c.get(f"{基址}/api/栏规")
    r.raise_for_status()
    return r.json()["账册版本"]


async def main() -> int:
    async with httpx.AsyncClient(timeout=15) as c:
        版 = await 取版本(c)
        报文体 = {
            "期望账册版本": 版,
            "批次编号": "并发",
            "报文": [{
                "报文编号": "D-并-1", "站点键": "站-河东", "指标键": "PM25",
                "读数": 10.0, "观测时": "2026-11-24T11:00:00Z",
            }],
        }
        律体 = {"期望账册版本": 版, "PM25上限": "90"}
        先 = asyncio.Event()

        async def 改律():
            await 先.wait()
            return await c.post(f"{基址}/api/栏规", json=律体)

        async def 装报():
            await 先.wait()
            return await c.post(f"{基址}/api/观测报文/装载", json=报文体)

        甲, 乙 = asyncio.create_task(改律()), asyncio.create_task(装报())
        先.set()
        改r, 装r = await 甲, await 乙

        改成 = 改r.status_code == 200 and "错误" not in 改r.json()
        装j = 装r.json()
        装成 = 装r.status_code == 200 and not 装j.get("拒绝")

        print("改栏规:", 改r.status_code, json.dumps(改r.json(), ensure_ascii=False)[:160])
        print("装载:", 装r.status_code, json.dumps(装j, ensure_ascii=False)[:160])

        毕 = await 取版本(c)
        ok = (改成 + 装成) == 1 and int(毕) == int(版) + 1
        if 装成:
            ok = ok and 装j.get("入栏") == 1
        print(f"版本 {版} → {毕}；恰成一路={ (改成 + 装成) == 1 }")
        print("并发双请求验证:", "绿" if ok else "红")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
