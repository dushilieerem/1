from pathlib import Path

import pytest

from data_ingestion.ifind.common import file_ops


def test_replace_with_retry_recovers_from_transient_permission_error(tmp_path, monkeypatch):
    source = tmp_path / "market_data.csv.tmp"
    target = tmp_path / "market_data.csv"
    source.write_text("new", encoding="utf-8")
    target.write_text("old", encoding="utf-8")

    attempts = 0
    original_replace = Path.replace

    def flaky_replace(self: Path, destination: Path) -> Path:
        nonlocal attempts
        if self == source and attempts < 2:
            attempts += 1
            raise PermissionError(5, "Access is denied")
        return original_replace(self, destination)

    monkeypatch.setattr(Path, "replace", flaky_replace)
    monkeypatch.setattr(file_ops, "REPLACE_RETRY_DELAY_SECONDS", 0.0)

    file_ops.replace_with_retry(source, target)

    assert attempts == 2
    assert target.read_text(encoding="utf-8") == "new"
    assert not source.exists()


def test_replace_with_retry_preserves_source_after_persistent_permission_error(
    tmp_path, monkeypatch
):
    source = tmp_path / "market_data.csv.tmp"
    target = tmp_path / "market_data.csv"
    source.write_text("new", encoding="utf-8")
    target.write_text("old", encoding="utf-8")

    def locked_replace(*args):
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(Path, "replace", locked_replace)
    monkeypatch.setattr(file_ops, "REPLACE_RETRIES", 2)
    monkeypatch.setattr(file_ops, "REPLACE_RETRY_DELAY_SECONDS", 0.0)

    with pytest.raises(PermissionError):
        file_ops.replace_with_retry(source, target)

    assert source.read_text(encoding="utf-8") == "new"
    assert target.read_text(encoding="utf-8") == "old"
