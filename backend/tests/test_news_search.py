# -*- coding: utf-8 -*-
"""资讯搜索的已知漏搜样本及组合筛选回归，不连接线上数据库。

执行真实 list_news 查询，用 SQLite 内存样本验证结果；只适配占位符、
ILIKE 和 JSONB 数组函数的方言差异，不替换业务 WHERE 条件。
PostgreSQL 的执行计划和性能仍需部署环境验证。
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.news import news_store as store  # noqa: E402


class SampleDatabase:
    def __init__(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.create_function(
            "json_contains", 2,
            lambda value, wanted: all(x in json.loads(value) for x in json.loads(wanted)),
        )
        self.db.execute("""CREATE TABLE news_items (
            id INTEGER, title TEXT, summary TEXT, body TEXT, published_at TEXT,
            source TEXT, category TEXT, url TEXT, symbols TEXT, themes TEXT,
            industries TEXT, is_flash INTEGER, is_featured INTEGER
        )""")
        self.add(1, "短期融资券兑付完成的公告", symbols=["601162.SH"], category="announce", source="cninfo")
        self.add(2, "临时股东会会议资料", symbols=["601162.SH"], category="announce", source="cninfo")
        self.add(3, "天风证券：子公司增资", symbols=["601162.SH"], body="证券代码601162.SH", themes=["金融"])
        self.add(4, "临床试验取得进展", themes=["CRO"], industries=["医药生物"])
        self.add(5, "算力芯片新进展", themes=["算力"])
        self.add(6, "医疗算力平台", themes=["CRO", "算力"], industries=["医药生物"])
        self.add(7, "100%成长_方案\\样例", symbols=["300345.SZ"], body="带'引号的文本")
        self.add(8, "另一篇公告", symbols=["300345.SZ"], category="announce", source="cninfo")

    def add(self, ident, title, *, symbols=(), themes=(), industries=(), body="", category="flash", source="cls"):
        self.db.execute(
            "INSERT INTO news_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ident, title, "", body, "2026-10-19T10:00:00+08:00", source, category,
             "", json.dumps(list(symbols)), json.dumps(list(themes), ensure_ascii=False),
             json.dumps(list(industries), ensure_ascii=False), int(category == "flash"), 0),
        )

    def execute(self, sql, params):
        sql = sql.replace("%s", "?").replace("ILIKE", "LIKE")
        sql = re.sub(r"jsonb_array_elements_text\((\w+)\) AS search_tag\(value\)",
                     r"json_each(\1) AS search_tag", sql)
        sql = re.sub(r"(\w+) @> \?::jsonb", r"json_contains(\1, ?)", sql)
        return self.db.execute(sql, params)


class NewsSearchTests(unittest.TestCase):
    def setUp(self):
        self.samples = SampleDatabase()

        @contextmanager
        def connection():
            yield self.samples

        self.db_patch = patch.object(store, "get_conn", connection)
        self.caps_patch = patch.object(store, "ensure_news_within_caps", return_value=None)
        self.db_patch.start()
        self.caps_patch.start()
        self.addCleanup(self.db_patch.stop)
        self.addCleanup(self.caps_patch.stop)
        self.addCleanup(self.samples.db.close)

    def ids(self, **params):
        return [item["id"] for item in store.list_news(**params)["items"]]

    def test_full_stock_code_does_not_lose_announcements_without_code_in_body(self):
        for query in ("601162", "601162.SH", "601162.sh"):
            with self.subTest(query=query):
                self.assertEqual(self.ids(q=query), [3, 2, 1])

    def test_other_exchange_and_metadata_only_stock_code(self):
        self.assertEqual(self.ids(q="300345.SZ"), [8, 7])

    def test_theme_and_industry_search_include_metadata_only_items(self):
        self.assertEqual(self.ids(q="CRO"), [6, 4])
        self.assertEqual(self.ids(q="医药生物"), [6, 4])

    def test_source_category_and_tags_still_intersect_with_query(self):
        self.assertEqual(self.ids(q="601162.SH", source="cninfo", category="announce"), [2, 1])
        self.assertEqual(self.ids(q="CRO", theme=["算力"]), [6])

    def test_multiple_themes_keep_union_and_other_dimensions_intersect(self):
        self.assertEqual(self.ids(theme=["CRO", "算力"]), [6, 5, 4])
        self.assertEqual(self.ids(theme=["CRO", "算力"], industry=["医药生物"]), [6, 4])

    def test_total_and_pagination_share_the_same_search_scope(self):
        result = store.list_news(q="601162.SH", limit=1, offset=1)
        self.assertEqual(result["total"], 3)
        self.assertEqual([item["id"] for item in result["items"]], [2])

    def test_literal_percent_underscore_backslash_and_quote_are_not_wildcards(self):
        for query in ("%", "_", "\\", "'"):
            with self.subTest(query=query):
                self.assertEqual(self.ids(q=query), [7])
        self.assertEqual(self.ids(q='"'), [])  # 不匹配 JSON 序列化产生的引号。

    def test_empty_and_unmatched_queries(self):
        self.assertEqual(len(self.ids(q="  ")), 8)
        self.assertEqual(self.ids(q="__no_news__"), [])


if __name__ == "__main__":
    unittest.main()
