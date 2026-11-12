# -*- coding: utf-8 -*-
"""把文档平台的页文本裁剪成机构端可用的“年报章节页”缓存。

输入（只读）：数据业务的 pagetext release
  <release>/page_text/year=YYYY/part.parquet
  <release>/section_index/report_period=YYYY-MM-DD/part.parquet
输出：
  <out> 单个 parquet，按 symbol 排序，字段
  (symbol, doc_id, report_period, section_name, page_no, text, source_sha256, pdf_url, available_time)

规则：
- 只用年报（doc_type=annual）；每只股票取 as_of 前最近一期年报；
- 六节：公司治理/股份质押冻结/承诺事项/关联交易/对外担保/董监高变动；
- 同一页命中多节时按节各存一份，换取按节取数的简单性；
- PIT：available_time <= as_of。

用法：
  python scripts/ops/build_doc_section_cache.py --limit 200      # 试点
  python scripts/ops/build_doc_section_cache.py                  # 全量
"""
from __future__ import annotations

import argparse
import glob
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

DEFAULT_RELEASE = "/data/dev01/project/svquant-data/documents/doc_release/pagetext-20261112"
SECTIONS = ("公司治理", "股份质押冻结", "承诺事项", "关联交易", "对外担保", "董监高变动")
SCHEMA = pa.schema(
    [
        ("symbol", pa.string()),
        ("doc_id", pa.string()),
        ("report_period", pa.string()),
        ("section_name", pa.string()),
        ("page_no", pa.string()),
        ("text", pa.string()),
        ("source_sha256", pa.string()),
        ("pdf_url", pa.string()),
        ("available_time", pa.string()),
    ]
)


def _section_pages(release: Path, as_of: str) -> tuple[dict[str, str], dict[str, dict[str, set[str]]]]:
    """返回 (doc_id -> symbol, doc_id -> {section: {page_no}})。

    只保留每只股票 as_of 前最近一期年报的六节页。
    """
    latest: dict[str, tuple[str, str]] = {}
    doc_symbol: dict[str, str] = {}
    raw: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for path in sorted(glob.glob(str(release / "section_index" / "report_period=*" / "part.parquet"))):
        table = pq.ParquetFile(path).read(
            columns=["doc_id", "symbol", "report_period", "doc_type", "section_name", "page_start", "page_end"],
        )
        if table.num_rows == 0:
            continue
        d = table.to_pydict()
        for doc_id, symbol, period, doc_type, section, start, end in zip(
            d["doc_id"], d["symbol"], d["report_period"], d["doc_type"], d["section_name"], d["page_start"], d["page_end"]
        ):
            if str(doc_type) != "annual" or section not in SECTIONS:
                continue
            period, symbol, doc_id = str(period)[:10], str(symbol), str(doc_id)
            if period > as_of:
                continue
            if symbol not in latest or period > latest[symbol][0]:
                latest[symbol] = (period, doc_id)
            doc_symbol[doc_id] = symbol
            raw[doc_id][section].update(str(p) for p in range(int(start), int(end) + 1))
    keep = {
        doc_id: {sec: pages for sec, pages in sections.items() if pages}
        for doc_id, sections in raw.items()
        if doc_id in doc_symbol and latest.get(doc_symbol[doc_id], ("", ""))[1] == doc_id
    }
    return doc_symbol, keep


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", default=DEFAULT_RELEASE)
    parser.add_argument("--out", default="")
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 只股票（试点）")
    args = parser.parse_args()

    release = Path(args.release)
    if not (release / "_SUCCESS").exists():
        print(f"release 未完成：{release}/_SUCCESS 不存在", file=sys.stderr)
        return 2
    out = Path(args.out or f"backend/output/doc_sections_{release.name}.parquet")
    t0 = time.time()
    doc_symbol, keep = _section_pages(release, args.as_of)
    if args.limit:
        wanted = set(sorted(set(doc_symbol.values()))[: args.limit])
        keep = {d: v for d, v in keep.items() if doc_symbol.get(d) in wanted}
    print(f"docs={len(keep)} elapsed={round(time.time()-t0,1)}s", flush=True)
    if not keep:
        print("没有匹配的年报章节", file=sys.stderr)
        return 1

    writer = None
    written = 0
    try:
        for path in sorted(glob.glob(str(release / "page_text" / "year=*" / "part.parquet"))):
            parquet = pq.ParquetFile(path)
            for batch in parquet.iter_batches(
                batch_size=200_000,
                columns=["doc_id", "symbol", "report_period", "page_no", "text", "source_sha256", "pdf_url", "available_time"],
            ):
                d = pa.Table.from_batches([batch]).to_pydict()
                rows: dict[str, list] = {k: [] for k in SCHEMA.names}
                for doc_id, symbol, period, page_no, text, sha, url, avail in zip(
                    d["doc_id"], d["symbol"], d["report_period"], d["page_no"], d["text"],
                    d["source_sha256"], d["pdf_url"], d["available_time"],
                ):
                    sections = keep.get(str(doc_id))
                    if not sections:
                        continue
                    avail_s = str(avail)[:10]
                    if avail_s > args.as_of:
                        continue
                    page_s = str(page_no)
                    for section, pages in sections.items():
                        if page_s not in pages:
                            continue
                        rows["symbol"].append(str(symbol))
                        rows["doc_id"].append(str(doc_id))
                        rows["report_period"].append(str(period)[:10])
                        rows["section_name"].append(section)
                        rows["page_no"].append(page_s)
                        rows["text"].append(text)
                        rows["source_sha256"].append(sha)
                        rows["pdf_url"].append(url)
                        rows["available_time"].append(avail_s)
                if not rows["symbol"]:
                    continue
                table = pa.Table.from_pydict(rows, schema=SCHEMA)
                if writer is None:
                    out.parent.mkdir(parents=True, exist_ok=True)
                    writer = pq.ParquetWriter(out, SCHEMA, compression="zstd")
                writer.write_table(table)
                written += table.num_rows
                print(f"  +{table.num_rows} rows (total {written}) {round(time.time()-t0,1)}s", flush=True)
    finally:
        if writer is not None:
            writer.close()
    if written == 0:
        print("没有匹配的页文本", file=sys.stderr)
        return 1
    table = pq.read_table(out).sort_by(
        [("symbol", "ascending"), ("section_name", "ascending"), ("page_no", "ascending")]
    )
    pq.write_table(table, out, compression="zstd", row_group_size=20_000)
    print(f"done rows={table.num_rows} out={out} elapsed={round(time.time()-t0,1)}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
