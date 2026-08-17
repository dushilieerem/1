from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from data_ingestion.shared.panel_quality import inspect_panels  # noqa: E402


def test_inspect_panels_reports_calendar_mismatch_and_missing_manifest(tmp_path):
    panels = tmp_path / "panels"
    panels.mkdir()
    index = pd.to_datetime(["2026-07-22", "2026-07-23"])
    pd.DataFrame({"000001": [1.0, 2.0]}, index=index).to_parquet(panels / "close.parquet")
    pd.DataFrame({"000001": [1.0]}, index=index[:1]).to_parquet(panels / "volume.parquet")

    report = inspect_panels(panels, metadata_dir=tmp_path / "metadata")

    assert report["field_count"] == 2
    assert report["manifest_files"] == []
    assert report["issue_count"] == 1
    assert report["issues"] == [{"field": "volume", "type": "calendar_mismatch"}]
