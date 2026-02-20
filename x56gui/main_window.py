from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QAction, QCloseEvent, QColor, QIcon
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QColorDialog,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QMenu,
    QPushButton,
    QSpinBox,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .calibration import CALIBRATION_COLORS, CalibrationStore, ColorCalibration, ColorOffset
from .effects import EFFECT_MODES, EFFECT_OFF, compute_effect_color, next_phase
from .profile_store import DeviceDefaultProfile, ProfileStore
from .protocol import SUPPORTED_PRODUCTS
from .startup import disable as disable_autostart
from .startup import enable as enable_autostart
from .startup import is_enabled as is_autostart_enabled
from .udev import has_x56_udev_rule, install_x56_udev_rule, should_manage_udev
from .usb_backend import BackendError, DeviceInfo, X56UsbBackend


PRESETS: list[tuple[str, tuple[int, int, int]]] = [
    ("Red", (255, 0, 0)),
    ("Green", (0, 255, 0)),
    ("Blue", (0, 0, 255)),
    ("White", (255, 255, 255)),
    ("Amber", (255, 128, 0)),
]


@dataclass
class EffectSession:
    key: str
    mode: str
    speed: int
    brightness: int
    base_rgb: tuple[int, int, int]
    target_ids: list[int]
    product_id: int | None = None
    phase: float = 0.0


class CalibrationDialog(QDialog):
    def __init__(
        self,
        devices: list[DeviceInfo],
        store: CalibrationStore,
        preview_callback,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._devices = devices
        self._store = store
        self._preview_callback = preview_callback

        self.setWindowTitle("Color Calibration")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.device_combo = QComboBox()
        for device in devices:
            label = f"{device.id}: {device.name} (bus {device.bus}, device {device.address})"
            self.device_combo.addItem(label, userData=device.id)
        self.device_combo.currentIndexChanged.connect(self._load_current_profile)
        form.addRow("Device", self.device_combo)

        self.target_combo = QComboBox()
        for name in CALIBRATION_COLORS.keys():
            self.target_combo.addItem(name)
        self.target_combo.currentIndexChanged.connect(self._load_current_profile)
        form.addRow("Target color", self.target_combo)

        self.offset_r = self._make_offset_spin()
        self.offset_g = self._make_offset_spin()
        self.offset_b = self._make_offset_spin()
        form.addRow("Red offset", self.offset_r)
        form.addRow("Green offset", self.offset_g)
        form.addRow("Blue offset", self.offset_b)

        layout.addLayout(form)

        info = QLabel(
            "Use target color and offsets to visually match this device.\n"
            "Preview sends the selected target immediately to the selected device."
        )
        layout.addWidget(info)

        buttons = QHBoxLayout()
        preview_button = QPushButton("Preview Target")
        preview_button.clicked.connect(self._preview_target)
        save_button = QPushButton("Save")
        save_button.clicked.connect(self._save_profile)
        reset_button = QPushButton("Reset")
        reset_button.clicked.connect(self._reset_profile)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)

        buttons.addWidget(preview_button)
        buttons.addWidget(save_button)
        buttons.addWidget(reset_button)
        buttons.addStretch(1)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        if devices:
            self._load_current_profile()

    @staticmethod
    def _make_offset_spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(-255.0, 255.0)
        spin.setSingleStep(1.0)
        spin.setDecimals(0)
        spin.setValue(0.0)
        return spin

    def _current_device(self) -> DeviceInfo | None:
        if not self._devices:
            return None
        selected_id = self.device_combo.currentData()
        if selected_id is None:
            return None
        for dev in self._devices:
            if dev.id == int(selected_id):
                return dev
        return None

    def _set_offsets(self, offset: ColorOffset) -> None:
        self.offset_r.setValue(float(offset.red))
        self.offset_g.setValue(float(offset.green))
        self.offset_b.setValue(float(offset.blue))

    def _load_current_profile(self) -> None:
        device = self._current_device()
        if device is None:
            return
        calibration = self._store.get_for_device(device)
        if calibration is None:
            calibration = ColorCalibration()
        self._set_offsets(calibration.offset_for(self.target_combo.currentText()))

    def _current_offset(self) -> ColorOffset:
        return ColorOffset(
            red=int(round(self.offset_r.value())),
            green=int(round(self.offset_g.value())),
            blue=int(round(self.offset_b.value())),
        )

    def _save_profile(self) -> None:
        device = self._current_device()
        if device is None:
            return
        calibration = self._store.get_for_device(device)
        if calibration is None:
            calibration = ColorCalibration()
        updated = calibration.with_offset(self.target_combo.currentText(), self._current_offset())
        self._store.set_for_device(device, updated)
        QMessageBox.information(self, "Color Calibration", "Calibration saved for selected device.")

    def _reset_profile(self) -> None:
        device = self._current_device()
        if device is None:
            return
        calibration = self._store.get_for_device(device)
        if calibration is None:
            calibration = ColorCalibration()
        updated = calibration.with_offset(self.target_combo.currentText(), ColorOffset())
        self._store.set_for_device(device, updated)
        self._set_offsets(ColorOffset())
        QMessageBox.information(self, "Color Calibration", "Offset reset for selected color.")

    def _preview_target(self) -> None:
        device = self._current_device()
        if device is None:
            return
        target_name = self.target_combo.currentText()
        base = CALIBRATION_COLORS[target_name]

        calibration = self._store.get_for_device(device)
        if calibration is None:
            calibration = ColorCalibration()
        calibration = calibration.with_offset(target_name, self._current_offset())

        self._preview_callback(device.id, base, calibration)


