import ctypes
import ctypes.util
import sys

from PyQt6.QtWidgets import QApplication

from .main_window import MainWindow


def _set_process_name(name: str) -> None:
    try:
        libc_path = ctypes.util.find_library("c") or "libc.so.6"
        libc = ctypes.CDLL(libc_path)
        pr_set_name = 15
        encoded = name.encode("utf-8")[:15]
        libc.prctl(pr_set_name, ctypes.c_char_p(encoded), 0, 0, 0)
    except Exception:
        pass

    try:
        sys.argv[0] = name
    except Exception:
        pass


def main() -> int:
    _set_process_name("x56gui")
    start_hidden = "--start-hidden" in sys.argv
    app = QApplication(sys.argv)
    app.setApplicationName("X-56 RGB Utility")
    app.setDesktopFileName("x56gui.desktop")
    window = MainWindow(start_hidden=start_hidden)
    if not start_hidden:
        window.show()
    return app.exec()
