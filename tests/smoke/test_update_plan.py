"""Il delta non tocca brani, database o log, e verifica gli hash."""

import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.update_plan import (
    build_manifest,
    diff_manifests,
    is_protected_path,
    stage_delta_zip,
    verify_package_tree,
)


def test_protected_paths() -> None:
    assert is_protected_path("data/karaoke.db")
    assert is_protected_path("media/downloads/a.mp4")
    assert is_protected_path("logs/karaoke_manager.log")
    assert is_protected_path("github_update_token.txt")
    assert is_protected_path("../KaraokeManager.exe")
    assert not is_protected_path("_internal/python312.dll")
    assert not is_protected_path("KaraokeManager.exe")


def test_diff_lists_only_changed_program_files(tmp_path: Path) -> None:
    old_root = tmp_path / "old"
    new_root = tmp_path / "new"
    for root, payload in ((old_root, b"one"), (new_root, b"two")):
        (root / "_internal").mkdir(parents=True)
        (root / "data").mkdir()
        (root / "_internal" / "python312.dll").write_bytes(payload)
        (root / "data" / "karaoke.db").write_bytes(b"secret-db")
        (root / "KaraokeManager.exe").write_bytes(payload)
    old = build_manifest(old_root, "2.2.6")
    new = build_manifest(new_root, "2.2.7")
    assert all(not item["path"].startswith("data/") for item in old["files"])
    plan = diff_manifests(old, new)
    paths = {item["path"] for item in plan["files"]}
    assert paths == {"_internal/python312.dll", "KaraokeManager.exe"}
    assert plan["removed"] == []
    assert plan["from_version"] == "2.2.6"
    assert plan["to_version"] == "2.2.7"


def test_stage_rejects_protected_delete(tmp_path: Path) -> None:
    archive_path = tmp_path / "delta.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "plan.json",
            json.dumps({"files": [], "removed": ["data/karaoke.db"]}),
        )
    try:
        stage_delta_zip(archive_path, tmp_path / "stage")
    except ValueError as exc:
        assert "protetto" in str(exc)
        return
    raise AssertionError("doveva rifiutare la cancellazione del database")


def test_verify_rejects_python313_forwarder(tmp_path: Path) -> None:
    internal = tmp_path / "_internal"
    internal.mkdir()
    (internal / "python3.dll").write_bytes(b"forward python313.dll")
    errors = verify_package_tree(tmp_path)
    assert any("3.13" in item for item in errors)
    assert any("manca" in item for item in errors)


if __name__ == "__main__":
    test_protected_paths()
    print("ok")
