#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""marketdata 发布核对与回滚（P1-O07）。

用法：
  python scripts/data_release.py check --data-dir /path/marketdata [--checksum]
  python scripts/data_release.py snapshot --data-dir /path/marketdata --out /path/release
  python scripts/data_release.py rollback --data-dir /path/marketdata --from /path/release [--apply]

rollback 默认 dry-run；只有显式 --apply 才会复制文件，并在数据目录内留备份。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def _load_manifest(data_dir: Path) -> dict[str, Any]:
    path = data_dir / "data_manifest.yaml"
    if not path.exists():
        raise FileNotFoundError(f"缺少 data_manifest.yaml：{path}")
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("需要 PyYAML：pip install pyyaml") from exc
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("data_manifest.yaml 结构非法")
    return raw


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def check_release(data_dir: Path, *, checksum: bool = False) -> dict[str, Any]:
    manifest = _load_manifest(data_dir)
    assets = manifest.get("assets") or []
    errors: list[str] = []
    checked: list[dict[str, Any]] = []
    for asset in assets:
        rel = str(asset.get("path") or "")
        if not rel:
            errors.append("资产缺少 path")
            continue
        path = data_dir / rel
        item: dict[str, Any] = {"path": rel, "exists": path.exists()}
        if not path.exists():
            errors.append(f"缺少文件：{rel}")
        else:
            item["size"] = path.stat().st_size
            if item["size"] <= 0:
                errors.append(f"空文件：{rel}")
            expected_sha = str(asset.get("sha256") or "")
            if checksum and expected_sha:
                actual = _sha256(path)
                item["sha256_ok"] = actual == expected_sha
                if actual != expected_sha:
                    errors.append(f"sha256 不一致：{rel}")
        checked.append(item)
    return {
        "ok": not errors,
        "data_version": manifest.get("data_version"),
        "generated_at": manifest.get("generated_at"),
        "asset_count": len(assets),
        "errors": errors,
        "assets": checked,
    }


def snapshot(data_dir: Path, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = data_dir / "data_manifest.yaml"
    if not manifest.exists():
        raise FileNotFoundError(f"缺少 {manifest}")
    shutil.copy2(manifest, out_dir / "data_manifest.yaml")
    for name in ("quality_report.json",):
        src = data_dir / name
        if src.exists():
            shutil.copy2(src, out_dir / name)
    info = {
        "snapshot_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(data_dir),
        "manifest": str(out_dir / "data_manifest.yaml"),
    }
    (out_dir / "RELEASE_INFO.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"ok": True, "out": str(out_dir), "info": info}


def rollback(data_dir: Path, release_dir: Path, *, apply: bool = False) -> dict[str, Any]:
    src_manifest = release_dir / "data_manifest.yaml"
    if not src_manifest.exists():
        raise FileNotFoundError(f"发布目录缺少 data_manifest.yaml：{src_manifest}")
    check = check_release(release_dir)
    if not check["ok"]:
        raise ValueError("待回滚的发布目录不完整：" + "; ".join(check["errors"][:5]))

    plan = {
        "data_dir": str(data_dir),
        "release_dir": str(release_dir),
        "data_version": check["data_version"],
        "apply": bool(apply),
    }
    if not apply:
        return {"ok": True, "dry_run": True, "plan": plan}

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = data_dir / f".rollback_backup-{stamp}"
    backup.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest(release_dir)
    restored: list[str] = []
    for asset in manifest.get("assets") or []:
        rel = str(asset.get("path") or "")
        if not rel:
            continue
        src = release_dir / rel
        dst = data_dir / rel
        if dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, backup / rel.replace("/", "__"))
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        restored.append(rel)
    shutil.copy2(src_manifest, data_dir / "data_manifest.yaml")
    return {
        "ok": True,
        "dry_run": False,
        "backup": str(backup),
        "restored": restored,
        "data_version": check["data_version"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="marketdata 发布核对与回滚")
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="核对发布清单")
    p_check.add_argument("--data-dir", required=True)
    p_check.add_argument("--checksum", action="store_true")

    p_snap = sub.add_parser("snapshot", help="备份清单/质量报告")
    p_snap.add_argument("--data-dir", required=True)
    p_snap.add_argument("--out", required=True)

    p_rb = sub.add_parser("rollback", help="回滚到指定发布目录（默认 dry-run）")
    p_rb.add_argument("--data-dir", required=True)
    p_rb.add_argument("--from", dest="release_dir", required=True)
    p_rb.add_argument("--apply", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            out = check_release(Path(args.data_dir), checksum=args.checksum)
        elif args.command == "snapshot":
            out = snapshot(Path(args.data_dir), Path(args.out))
        else:
            out = rollback(
                Path(args.data_dir), Path(args.release_dir), apply=args.apply
            )
    except Exception as exc:  # noqa: BLE001
        print(f"[data-release] 失败：{exc}", file=sys.stderr)
        return 2
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
