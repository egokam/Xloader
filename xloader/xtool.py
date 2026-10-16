from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass
from collections.abc import Callable
from pathlib import Path


OutputCallback = Callable[[str], None]
CompletionCallback = Callable[[int], None]
LogoutCallback = Callable[[bool, str | None], None]


@dataclass(frozen=True)
class AuthStatus:
    signed_in: bool
    apple_id: str | None = None
    team_id: str | None = None
    token_expiry: str | None = None
    error: str | None = None


class XToolService:
    """Small asynchronous wrapper around Xloader's bundled xtool runtime."""

    def __init__(self) -> None:
        configured = os.environ.get("XLOADER_XTOOL")
        module_dir = Path(__file__).resolve().parent
        bundled_candidates = (
            module_dir / "vendor" / "xtool",
            module_dir / "vendor" / "xtool.AppImage",
        )
        local_binary = Path.home() / ".local" / "bin" / "xtool"
        self.executable = None
        self.source = None
        candidates = (
            ("configured", configured),
            *(("bundled", str(candidate)) for candidate in bundled_candidates),
            ("local", str(local_binary)),
            ("path", shutil.which("xtool")),
        )
        for source, candidate in candidates:
            if not candidate:
                continue
            resolved = shutil.which(candidate) or str(Path(candidate).expanduser())
            if Path(resolved).is_file() and os.access(resolved, os.X_OK):
                self.executable = resolved
                self.source = source
                break

    @property
    def available(self) -> bool:
        return bool(self.executable)

    @property
    def bundled(self) -> bool:
        return self.source == "bundled"

    def _environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        if self.bundled:
            # The bundled upstream release is an AppImage. Its extract-and-run
            # mode avoids requiring FUSE on the user's system.
            environment["APPIMAGE_EXTRACT_AND_RUN"] = "1"
        return environment

    def auth_status(self) -> AuthStatus:
        if not self.executable:
            return AuthStatus(False, error="Xloader's signing engine was not found")

        try:
            result = subprocess.run(
                [self.executable, "auth", "status"],
                capture_output=True,
                text=True,
                timeout=12,
                check=False,
                env=self._environment(),
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return AuthStatus(False, error=self.clean_output(str(error)))

        output = self._strip_ansi(result.stdout + "\n" + result.stderr)
        signed_in = bool(re.search(r"(?im)^\s*Logged in\.", output))
        if not signed_in:
            explicit_signed_out = bool(
                re.search(r"(?im)^\s*(Not logged in|Logged out)\b", output)
            )
            error = None
            if result.returncode != 0 and not explicit_signed_out:
                error = self.clean_output(output.strip()) or "Could not read xtool account status"
            return AuthStatus(False, error=error)

        return AuthStatus(
            signed_in=True,
            apple_id=self._status_value(output, "Apple ID"),
            team_id=self._status_value(output, "Team ID"),
            token_expiry=self._status_value(output, "Token expiry"),
        )

    def logout(self, callback: LogoutCallback) -> None:
        if not self.executable:
            callback(False, "Xloader's signing engine was not found")
            return

        def worker() -> None:
            try:
                result = subprocess.run(
                    [self.executable, "auth", "logout"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                    env=self._environment(),
                )
                detail = self.clean_output((result.stderr or result.stdout).strip())
                callback(result.returncode == 0, detail or None)
            except (OSError, subprocess.TimeoutExpired) as error:
                callback(False, self.clean_output(str(error)))

        threading.Thread(target=worker, name="xloader-auth-logout", daemon=True).start()

    def open_login_terminal(self) -> str | None:
        if not self.executable:
            return "Xloader's signing engine was not found"

        terminals = (
            ("konsole", ["--separate", "-e"]),
            ("x-terminal-emulator", ["-e"]),
            ("xterm", ["-T", "Xloader · Apple sign-in", "-e"]),
        )
        for command, prefix in terminals:
            terminal = shutil.which(command)
            if not terminal:
                continue
            try:
                subprocess.Popen(
                    [terminal, *prefix, self.executable, "auth", "login"],
                    cwd=str(Path.home()),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                    env=self._environment(),
                )
                return None
            except OSError as error:
                return self.clean_output(str(error))
        return "No terminal app was found. Install a terminal app and try signing in again."

    def find_usb_device(self) -> tuple[str | None, str | None]:
        if not self.executable:
            return None, "xtool was not found"

        try:
            result = subprocess.run(
                [self.executable, "devices", "--usb", "--no-wait"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
                env=self._environment(),
            )
        except subprocess.TimeoutExpired:
            return None, "Device scan timed out"
        except OSError as error:
            return None, str(error)

        if result.returncode != 0:
            details = self.clean_output(result.stderr or result.stdout).strip()
            return None, details or "xtool could not scan USB devices"

        for line in result.stdout.splitlines():
            match = re.match(r"\s*(.+?)\s+\[usb\]:\s+\S+\s*$", line)
            if match:
                return match.group(1).strip(), None
        return None, None

    def install_ipa(self, ipa_path: str, on_output: OutputCallback, on_complete: CompletionCallback) -> None:
        if not self.executable:
            on_output("xtool was not found")
            on_complete(127)
            return

        def worker() -> None:
            try:
                process = subprocess.Popen(
                    [self.executable, "install", "--usb", ipa_path],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    env=self._environment(),
                )
                if process.stdout is not None:
                    for line in process.stdout:
                        line = self.clean_output(line.rstrip())
                        if line:
                            on_output(line)
                on_complete(process.wait())
            except OSError as error:
                on_output(f"Could not start xtool: {error}")
                on_complete(127)

        threading.Thread(target=worker, name="xloader-install", daemon=True).start()

    @staticmethod
    def clean_output(value: str) -> str:
        value = re.sub(r"\budid:\s*\S+", "device ID hidden", value, flags=re.IGNORECASE)
        value = re.sub(
            r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b",
            "Apple Account hidden",
            value,
        )
        return value

    @staticmethod
    def _status_value(output: str, name: str) -> str | None:
        match = re.search(rf"(?im)^\s*-\s*{re.escape(name)}:\s*(.+?)\s*$", output)
        return match.group(1).strip() if match else None

    @staticmethod
    def _strip_ansi(value: str) -> str:
        return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)
