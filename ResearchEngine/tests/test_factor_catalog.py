"""因子源码与索引同步测试。"""

from __future__ import annotations

import uuid

import yaml

from app.repositories.catalogs.factor_catalog import check_catalog, sync_catalog


def test_repository_factor_catalog_is_synchronized():
    assert check_catalog() == []


def test_sync_and_check_catalog_follow_factor_source(tmp_path):
    factor_dir = tmp_path / "libraries"
    factor_dir.mkdir()
    module_name = f"catalog_test_{uuid.uuid4().hex}"
    module_path = factor_dir / f"{module_name}.py"
    index_path = factor_dir / "index.yaml"
    overview_path = tmp_path / "因子库总览.md"
    overview_path.write_text("研究员手工维护的总览文档。\n", encoding="utf-8")

    module_path.write_text(
        "from app.quantcore import FactorLibrary\n\n"
        f"class CatalogTestLibrary(FactorLibrary):\n"
        "    author = 'test'\n\n"
        "    def first_factor(self, window: int = 5):\n"
        "        \"\"\"第一个测试因子。\"\"\"\n"
        "        return self.close.rolling(window).mean()\n",
        encoding="utf-8",
    )
    index_path.write_text(
        "version: 1\n"
        "libraries:\n"
        f"  {module_name}:\n"
        f"    file: {module_name}.py\n"
        "    tags: [test]\n",
        encoding="utf-8",
    )

    catalog = sync_catalog(
        factor_dir=factor_dir,
        index_path=index_path,
    )
    assert catalog["total_factors"] == 1
    assert check_catalog(
        factor_dir=factor_dir,
        index_path=index_path,
    ) == []

    indexed = yaml.safe_load(index_path.read_text(encoding="utf-8"))
    library = indexed["libraries"][module_name]
    assert library["factor_count"] == 1
    assert library["tags"] == ["test"]
    assert library["factors"][0]["name"] == "first_factor"
    assert overview_path.read_text(encoding="utf-8") == "研究员手工维护的总览文档。\n"

    # 源码发生变化但未运行 sync 时，校验必须阻止提交。
    module_path.write_text(
        module_path.read_text(encoding="utf-8")
        + "\n    def second_factor(self):\n"
        + "        \"\"\"第二个测试因子。\"\"\"\n"
        + "        return self.close\n",
        encoding="utf-8",
    )
    errors = check_catalog(
        factor_dir=factor_dir,
        index_path=index_path,
    )
    assert len(errors) == 1
    assert "索引未同步" in errors[0]

    catalog = sync_catalog(
        factor_dir=factor_dir,
        index_path=index_path,
    )
    assert catalog["total_factors"] == 2
    assert check_catalog(
        factor_dir=factor_dir,
        index_path=index_path,
    ) == []
    assert overview_path.read_text(encoding="utf-8") == "研究员手工维护的总览文档。\n"
