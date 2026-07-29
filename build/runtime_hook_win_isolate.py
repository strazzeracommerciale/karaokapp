"""Isola le DLL Python bundled da altre installazioni Python sul PATH (Windows)."""

import os
import sys


def _is_system_python_dir(path: str) -> bool:
    lower = path.lower().replace("/", "\\")
    if "windowsapps" in lower:
        return True
    if "\\python3" in lower and (
        lower.endswith("\\scripts") or "\\python3" in lower.split("\\")[-1]
    ):
        return True
    for token in ("\\python313\\", "\\python312\\", "\\python311\\"):
        if token in lower:
            return True
    return False


if sys.platform == "win32" and getattr(sys, "frozen", False):
    app_dir = os.path.dirname(os.path.abspath(sys.executable))
    internal = os.path.join(app_dir, "_internal")

    for key in (
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHONEXECUTABLE",
        "PYTHONUTF8",
        "PYTHONNOUSERSITE",
    ):
        os.environ.pop(key, None)

    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(app_dir)
        if os.path.isdir(internal):
            os.add_dll_directory(internal)

    path_parts = os.environ.get("PATH", "").split(os.pathsep)
    filtered: list[str] = []
    seen: set[str] = set()
    for part in [app_dir, internal, *path_parts]:
        if not part or part in seen:
            continue
        if _is_system_python_dir(part):
            continue
        seen.add(part)
        filtered.append(part)
    os.environ["PATH"] = os.pathsep.join(filtered)
