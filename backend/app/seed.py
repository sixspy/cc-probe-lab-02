from datetime import datetime, timezone
from app.db import 连接

建表 = """
CREATE TABLE IF NOT EXISTS 栏规 (
  键 TEXT PRIMARY KEY,
  值 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 门槛账册 (
  序号 INTEGER PRIMARY KEY AUTOINCREMENT,
  指标键 TEXT NOT NULL,
  下限 TEXT NOT NULL,
  上限 TEXT NOT NULL,
  指纹 TEXT NOT NULL,
  账册版本 INTEGER NOT NULL,
  时刻 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 站点源 (
  源键 TEXT PRIMARY KEY,
  名称 TEXT NOT NULL,
  介质 TEXT NOT NULL DEFAULT '大气',
  区域 TEXT NOT NULL DEFAULT '',
  说明 TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS 观测报文 (
  报文编号 TEXT PRIMARY KEY,
  站点键 TEXT NOT NULL,
  指标键 TEXT NOT NULL,
  读数 REAL NOT NULL,
  观测时 TEXT NOT NULL,
  处理时 TEXT NOT NULL,
  命运 TEXT NOT NULL DEFAULT '已装载',
  批次编号 TEXT NOT NULL DEFAULT '',
  分流 TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS 入栏缓冲 (
  报文编号 TEXT PRIMARY KEY,
  站点键 TEXT NOT NULL,
  指标键 TEXT NOT NULL,
  读数 REAL NOT NULL,
  观测时 TEXT NOT NULL,
  栏号 TEXT NOT NULL,
  命运 TEXT NOT NULL DEFAULT '在栏',
  入栏时 TEXT NOT NULL,
  门槛指纹 TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS 站点汇总账 (
  汇总编号 TEXT PRIMARY KEY,
  栏号 TEXT NOT NULL,
  站点键 TEXT NOT NULL,
  指标键 TEXT NOT NULL,
  报文数 INTEGER NOT NULL,
  均值 REAL NOT NULL,
  物化时 TEXT NOT NULL,
  命运 TEXT NOT NULL DEFAULT '已汇总',
  门槛指纹 TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS 影子归档 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  报文编号 TEXT NOT NULL,
  站点键 TEXT NOT NULL,
  指标键 TEXT NOT NULL,
  读数 REAL NOT NULL,
  观测时 TEXT NOT NULL,
  草稿命运 TEXT NOT NULL,
  原因 TEXT NOT NULL,
  门槛指纹 TEXT NOT NULL DEFAULT '',
  只读 INTEGER NOT NULL DEFAULT 1,
  归档时 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 坏点匣 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  报文编号 TEXT NOT NULL,
  站点键 TEXT NOT NULL,
  原因 TEXT NOT NULL,
  读数 REAL NOT NULL,
  观测时 TEXT NOT NULL,
  入匣时 TEXT NOT NULL,
  分流 TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS 栏贯验 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  时刻 TEXT NOT NULL,
  在栏笔数 INTEGER NOT NULL,
  汇总报文数 INTEGER NOT NULL,
  坏点笔数 INTEGER NOT NULL,
  是否对齐 INTEGER NOT NULL,
  说明 TEXT NOT NULL,
  影子笔数 INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS 装载批次 (
  编号 TEXT PRIMARY KEY,
  时刻 TEXT NOT NULL,
  入流 INTEGER NOT NULL DEFAULT 0,
  入栏 INTEGER NOT NULL DEFAULT 0,
  坏点 INTEGER NOT NULL DEFAULT 0,
  报告 TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS 结栏批次 (
  编号 TEXT PRIMARY KEY,
  栏号 TEXT NOT NULL,
  时刻 TEXT NOT NULL,
  汇总数 INTEGER NOT NULL DEFAULT 0,
  报告 TEXT NOT NULL DEFAULT '{}'
);
"""

# 旧库补列：CREATE TABLE IF NOT EXISTS 不会给既有表增列。
补列 = [
    ("观测报文", "分流", "TEXT NOT NULL DEFAULT ''"),
    ("入栏缓冲", "门槛指纹", "TEXT NOT NULL DEFAULT ''"),
    ("站点汇总账", "门槛指纹", "TEXT NOT NULL DEFAULT ''"),
    ("坏点匣", "分流", "TEXT NOT NULL DEFAULT ''"),
    ("栏贯验", "影子笔数", "INTEGER NOT NULL DEFAULT 0"),
]

默认栏规 = {
    "当前栏号": "B-demo",
    "PM25上限": "75",
    "PM25下限": "0",
    "标定偏移上限": "5",
    "栏策略": "分指标质控门槛，门槛账册与入栏同票",
    "账册版本": "1",
    "门槛:PM25:下限": "0",
    "门槛:PM25:上限": "75",
    "门槛:浊度:下限": "0",
    "门槛:浊度:上限": "5",
}


def 此刻() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _补齐列(conn) -> None:
    for 表, 列, 定义 in 补列:
        已有 = {r["name"] for r in conn.execute(f"PRAGMA table_info({表})").fetchall()}
        if 列 not in 已有:
            conn.execute(f"ALTER TABLE {表} ADD COLUMN {列} {定义}")


def _首账(conn) -> None:
    """门槛账册首条：按指标钉下限/上限与指纹。"""
    from app.services import 校验

    规 = {r["键"]: r["值"] for r in conn.execute("SELECT 键,值 FROM 栏规").fetchall()}
    表 = 校验.读门槛表(规)
    for 指标, (lo, hi) in sorted(表.items()):
        conn.execute(
            """INSERT INTO 门槛账册(指标键,下限,上限,指纹,账册版本,时刻)
               VALUES (?,?,?,?,?,?)""",
            (指标, str(lo), str(hi), 校验.指标指纹(规, 指标), 1, 此刻()),
        )


def 初始化库() -> None:
    conn = 连接()
    conn.executescript(建表)
    _补齐列(conn)
    if conn.execute("SELECT COUNT(*) AS c FROM 栏规").fetchone()["c"] == 0:
        for k, v in 默认栏规.items():
            conn.execute("INSERT INTO 栏规(键,值) VALUES (?,?)", (k, v))
    if conn.execute("SELECT COUNT(*) AS c FROM 站点源").fetchone()["c"] == 0:
        for row in [
            ("站-河东", "河东大气站", "大气", "城区", "示范站"),
            ("站-湖西", "湖西水质站", "水质", "湖区", "示范站"),
            ("站-北岭", "北岭大气站", "大气", "近郊", "示范站"),
            ("站-江口", "江口大气站", "大气", "河口", "示范站"),
            ("站-林场", "林场微站", "大气", "林区", "示范站"),
        ]:
            conn.execute(
                "INSERT INTO 站点源(源键,名称,介质,区域,说明) VALUES (?,?,?,?,?)",
                row,
            )
    if conn.execute("SELECT COUNT(*) AS c FROM 门槛账册").fetchone()["c"] == 0:
        _首账(conn)
    conn.commit()
    conn.close()
