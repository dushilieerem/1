"""SQLite 因子库加载器测试。"""

from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd

from app.models.data import Panel
from app.models.factor_backtest import FactorBacktestSpec
from app.services.catalog.query import CatalogQuery
from app.services.factor.loader import load_factor_from_spec
from app.services.factor.sqlite_loader import SQLiteFactorLoader, SQLiteFactorRepository


def _make_factor_database(tmp_path):
    db_path = tmp_path / "factor_library.db"
    tool_path = tmp_path / "tool.py"
    tool_path.write_text(
        "import numpy as np\n"
        "import pandas as pd\n"
        "EPSILON = 1e-12\n"
        "def vwap(data):\n"
        "    return data.close\n"
        "_vwap = vwap\n"
        "def sma(x, window, m=1.0):\n"
        "    return x.rolling(int(window)).mean()\n"
        "_sma = sma\n",
        encoding="utf-8",
    )
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE factor_libraries (
                library_id INTEGER PRIMARY KEY AUTOINCREMENT,
                library_name TEXT NOT NULL UNIQUE,
                description TEXT
            );
            CREATE TABLE categories (
                category_id TEXT PRIMARY KEY,
                category_name TEXT NOT NULL UNIQUE,
                description TEXT
            );
            CREATE TABLE factors (
                sv_id TEXT PRIMARY KEY,
                library_id INTEGER NOT NULL,
                factor_name TEXT NOT NULL,
                factor_name_en TEXT NOT NULL,
                factor_code TEXT NOT NULL,
                category_id TEXT NOT NULL,
                description TEXT,
                FOREIGN KEY (library_id) REFERENCES factor_libraries(library_id),
                FOREIGN KEY (category_id) REFERENCES categories(category_id)
            );
            INSERT INTO factor_libraries(library_name, description)
            VALUES ('主因子库', '测试 SQLite 因子库');
            INSERT INTO categories(category_id, category_name)
            VALUES ('SV01', '动量因子');
            """
        )
        connection.execute(
            """
            INSERT INTO factors(
                sv_id, library_id, factor_name, factor_name_en, factor_code,
                category_id, description
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "SV01_0001",
                1,
                "测试动量",
                "Test Momentum",
                "def test_momentum(self, window: int = 2):\n"
                "    return tool._sma(self.close, window)",
                "SV01",
                "测试因子说明",
            ),
        )
        connection.execute(
            """
            INSERT INTO factors(
                sv_id, library_id, factor_name, factor_name_en, factor_code,
                category_id, description
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "SV01_0002",
                1,
                "静态化兼容",
                "Staticized Compatibility",
                "def staticized(self):\n"
                "    vwap = tool._vwap(self)\n"
                "    return tool.vwap.rolling(2).mean()",
                "SV01",
                "测试静态化兼容",
            ),
        )
    return db_path, tool_path


def _panel():
    dates = pd.bdate_range("2026-01-01", periods=3)
    close = pd.DataFrame(
        {"A": [1.0, 2.0, 3.0], "B": [3.0, 4.0, 5.0]},
        index=dates,
    )
    return Panel({"close": close})


def test_sqlite_repository_and_loader_use_stable_id_and_function_alias(tmp_path):
    db_path, tool_path = _make_factor_database(tmp_path)
    repository = SQLiteFactorRepository(db_path)

    record = repository.get_factor("test_momentum", library_name="主因子库")
    assert record.sv_id == "SV01_0001"
    assert record.factor_name == "测试动量"
    assert record.function_name == "test_momentum"

    loader = SQLiteFactorLoader(db_path, tool_path)
    by_id = loader.load_factor(factor_name="SV01_0001", library_name="主因子库")
    by_function = loader.load_factor(
        factor_name="test_momentum",
        library_name="主因子库",
    )
    staticized = loader.load_factor(
        factor_name="SV01_0002",
        library_name="主因子库",
    )
    expected = pd.DataFrame(
        {"A": [np.nan, 1.5, 2.5], "B": [np.nan, 3.5, 4.5]},
        index=_panel().close.index,
    )
    pd.testing.assert_frame_equal(by_id.compute(_panel()), expected)
    pd.testing.assert_frame_equal(by_function.compute(_panel()), expected)
    pd.testing.assert_frame_equal(
        staticized.compute(_panel()),
        _panel().close.rolling(2).mean(),
    )


def test_catalog_and_spec_default_to_sqlite_records(tmp_path, monkeypatch):
    db_path, tool_path = _make_factor_database(tmp_path)
    monkeypatch.setenv("SVQUANT_FACTOR_DB_PATH", str(db_path))
    monkeypatch.setenv("SVQUANT_FACTOR_TOOL_PATH", str(tool_path))

    catalog = CatalogQuery()
    assert catalog.list_factor_libraries()[0].factor_count == 2
    factor = catalog.list_factors("主因子库")[0]
    assert factor.name == "SV01_0001"
    assert factor.display_name == "测试动量"
    assert factor.category_name == "动量因子"
    assert not hasattr(factor, "category_id")

    resolved = load_factor_from_spec(
        spec=FactorBacktestSpec(
            factor_name="SV01_0001",
            library_names=("主因子库",),
        )
    )
    assert resolved.name == "SV01_0001"
