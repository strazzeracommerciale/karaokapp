"""Manifest, delta e controlli del pacchetto Windows prima della pubblicazione.

Uso:
  python build/update_package.py manifest --dist dist/KaraokeManager
  python build/update_package.py verify --dist dist/KaraokeManager
  python build/update_package.py fetch-previous --out dist/previous-manifest.json
  python build/update_package.py delta --previous dist/previous-manifest.json --dist dist/KaraokeManager --out dist/KaraokeManager-delta-from-2.2.6.zip
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.update_plan import (  # noqa: E402
    build_manifest,
    diff_manifests,
    is_protected_path,
    verify_package_tree,
)

REPO = "strazzeracommerciale/karaokapp"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def cmd_manifest(dist: Path) -> None:
    import config

    manifest = build_manifest(dist, config.APP_VERSION)
    _write_json(dist / "manifest.json", manifest)
    _write_json(dist.parent / "manifest.json", manifest)
    print(f"Manifest {manifest['version']}: {len(manifest['files'])} file")


def cmd_verify(dist: Path) -> None:
    errors = verify_package_tree(dist)
    if errors:
        print("Pacchetto non pubblicabile:", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        raise SystemExit(1)
    print("Verifica pacchetto ok")


def cmd_fetch_previous(out: Path) -> None:
    url = f"https://api.github.com/repos/{REPO}/releases/latest"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "KaraokeManager-build",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            release = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - build continua senza delta
        print(f"Nessuna release precedente usabile: {exc}")
        return
    assets = release.get("assets") or []
    asset = next((item for item in assets if item.get("name") == "manifest.json"), None)
    if not asset:
        print(f"Release {release.get('tag_name')} senza manifest.json: delta non creato")
        return
    download = asset.get("browser_download_url")
    if not download:
        print("manifest.json senza URL")
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(download, out)  # noqa: S310 - URL della release GitHub
    print(f"Manifest precedente salvato: {out}")


def cmd_delta(previous: Path, dist: Path, out: Path) -> None:
    import config

    old = json.loads(previous.read_text(encoding="utf-8"))
    new = build_manifest(dist, config.APP_VERSION)
    plan = diff_manifests(old, new)
    if not plan["files"] and not plan["removed"]:
        print("Nessun file cambiato: delta non creato")
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("plan.json", json.dumps(plan, indent=2))
        archive.writestr("manifest.json", json.dumps(new, indent=2))
        for item in plan["files"]:
            rel = item["path"]
            if is_protected_path(rel):
                raise SystemExit(f"Il delta include un path protetto: {rel}")
            source = dist / rel
            data = source.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if digest != item["sha256"]:
                raise SystemExit(f"Hash incoerente per {rel}")
            archive.writestr(f"payload/{rel}", data)
    changed = len(plan["files"])
    removed = len(plan["removed"])
    size_mb = out.stat().st_size / (1024 * 1024)
    print(
        f"Delta {plan['from_version']} -> {plan['to_version']}: "
        f"{changed} file, {removed} rimossi, {size_mb:.1f} MB -> {out.name}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    manifest = sub.add_parser("manifest")
    manifest.add_argument("--dist", type=Path, required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--dist", type=Path, required=True)
    fetch = sub.add_parser("fetch-previous")
    fetch.add_argument("--out", type=Path, required=True)
    delta = sub.add_parser("delta")
    delta.add_argument("--previous", type=Path, required=True)
    delta.add_argument("--dist", type=Path, required=True)
    delta.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.cmd == "manifest":
        cmd_manifest(args.dist)
    elif args.cmd == "verify":
        cmd_verify(args.dist)
    elif args.cmd == "fetch-previous":
        cmd_fetch_previous(args.out)
    elif args.cmd == "delta":
        cmd_delta(args.previous, args.dist, args.out)


if __name__ == "__main__":
    main()
