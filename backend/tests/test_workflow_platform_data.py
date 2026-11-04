import json
from pathlib import Path
from unittest.mock import patch
import pytest
from services.workflow_workspace.platform_data import published_view

def publish(root, view_id="release-1", digest="a"*64):
    root.mkdir(exist_ok=True)
    (root/"manifest.json").write_text(json.dumps({"view_id":view_id,"datasets":{
        "daily_bars":{"sha256":digest,"release":"source-1","source":"/private/source","path":"/internal","pit_rule":"date <= as_of"}}}))
    return root

def test_metadata_keeps_provenance_without_disclosing_paths(tmp_path):
    with patch("services.workflow_workspace.platform_data.materialized_view_root",return_value=publish(tmp_path)):
        data=published_view()
    assert data["view_id"]=="release-1"
    assert len(data["manifest_sha256"])==64
    assert "source" not in data["datasets"]["daily_bars"]
    assert data["datasets"]["daily_bars"]["pit_rule"]=="date <= as_of"
    assert data["research_ready"] is False

@pytest.mark.parametrize("view_id,digest",[("current","a"*64),("release-1","bad")])
def test_incomplete_version_rejected(tmp_path,view_id,digest):
    with patch("services.workflow_workspace.platform_data.materialized_view_root",return_value=publish(tmp_path,view_id,digest)):
        with pytest.raises(ValueError): published_view()

def test_current_switch_does_not_change_existing_snapshot(tmp_path):
    a=publish(tmp_path/"a");b=publish(tmp_path/"b","release-2","b"*64)
    current=tmp_path/"current";current.symlink_to(a,target_is_directory=True)
    with patch("services.workflow_workspace.platform_data.materialized_view_root",return_value=current):
        first=published_view()
        current.unlink();current.symlink_to(b,target_is_directory=True)
        second=published_view()
    assert first["view_id"]=="release-1"
    assert second["view_id"]=="release-2"
    assert first["manifest_sha256"]!=second["manifest_sha256"]

def test_no_configuration_does_not_fall_back_to_synthetic():
    with patch("services.workflow_workspace.platform_data.materialized_view_root",return_value=None):
        with pytest.raises(ValueError): published_view()
