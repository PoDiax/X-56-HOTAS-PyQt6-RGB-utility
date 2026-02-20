from __future__ import annotations

from dataclasses import dataclass

import usb.core
import usb.util

from .calibration import ColorCalibration
from .protocol import (
    REQUEST_SET_REPORT,
    REQUEST_TYPE_SET_REPORT,
    SUPPORTED_PRODUCTS,
    USB_TIMEOUT_MS,
    VENDOR_ID,
    WINDEX_INTERFACE_2,
    WVALUE_APPLY,
    WVALUE_RGB,
    build_apply_packet,
    build_rgb_packet,
)


class BackendError(Exception):
    pass


@dataclass(frozen=True)
class DeviceInfo:
    id: int
    name: str
    bus: int
    address: int
    product_id: int


@dataclass
class _DeviceEntry:
    info: DeviceInfo
    device: usb.core.Device


class X56UsbBackend:
    def __init__(self) -> None:
        self._entries: list[_DeviceEntry] = []

    def refresh(self) -> list[DeviceInfo]:
        discovered = usb.core.find(find_all=True, idVendor=VENDOR_ID)
        devices = list(discovered or [])
        filtered = [
            dev
            for dev in devices
            if int(getattr(dev, "idProduct", 0)) in SUPPORTED_PRODUCTS
        ]
        filtered.sort(key=lambda dev: (int(getattr(dev, "bus", 0)), int(getattr(dev, "address", 0))))

        entries: list[_DeviceEntry] = []
        for index, dev in enumerate(filtered, start=1):
            product_id = int(dev.idProduct)
            entries.append(
                _DeviceEntry(
                    info=DeviceInfo(
                        id=index,
                        name=SUPPORTED_PRODUCTS[product_id],
                        bus=int(getattr(dev, "bus", 0)),
                        address=int(getattr(dev, "address", 0)),
                        product_id=product_id,
                    ),
                    device=dev,
                )
            )

        self._entries = entries
        return [entry.info for entry in entries]

    def set_rgb(self, device_id: int, red: int, green: int, blue: int) -> int:
        applied, failures = self.set_rgb_many([device_id], red, green, blue)
        if failures:
            raise BackendError(failures[0])
        return applied

    def set_rgb_many(
        self,
        device_ids: list[int],
        red: int,
        green: int,
        blue: int,
        calibrations: dict[int, ColorCalibration] | None = None,
        calibration_target: str | None = None,
    ) -> tuple[int, list[str]]:
        self._validate_rgb(red, green, blue)
        calibration_map = calibrations or {}

        if not self._entries:
            self.refresh()
        if not self._entries:
            raise BackendError("No compatible X-56 devices found.")

        if not device_ids:
            raise BackendError("No target device selected.")

        if 0 in device_ids:
            targets = list(self._entries)
        else:
            wanted = set(device_ids)
            targets = [entry for entry in self._entries if entry.info.id in wanted]

        if not targets:
            raise BackendError("Selected device ids were not found.")

        apply_packet = build_apply_packet()

        applied = 0
        failures: list[str] = []
        for entry in targets:
            try:
                calibration = calibration_map.get(entry.info.id)
                if calibration is not None:
                    target_name = calibration_target or calibration.closest_target_name(red, green, blue)
                    out_r, out_g, out_b = calibration.apply(red, green, blue, target_name=target_name)
                else:
                    out_r, out_g, out_b = red, green, blue

                rgb_packet = build_rgb_packet(out_r, out_g, out_b)
                self._set_rgb_single(entry.device, rgb_packet, apply_packet)
                applied += 1
            except BackendError as exc:
                failures.append(f"Device {entry.info.id} ({entry.info.name}): {exc}")
        return applied, failures

    @staticmethod
    def _validate_rgb(red: int, green: int, blue: int) -> None:
        for value in (red, green, blue):
            if value < 0 or value > 255:
                raise BackendError("RGB values must be in range 0-255.")

    def _set_rgb_single(
        self,
        device: usb.core.Device,
        rgb_packet: bytearray,
        apply_packet: bytearray,
    ) -> None:
        attempts = [
            ([2, 0], WINDEX_INTERFACE_2),
            ([2, 0], 2),
            ([2], WINDEX_INTERFACE_2),
            ([2], 2),
        ]

        last_error: BackendError | None = None
        for interfaces, windex in attempts:
            try:
                self._send_rgb_with_setup(device, interfaces, windex, rgb_packet, apply_packet)
                return
            except BackendError as exc:
                last_error = exc

        if last_error is not None:
            raise last_error
        raise BackendError("USB transfer failed. Unknown error.")

    def _send_rgb_with_setup(
        self,
        device: usb.core.Device,
        interfaces: list[int],
        windex: int,
        rgb_packet: bytearray,
        apply_packet: bytearray,
    ) -> None:
        attached_ifaces: list[int] = []

        try:
            try:
                device.set_configuration()
            except usb.core.USBError:
                pass

            for iface in interfaces:
                if self._kernel_active(device, iface):
                    device.detach_kernel_driver(iface)
                    attached_ifaces.append(iface)
                usb.util.claim_interface(device, iface)

            device.ctrl_transfer(
                REQUEST_TYPE_SET_REPORT,
                REQUEST_SET_REPORT,
                WVALUE_RGB,
                windex,
                rgb_packet,
                timeout=USB_TIMEOUT_MS,
            )
            try:
                device.ctrl_transfer(
                    REQUEST_TYPE_SET_REPORT,
                    REQUEST_SET_REPORT,
                    WVALUE_APPLY,
                    windex,
                    apply_packet,
                    timeout=USB_TIMEOUT_MS,
                )
            except usb.core.USBError as exc:
                if self._is_pipe_error(exc):
                    pass
                else:
                    raise
        except usb.core.USBError as exc:
            details = str(exc).strip()
            if details:
                raise BackendError(
                    f"USB transfer failed ({details})."
                ) from exc
            raise BackendError("USB transfer failed.") from exc
        finally:
            for iface in interfaces:
                try:
                    usb.util.release_interface(device, iface)
                except usb.core.USBError:
                    pass
                if iface in attached_ifaces:
                    try:
                        device.attach_kernel_driver(iface)
                    except usb.core.USBError:
                        pass

    @staticmethod
    def _is_pipe_error(exc: usb.core.USBError) -> bool:
        err_no = getattr(exc, "errno", None)
        if err_no == 32:
            return True
        return "pipe error" in str(exc).lower()

    @staticmethod
    def _kernel_active(device: usb.core.Device, iface: int) -> bool:
        try:
            return bool(device.is_kernel_driver_active(iface))
        except (NotImplementedError, usb.core.USBError):
            return False
