"""Piano di aggiornamento per file: cosa copiare, cosa non toccare."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

PROTECTED_TOP_LEVEL = frozenset({"data", "media", "logs"})
TOKEN_FILE = "github_update_token.txt"

REQUIRED_FILES = (
    "KaraokeManager.exe",
    "apply_update.ps1",
    "manifest.json",
    "_internal/python312.dll",
    "_internal/python3.dll",
    "_internal/PyQt6/QtCore.pyd",
    "_internal/PyQt6/Qt6/bin/Qt6Core.dll",
    "_internal/PyQt6/sip.cp312-win_amd64.pyd",
    "_internal/PyQt6/Qt6/plugins/platforms/qwindows.dll",
    "bin/ffmpeg.exe",
    "vlc/libvlc.dll",
    "mpv/mpv.exe",
    "mpv/vulkan-1.dll",
)


def normalize_rel(path: str) -> str:
    """Path relativo con slash, senza '.' iniziali."""
    return path.replace("\\", "/").lstrip("/")


def is_protected_path(path: str) -> bool:
    """True per brani, database, log e token: non vanno nell'aggiornamento."""
    rel = normalize_rel(path)
    if not rel or rel == TOKEN_FILE or ".." in rel.split("/"):
        return True
    top = rel.split("/", 1)[0]
    return top in PROTECTED_TOP_LEVEL


def sha256_file(path: Path) -> str:
    """Impronta SHA-256 esadecimale minuscola."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(root: Path, version: str) -> dict:
    """Elenco dei file di programma, senza dati utente."""
    files: list[dict] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if is_protected_path(rel):
            continue
        files.append({"path": rel, "sha256": sha256_file(path), "size": path.stat().st_size})
    return {"version": version, "files": files}


def diff_manifests(old: dict, new: dict) -> dict:
    """File nuovi o diversi, e file da cancellare. I path protetti non escono mai."""
    old_map = {
        item["path"]: item["sha256"]
        for item in old.get("files", [])
        if not is_protected_path(item["path"])
    }
    new_items = [item for item in new.get("files", []) if not is_protected_path(item["path"])]
    new_map = {item["path"]: item["sha256"] for item in new_items}
    changed = [item for item in new_items if old_map.get(item["path"]) != item["sha256"]]
    removed = [path for path in old_map if path not in new_map]
    return {
        "from_version": str(old.get("version") or ""),
        "to_version": str(new.get("version") or ""),
        "files": changed,
        "removed": removed,
    }


def verify_package_tree(root: Path) -> list[str]:
    """Errori che impediscono di pubblicare l'installer. Lista vuota se è sano."""
    errors: list[str] = []
    for rel in REQUIRED_FILES:
        if not (root / rel).is_file():
            errors.append(f"manca {rel}")
    ffmpeg = root / "bin" / "ffmpeg.exe"
    if ffmpeg.is_file() and ffmpeg.stat().st_size < 20 * 1024 * 1024:
        errors.append(f"ffmpeg è uno stub ({ffmpeg.stat().st_size} byte)")
    internal = root / "_internal"
    if internal.is_dir():
        leftovers = [path.name for path in internal.rglob("*cp313*")]
        if leftovers:
            errors.append("restano moduli Python 3.13: " + ", ".join(leftovers[:8]))
        python3 = internal / "python3.dll"
        if python3.is_file():
            blob = python3.read_bytes()
            if b"python313" in blob:
                errors.append("python3.dll inoltra ancora a Python 3.13")
            if b"python312" not in blob:
                errors.append("python3.dll non inoltra a Python 3.12")
    db = root / "data" / "karaoke.db"
    if db.is_file() and db.stat().st_size > 0:
        errors.append("il pacchetto contiene un database: non va distribuito")
    return errors


def stage_delta_zip(zip_path: Path, staging: Path) -> dict:
    """Estrae il delta e rifiuta path protetti o hash diversi dal piano."""
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/"):
                raise ValueError(f"Voce zip non ammessa: {name}")
        archive.extractall(staging)
    plan_path = staging / "plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    payload = staging / "payload"
    for item in plan.get("files") or []:
        rel = normalize_rel(str(item.get("path") or ""))
        if is_protected_path(rel):
            raise ValueError(f"Il delta tocca un path protetto: {rel}")
        file_path = payload / rel
        if not file_path.is_file():
            raise ValueError(f"File delta mancante: {rel}")
        digest = sha256_file(file_path)
        if digest != str(item.get("sha256") or "").lower():
            raise ValueError(f"Hash non valido: {rel}")
    for rel in plan.get("removed") or []:
        if is_protected_path(str(rel)):
            raise ValueError(f"Il delta cancellerebbe un path protetto: {rel}")
    return plan
