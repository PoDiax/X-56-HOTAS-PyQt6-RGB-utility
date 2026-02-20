from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


RULE_FILENAME = "99-x56-hotas.rules"
RULE_TARGET_PATH = Path("/etc/udev/rules.d") / RULE_FILENAME

RULE_CONTENT = """SUBSYSTEM==\"usb\", ATTR{idVendor}==\"0738\", ATTR{idProduct}==\"2221\", MODE=\"0666\", TAG+=\"uaccess\"
SUBSYSTEM==\"usb\", ATTR{idVendor}==\"0738\", ATTR{idProduct}==\"a221\", MODE=\"0666\", TAG+=\"uaccess\"
"""

_UDEV_RULE_DIRS = [
    Path("/etc/udev/rules.d"),
    Path("/run/udev/rules.d"),
    Path("/usr/lib/udev/rules.d"),
    Path("/lib/udev/rules.d"),
]


def should_manage_udev() -> bool:
    return os.name == "posix" and Path("/etc/udev").exists() and os.geteuid() != 0


def has_x56_udev_rule() -> bool:
    required_tokens = (
        'ATTR{idVendor}=="0738"',
        'ATTR{idProduct}=="2221"',
        'ATTR{idProduct}=="a221"',
    )

    for rules_dir in _UDEV_RULE_DIRS:
        if not rules_dir.exists():
            continue

        for rule_file in rules_dir.glob("*.rules"):
            try:
                text = rule_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            vendor_present = required_tokens[0] in text
            joystick_present = required_tokens[1] in text
            throttle_present = required_tokens[2] in text
            if vendor_present and joystick_present and throttle_present:
                return True
    return False


def install_x56_udev_rule() -> tuple[bool, str]:
    if not should_manage_udev():
        return False, "udev rule installation is not needed for this session."

    if has_x56_udev_rule():
        return True, "X-56 udev rule already exists."

    if shutil.which("pkexec") is None:
        return (
            False,
            "pkexec is not available. Create the rule manually:\n"
            f"{RULE_TARGET_PATH}\n"
            "Then run: sudo udevadm control --reload-rules && sudo udevadm trigger",
        )

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tmp:
            tmp.write(RULE_CONTENT)
            temp_path = Path(tmp.name)

        subprocess.run(
            [
                "pkexec",
                "install",
                "-m",
                "0644",
                str(temp_path),
                str(RULE_TARGET_PATH),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["pkexec", "udevadm", "control", "--reload-rules"],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["pkexec", "udevadm", "trigger"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        if stderr:
            return False, f"Failed to install udev rule: {stderr}"
        return False, "Failed to install udev rule."
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

    return True, "udev rule installed. Replug devices if they were already connected."