class MainWindow(QMainWindow):
    def __init__(self, start_hidden: bool = False) -> None:
        super().__init__()
        self.backend = X56UsbBackend()
        self.calibration_store = CalibrationStore()
        self.profile_store = ProfileStore()
        self._devices: list[DeviceInfo] = []
        self._udev_prompted = False
        self._start_hidden = start_hidden
        self._quitting = False
        self._detected_keys: set[tuple[int, int, int]] = set()
        self._profile_controls: dict[int, dict[str, object]] = {}
        self._effect_sessions: dict[str, EffectSession] = {}

        self.setWindowTitle("X-56 RGB Utility")
        self.setMinimumWidth(760)

        self._build_ui()
        self._build_tray()
        self._load_default_profiles_ui()
        self.refresh_devices()
        self._auto_apply_default_profiles(new_only=False)
        self._start_detection_poll()
        self._start_effect_timer()
        self._check_udev_rules_prompt()

    def _build_ui(self) -> None:
        root = QWidget(self)
        root_layout = QVBoxLayout(root)

        devices_box = QGroupBox("Devices")
        devices_layout = QVBoxLayout(devices_box)

        row = QHBoxLayout()
        self.all_devices_checkbox = QCheckBox("All devices")
        self.all_devices_checkbox.setChecked(True)
        self.all_devices_checkbox.toggled.connect(self._on_all_devices_toggled)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_devices)
        self.calibration_button = QPushButton("Calibration")
        self.calibration_button.clicked.connect(self.open_calibration_dialog)
        row.addWidget(self.all_devices_checkbox)
        row.addStretch(1)
        row.addWidget(self.calibration_button)
        row.addWidget(self.refresh_button)
        devices_layout.addLayout(row)

        self.device_list = QListWidget()
        self.device_list.setMinimumHeight(110)
        self.device_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        devices_layout.addWidget(self.device_list)
        root_layout.addWidget(devices_box)

        rgb_box = QGroupBox("RGB")
        rgb_layout = QGridLayout(rgb_box)
        self.red_spin = self._make_rgb_spinbox()
        self.green_spin = self._make_rgb_spinbox()
        self.blue_spin = self._make_rgb_spinbox()

        rgb_layout.addWidget(QLabel("Red"), 0, 0)
        rgb_layout.addWidget(self.red_spin, 0, 1)
        rgb_layout.addWidget(QLabel("Green"), 1, 0)
        rgb_layout.addWidget(self.green_spin, 1, 1)
        rgb_layout.addWidget(QLabel("Blue"), 2, 0)
        rgb_layout.addWidget(self.blue_spin, 2, 1)

        self.calibration_target_combo = QComboBox()
        self.calibration_target_combo.addItem("Auto (nearest)", userData=None)
        for name in CALIBRATION_COLORS.keys():
            self.calibration_target_combo.addItem(name, userData=name)
        rgb_layout.addWidget(QLabel("Calibration target"), 3, 0)
        rgb_layout.addWidget(self.calibration_target_combo, 3, 1)

        self.pick_button = QPushButton("Pick Color")
        self.pick_button.clicked.connect(self.pick_color)
        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self.apply_rgb)
        rgb_layout.addWidget(self.pick_button, 4, 0)
        rgb_layout.addWidget(self.apply_button, 4, 1)

        self.copy_default_device_combo = QComboBox()
        for product_id, product_name in sorted(SUPPORTED_PRODUCTS.items()):
            self.copy_default_device_combo.addItem(product_name, userData=product_id)

        self.copy_to_default_button = QPushButton("Copy to selected default")
        self.copy_to_default_button.clicked.connect(self.copy_color_to_selected_default)
        self.copy_to_all_defaults_button = QPushButton("Copy to all defaults")
        self.copy_to_all_defaults_button.clicked.connect(self.copy_color_to_all_defaults)

        rgb_layout.addWidget(QLabel("Default profile target"), 5, 0)
        rgb_layout.addWidget(self.copy_default_device_combo, 5, 1)
        rgb_layout.addWidget(self.copy_to_default_button, 6, 0)
        rgb_layout.addWidget(self.copy_to_all_defaults_button, 6, 1)

        root_layout.addWidget(rgb_box)

        presets_box = QGroupBox("Quick Presets")
        presets_layout = QHBoxLayout(presets_box)
        for name, rgb in PRESETS:
            button = QPushButton(name)
            button.clicked.connect(lambda _checked=False, c=rgb: self.apply_preset(c))
            presets_layout.addWidget(button)
        root_layout.addWidget(presets_box)

        profiles_box = QGroupBox("Default Profiles")
        profiles_layout = QGridLayout(profiles_box)
        profiles_layout.addWidget(QLabel("Controller"), 0, 0)
        profiles_layout.addWidget(QLabel("Enable"), 0, 1)
        profiles_layout.addWidget(QLabel("R"), 0, 2)
        profiles_layout.addWidget(QLabel("G"), 0, 3)
        profiles_layout.addWidget(QLabel("B"), 0, 4)
        profiles_layout.addWidget(QLabel("Effect"), 0, 5)
        profiles_layout.addWidget(QLabel("Spd"), 0, 6)
        profiles_layout.addWidget(QLabel("Bri"), 0, 7)
        profiles_layout.addWidget(QLabel("Action"), 0, 8)

        row_index = 1
        for product_id, product_name in sorted(SUPPORTED_PRODUCTS.items()):
            enabled_box = QCheckBox()
            red_spin = self._make_rgb_spinbox()
            green_spin = self._make_rgb_spinbox()
            blue_spin = self._make_rgb_spinbox()
            effect_mode_combo = QComboBox()
            effect_mode_combo.addItem("Off", userData=EFFECT_OFF)
            effect_mode_combo.addItem("Rainbow", userData="rainbow")

            effect_speed_spin = QSpinBox()
            effect_speed_spin.setRange(1, 20)
            effect_speed_spin.setValue(3)

            effect_brightness_spin = QSpinBox()
            effect_brightness_spin.setRange(5, 100)
            effect_brightness_spin.setValue(100)

            save_button = QPushButton("Save")
            save_button.clicked.connect(
                lambda _checked=False, pid=product_id: self._save_default_profile_for(pid)
            )

            profiles_layout.addWidget(QLabel(product_name), row_index, 0)
            profiles_layout.addWidget(enabled_box, row_index, 1)
            profiles_layout.addWidget(red_spin, row_index, 2)
            profiles_layout.addWidget(green_spin, row_index, 3)
            profiles_layout.addWidget(blue_spin, row_index, 4)
            profiles_layout.addWidget(effect_mode_combo, row_index, 5)
            profiles_layout.addWidget(effect_speed_spin, row_index, 6)
            profiles_layout.addWidget(effect_brightness_spin, row_index, 7)
            profiles_layout.addWidget(save_button, row_index, 8)

            self._profile_controls[product_id] = {
                "enabled": enabled_box,
                "red": red_spin,
                "green": green_spin,
                "blue": blue_spin,
                "effect_mode": effect_mode_combo,
                "effect_speed": effect_speed_spin,
                "effect_brightness": effect_brightness_spin,
            }
            row_index += 1

        self.apply_defaults_button = QPushButton("Apply Defaults Now")
        self.apply_defaults_button.clicked.connect(lambda: self._auto_apply_default_profiles(new_only=False))
        profiles_layout.addWidget(self.apply_defaults_button, row_index, 0, 1, 9)
        root_layout.addWidget(profiles_box)

        self.status_label = QLabel("")
        root_layout.addWidget(self.status_label)

        self.setCentralWidget(root)

    @staticmethod
    def _make_rgb_spinbox() -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(0, 255)
        return spin

    def refresh_devices(self, show_errors: bool = True) -> None:

        selected_keys: set[tuple[int, int, int]] = set()
        if not self.all_devices_checkbox.isChecked():
            for item in self.device_list.selectedItems():
                key = item.data(Qt.ItemDataRole.UserRole + 1)
                if isinstance(key, tuple) and len(key) == 3:
                    selected_keys.add((int(key[0]), int(key[1]), int(key[2])))

        try:
            self._devices = self.backend.refresh()
        except BackendError as exc:
            if show_errors:
                self._show_error(str(exc))
            return

        self.device_list.clear()

        for dev in self._devices:
            label = f"{dev.id}: {dev.name} (bus {dev.bus}, device {dev.address})"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, dev.id)
            item.setData(Qt.ItemDataRole.UserRole + 1, (dev.product_id, dev.bus, dev.address))
            self.device_list.addItem(item)

        self._detected_keys = {(dev.product_id, dev.bus, dev.address) for dev in self._devices}

        if self._devices:
            if self.all_devices_checkbox.isChecked():
                self._select_all_list_items()
            else:
                for index in range(self.device_list.count()):
                    item = self.device_list.item(index)
                    key = item.data(Qt.ItemDataRole.UserRole + 1)
                    if isinstance(key, tuple) and len(key) == 3:
                        if (int(key[0]), int(key[1]), int(key[2])) in selected_keys:
                            item.setSelected(True)
            self.status_label.setText(f"Found {len(self._devices)} compatible device(s).")
        else:
            self.status_label.setText("No compatible devices found.")

        self._on_all_devices_toggled(self.all_devices_checkbox.isChecked())

    def pick_color(self) -> None:
        current = QColor(self.red_spin.value(), self.green_spin.value(), self.blue_spin.value())
        chosen = QColorDialog.getColor(current, self, "Select RGB Color")
        if not chosen.isValid():
            return
        self.red_spin.setValue(chosen.red())
        self.green_spin.setValue(chosen.green())
        self.blue_spin.setValue(chosen.blue())

    def apply_preset(self, rgb: tuple[int, int, int]) -> None:
        self.red_spin.setValue(rgb[0])
        self.green_spin.setValue(rgb[1])
        self.blue_spin.setValue(rgb[2])
        self.apply_rgb()

    def copy_color_to_selected_default(self) -> None:
        selected_product_id = self.copy_default_device_combo.currentData()
        if selected_product_id is None:
            self._show_error("No default profile target selected.")
            return
        self._copy_current_color_to_default(int(selected_product_id))

    def copy_color_to_all_defaults(self) -> None:
        for product_id in sorted(SUPPORTED_PRODUCTS.keys()):
            self._copy_current_color_to_default(product_id)
        self.status_label.setText("Copied current RGB to all default profiles.")
        self._tray_message("X-56 Defaults", "Copied current RGB to all default profiles.")

    def _copy_current_color_to_default(self, product_id: int) -> None:
        controls = self._profile_controls.get(product_id)
        if controls is None:
            return
        controls["red"].setValue(self.red_spin.value())
        controls["green"].setValue(self.green_spin.value())
        controls["blue"].setValue(self.blue_spin.value())
        self._save_default_profile_for(product_id)

    def apply_rgb(self) -> None:
        if not self._devices:
            self._show_error("No compatible devices found. Connect devices and refresh.")
            return

        if self.all_devices_checkbox.isChecked():
            target_ids = [0]
        else:
            target_ids = self._selected_device_ids()
            if not target_ids:
                self._show_error("Select at least one device or enable All devices.")
                return

        red = self.red_spin.value()
        green = self.green_spin.value()
        blue = self.blue_spin.value()

        try:
            calibration_map = self._build_calibration_map(target_ids)
            calibration_target = self.calibration_target_combo.currentData()
            applied, failures = self.backend.set_rgb_many(
                target_ids,
                red,
                green,
                blue,
                calibrations=calibration_map,
                calibration_target=calibration_target,
            )
        except BackendError as exc:
            self._show_error(str(exc))
            return

        if self.all_devices_checkbox.isChecked():
            target_text = "all devices"
        else:
            target_text = "selected devices"

        if failures:
            message = (
                f"Applied RGB ({red},{green},{blue}) to {target_text}: {applied} success, "
                f"{len(failures)} failed.\n\n" + "\n".join(failures)
            )
            self.status_label.setText(
                f"Applied RGB with partial success: {applied} success, {len(failures)} failed."
            )
            QMessageBox.warning(self, "X-56 RGB Utility", message)
            return

        self.status_label.setText(f"Applied RGB ({red},{green},{blue}) to {target_text} ({applied} device(s)).")

    def _show_error(self, message: str) -> None:
        self.status_label.setText(message)
        QMessageBox.critical(self, "X-56 RGB Utility", message)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._quitting:
            event.accept()
            return
        if getattr(self, "tray", None) is not None and self.tray.isVisible():
            self.hide()
            event.ignore()
            self.status_label.setText("Running in tray.")
            return
        event.accept()

    def _build_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            if self._start_hidden:
                self.show()
            return

        tray_icon = QIcon.fromTheme("input-gaming")
        if tray_icon.isNull():
            tray_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)

        self.tray = QSystemTrayIcon(tray_icon, self)
        menu = QMenu(self)

        show_action = QAction("Show/Hide", self)
        show_action.triggered.connect(self._toggle_window_visibility)
        menu.addAction(show_action)

        apply_action = QAction("Apply Defaults Now", self)
        apply_action.triggered.connect(lambda: self._auto_apply_default_profiles(new_only=False))
        menu.addAction(apply_action)

        stop_effects_action = QAction("Stop Effects", self)
        stop_effects_action.triggered.connect(self.stop_all_effects)
        menu.addAction(stop_effects_action)

        self.autostart_action = QAction("Start on login", self)
        self.autostart_action.setCheckable(True)
        self.autostart_action.setChecked(is_autostart_enabled())
        self.autostart_action.triggered.connect(self._toggle_autostart)
        menu.addAction(self.autostart_action)

        menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._quit_from_tray)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

        if self._start_hidden:
            self.hide()
            self.status_label.setText("Started hidden in tray.")

    def _toggle_window_visibility(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def _tray_message(
        self,
        title: str,
        message: str,
        icon: QSystemTrayIcon.MessageIcon = QSystemTrayIcon.MessageIcon.Information,
    ) -> None:
        tray = getattr(self, "tray", None)
        if tray is not None and tray.isVisible():
            tray.showMessage(title, message, icon, 4000)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._toggle_window_visibility()

    def _quit_from_tray(self) -> None:
        self._quitting = True
        self._effect_sessions.clear()
        if getattr(self, "tray", None) is not None:
            self.tray.hide()
        self.close()

    def _toggle_autostart(self, checked: bool) -> None:
        try:
            if checked:
                enable_autostart()
                self.status_label.setText("Start on login enabled.")
            else:
                disable_autostart()
                self.status_label.setText("Start on login disabled.")
        except OSError as exc:
            self._show_error(f"Failed to update autostart: {exc}")
            if hasattr(self, "autostart_action"):
                self.autostart_action.setChecked(is_autostart_enabled())

    def _start_detection_poll(self) -> None:
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(4000)
        self.poll_timer.timeout.connect(self._poll_devices)
        self.poll_timer.start()

    def _start_effect_timer(self) -> None:
        self.effect_timer = QTimer(self)
        self.effect_timer.setInterval(180)
        self.effect_timer.timeout.connect(self._effect_tick)
        self.effect_timer.start()

    def _poll_devices(self) -> None:
        previous = set(self._detected_keys)
        self.refresh_devices(show_errors=False)
        current = set(self._detected_keys)
        newly_detected = current - previous
        if newly_detected:
            self._auto_apply_default_profiles(new_only=True, new_keys=newly_detected)

    def _resolved_target_ids(self, session: EffectSession) -> list[int]:
        if session.product_id is not None:
            return [dev.id for dev in self._devices if dev.product_id == session.product_id]
        valid = {dev.id for dev in self._devices}
        return [device_id for device_id in session.target_ids if device_id in valid]

    def _effect_tick(self) -> None:
        if not self._effect_sessions or not self._devices:
            return

        session_keys = list(self._effect_sessions.keys())
        for session_key in session_keys:
            session = self._effect_sessions.get(session_key)
            if session is None:
                continue
            if session.mode == EFFECT_OFF:
                del self._effect_sessions[session_key]
                continue

            target_ids = self._resolved_target_ids(session)
            if not target_ids:
                continue

            out_rgb = compute_effect_color(
                session.mode,
                session.base_rgb,
                session.phase,
                session.brightness / 100.0,
            )
            calibration_map = self._build_calibration_map(target_ids)
            try:
                _, failures = self.backend.set_rgb_many(
                    target_ids,
                    out_rgb[0],
                    out_rgb[1],
                    out_rgb[2],
                    calibrations=calibration_map,
                )
            except BackendError as exc:
                continue
            session.phase = next_phase(session.phase, session.speed)

    def stop_all_effects(self) -> None:
        self._effect_sessions.clear()
        self.status_label.setText("Stopped all effects.")
        self._tray_message("X-56 Effects", "Stopped all effects.")

    def _load_default_profiles_ui(self) -> None:
        for product_id, controls in self._profile_controls.items():
            profile = self.profile_store.get(product_id)
            enabled_box = controls["enabled"]
            red_spin = controls["red"]
            green_spin = controls["green"]
            blue_spin = controls["blue"]
            effect_mode_combo = controls["effect_mode"]
            effect_speed_spin = controls["effect_speed"]
            effect_brightness_spin = controls["effect_brightness"]

            enabled_box.setChecked(profile.enabled)
            red_spin.setValue(profile.red)
            green_spin.setValue(profile.green)
            blue_spin.setValue(profile.blue)

            effect_index = effect_mode_combo.findData(profile.effect_mode)
            effect_mode_combo.setCurrentIndex(max(0, effect_index))
            effect_speed_spin.setValue(profile.effect_speed)
            effect_brightness_spin.setValue(profile.effect_brightness)

    def _save_default_profile_for(self, product_id: int) -> None:
        controls = self._profile_controls.get(product_id)
        if controls is None:
            return

        enabled_box = controls["enabled"]
        red_spin = controls["red"]
        green_spin = controls["green"]
        blue_spin = controls["blue"]
        effect_mode_combo = controls["effect_mode"]
        effect_speed_spin = controls["effect_speed"]
        effect_brightness_spin = controls["effect_brightness"]

        effect_mode = effect_mode_combo.currentData()
        effect_enabled = effect_mode is not None and effect_mode != EFFECT_OFF

        profile = DeviceDefaultProfile(
            enabled=bool(enabled_box.isChecked()),
            name="Default",
            red=int(red_spin.value()),
            green=int(green_spin.value()),
            blue=int(blue_spin.value()),
            effect_enabled=effect_enabled,
            effect_mode=str(effect_mode) if effect_mode is not None else EFFECT_OFF,
            effect_speed=int(effect_speed_spin.value()),
            effect_brightness=int(effect_brightness_spin.value()),
        )
        self.profile_store.set(product_id, profile)
        self.status_label.setText(f"Saved default profile for {SUPPORTED_PRODUCTS[product_id]}.")
        self._tray_message(
            "X-56 Defaults",
            f"Saved default profile for {SUPPORTED_PRODUCTS[product_id]}.",
        )

    def _auto_apply_default_profiles(
        self,
        new_only: bool,
        new_keys: set[tuple[int, int, int]] | None = None,
    ) -> None:
        if not self._devices:
            return

        by_product: dict[int, list[int]] = {}
        for device in self._devices:
            by_product.setdefault(device.product_id, []).append(device.id)

        for product_id, device_ids in by_product.items():
            profile = self.profile_store.get(product_id)
            if not profile.enabled:
                self._effect_sessions.pop(f"profile:{product_id}", None)
                continue

            target_ids = device_ids
            if new_only:
                new_ids: list[int] = []
                for dev in self._devices:
                    key = (dev.product_id, dev.bus, dev.address)
                    if dev.product_id == product_id and new_keys is not None and key in new_keys:
                        new_ids.append(dev.id)
                target_ids = new_ids

            if not target_ids:
                continue

            if profile.effect_enabled and profile.effect_mode in EFFECT_MODES and profile.effect_mode != EFFECT_OFF:
                self._effect_sessions[f"profile:{product_id}"] = EffectSession(
                    key=f"profile:{product_id}",
                    mode=profile.effect_mode,
                    speed=profile.effect_speed,
                    brightness=profile.effect_brightness,
                    base_rgb=(profile.red, profile.green, profile.blue),
                    target_ids=[],
                    product_id=product_id,
                    phase=0.0,
                )
                self.status_label.setText(
                    f"Started default {profile.effect_mode} effect for {SUPPORTED_PRODUCTS[product_id]}."
                )
                continue
            self._effect_sessions.pop(f"profile:{product_id}", None)

            calibration_map = self._build_calibration_map(target_ids)
            applied, failures = self.backend.set_rgb_many(
                target_ids,
                profile.red,
                profile.green,
                profile.blue,
                calibrations=calibration_map,
            )
            if failures:
                self._tray_message(
                    "X-56 Defaults",
                    f"{SUPPORTED_PRODUCTS[product_id]}: {len(failures)} device(s) failed while applying defaults.",
                    QSystemTrayIcon.MessageIcon.Warning,
                )
            if applied:
                self.status_label.setText(
                    f"Applied default profile to {applied} {SUPPORTED_PRODUCTS[product_id]} device(s)."
                )
                self._tray_message(
                    "X-56 Defaults",
                    f"Applied default profile to {applied} {SUPPORTED_PRODUCTS[product_id]} device(s).",
                )

    def _on_all_devices_toggled(self, checked: bool) -> None:
        self.device_list.setEnabled(not checked)
        if checked:
            self._select_all_list_items()

    def _select_all_list_items(self) -> None:
        for index in range(self.device_list.count()):
            item = self.device_list.item(index)
            item.setSelected(True)

    def _selected_device_ids(self) -> list[int]:
        ids: list[int] = []
        for item in self.device_list.selectedItems():
            data = item.data(Qt.ItemDataRole.UserRole)
            if data is not None:
                ids.append(int(data))
        return ids

    def _build_calibration_map(self, target_ids: list[int]) -> dict[int, ColorCalibration]:
        if 0 in target_ids:
            target_set = {device.id for device in self._devices}
        else:
            target_set = set(target_ids)

        calibration_map: dict[int, ColorCalibration] = {}
        for device in self._devices:
            if device.id not in target_set:
                continue
            calibration = self.calibration_store.get_for_device(device)
            if calibration is not None:
                calibration_map[device.id] = calibration
        return calibration_map

    def open_calibration_dialog(self) -> None:
        if not self._devices:
            self._show_error("No devices found. Refresh first.")
            return
        dialog = CalibrationDialog(self._devices, self.calibration_store, self._preview_calibration_target, self)
        dialog.exec()

    def _preview_calibration_target(
        self,
        device_id: int,
        target_rgb: tuple[int, int, int],
        calibration: ColorCalibration,
    ) -> None:
        try:
            applied, failures = self.backend.set_rgb_many(
                [device_id],
                target_rgb[0],
                target_rgb[1],
                target_rgb[2],
                calibrations={device_id: calibration},
            )
        except BackendError as exc:
            self._show_error(str(exc))
            return

        if failures:
            self._show_error(failures[0])
            return

        self.status_label.setText(
            f"Preview sent to device {device_id}: target RGB ({target_rgb[0]},{target_rgb[1]},{target_rgb[2]})."
        )

    def _check_udev_rules_prompt(self) -> None:
        if self._udev_prompted:
            return
        if not should_manage_udev():
            return
        if has_x56_udev_rule():
            return

        self._udev_prompted = True
        reply = QMessageBox.question(
            self,
            "X-56 udev Rule",
            "No X-56 udev rule was detected.\n"
            "Install it now so the GUI can access devices without sudo?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            self.status_label.setText("udev rule not installed. You may need sudo for USB access.")
            return

        success, message = install_x56_udev_rule()
        if success:
            self.status_label.setText(message)
            QMessageBox.information(self, "X-56 udev Rule", message)
        else:
            self.status_label.setText(message)
            QMessageBox.warning(self, "X-56 udev Rule", message)
