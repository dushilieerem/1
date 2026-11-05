"""Read published company data metadata through SVQuant's existing view resolver."""
import hashlib
import json
import re
from services.data.platform_view import materialized_view_root

def _contract_revision(root) -> str:
    """The data contract's revision (not the manifest schema version)."""
    path = root / "data_contract.yaml"
    if not path.is_file():
        return ""
    match = re.search(r"^revision:\s*'?([^'\n]+)'?\s*$", path.read_text(encoding="utf-8"), re.M)
    return match.group(1).strip() if match else ""


def published_view():
    root = materialized_view_root()
    if root is None:
        raise ValueError("尚未配置公司发布数据 view")
    root = root.resolve(strict=True)
    raw = (root / "manifest.json").read_bytes()
    manifest = json.loads(raw)
    view_id = manifest.get("view_id")
    if not isinstance(view_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", view_id) or view_id == "current":
        raise ValueError("数据发布缺少具体 view_id，不能使用浮动版本进行研究")
    entries = manifest.get("datasets")
    if not isinstance(entries, dict) or not entries:
        raise ValueError("数据发布缺少数据集")
    datasets = {}
    for name, entry in entries.items():
        if not isinstance(entry, dict):
            raise ValueError("数据集契约无效")
        digest = entry.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("数据集缺少有效内容摘要")
        datasets[name] = {k: entry.get(k) for k in (
            "release", "sha256", "contract_version", "rows", "date_min", "date_max", "pit_rule")}
    return {
        "view_id": view_id, "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "contract_version": manifest.get("contract_version"),
        "contract_revision": _contract_revision(root),
        "generated_at": manifest.get("generated_at"), "datasets": datasets,
        "research_ready": False,
        "integration_status": "metadata_only",
        "note": "公司发布目录已接入；现有实验计算尚未切换到此数据源。",
    }
