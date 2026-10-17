from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceInfo:
    udid: str
    name: str
    model: str


class DeviceService:
    """Reads USB device identity through libimobiledevice command-line tools."""

    def __init__(self) -> None:
        self._idevice_id = shutil.which("idevice_id")
        self._ideviceinfo = shutil.which("ideviceinfo")
        self._idevicepair = shutil.which("idevicepair")

    def list_usb_devices(self) -> list[DeviceInfo]:
        if not self._idevice_id:
            return []

        try:
            result = subprocess.run(
                [self._idevice_id, "-l"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return []

        if result.returncode != 0:
            return []

        devices: list[DeviceInfo] = []
        udids = dict.fromkeys(
            line.strip() for line in result.stdout.splitlines() if line.strip()
        )
        for udid in udids:
            name = self._read_info(udid, "DeviceName") or "Connected iDevice"
            model = self._read_info(udid, "ProductType") or "Model unavailable"
            devices.append(DeviceInfo(udid=udid, name=name, model=model))
        return devices

    def repair_pairing(self, udid: str) -> tuple[bool, str]:
        if not self._idevicepair:
            return False, "Install libimobiledevice to pair with an iPhone."

        try:
            subprocess.run(
                [self._idevicepair, "-u", udid, "unpair"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            paired = subprocess.run(
                [self._idevicepair, "-u", udid, "pair"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return False, "Pairing timed out. Unlock your iDevice and try again."
        except OSError:
            return False, "Could not start the device pairing tool."

        if paired.returncode == 0:
            return True, "The device is paired."
        return False, "Pairing failed. Unlock your iDevice, reconnect it, and accept the Trust prompt."

    def _read_info(self, udid: str, key: str) -> str | None:
        if not self._ideviceinfo:
            return None

        try:
            result = subprocess.run(
                [self._ideviceinfo, "-u", udid, "-k", key],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

        value = result.stdout.strip()
        prefix = f"{key}:"
        if value.startswith(prefix):
            value = value[len(prefix) :].strip()
        return value if result.returncode == 0 and value else None
