from __future__ import annotations

from pathlib import Path
import shlex
import sys


AUTOSTART_FILENAME = "x56gui.desktop"


def autostart_path() -> Path:
    return Path.home() / ".config" / "autostart" / AUTOSTART_FILENAME


def is_enabled() -> bool:
    return autostart_path().exists()


def enable() -> None:
    path = autostart_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    exec_command = _build_exec_command()
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        "Name=X-56 RGB Utility\n"
        "Comment=Apply saved X-56 RGB defaults in tray\n"
        f"Exec={exec_command}\n"
        "Terminal=false\n"
        "StartupNotify=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    )
    path.write_text(content, encoding="utf-8")


def disable() -> None:
    path = autostart_path()
    if path.exists():
        path.unlink()


def _build_exec_command() -> str:
    python_exec = shlex.quote(str(_preferred_python_executable()))
    return f"{python_exec} -m x56gui --start-hidden"


def _preferred_python_executable() -> Path:
    if _is_arch_linux():
        system_python = Path("/usr/bin/python")
        if system_python.exists() and system_python.is_file():
            return system_python

    project_root = Path(__file__).resolve().parents[1]
    venv_python = project_root / ".venv" / "bin" / "python"
    if venv_python.exists() and venv_python.is_file():
        return venv_python
    return Path(sys.executable)


def _is_arch_linux() -> bool:
    try:
        with open("/etc/os-release", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("ID_LIKE=") and "arch" in line.lower():
                    return True
                if line.startswith("ID=") and "arch" in line.lower():
                    return True
    except OSError:
        pass
    return False

# def get_os_release():
#     data = {}
#     path = Path("/etc/os-release")

#     if not path.exists():
#         return data

#     with path.open() as f:
#         for line in f:
#             if "=" not in line:
#                 continue
#             key, value = line.strip().split("=", 1)
#             data[key] = value.strip('"')

#     return data


# def is_arch_based():
#     os_info = get_os_release()

#     id_like = os_info.get("ID_LIKE", "").lower()
#     distro_id = os_info.get("ID", "").lower()

#     return "arch" in id_like.split() or distro_id == "arch"
