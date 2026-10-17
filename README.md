# Xloader

Xloader is a Linux-first desktop companion for signing, installing, and refreshing iOS apps on Apple devices.

The goal is to make the Linux-to-iPhone workflow understandable and reliable, with xtool as the first integration point.

## First milestone: cable-based installer

The SwiftPM build and IPA install pipelines have both succeeded on the connected iPhone. The first app milestone is to put that proven xtool flow behind a polished desktop interface, then validate it with more IPA sources and repeat installs:

1. Discover a connected iPhone over USB and show its connection state.
2. Select an IPA and display the provisioning, signing, packaging, and installation progress.
3. Reinstall an existing app over USB with a renewed provisioning profile and confirm its data is preserved.
4. Detect provisioning expiry and refresh eligible apps when the iPhone is connected by USB.

The SwiftPM build-and-run path and the import-an-IPA path are separate workflows. Xloader should verify both instead of assuming that IPA installation also handles signing.

### Verified: SwiftPM build and USB install

On 16 October 2026, `xtool 1.22.2 dev run --usb` was run from the MusicNative project. The debug build succeeded and xtool installed and verified the app on the connected iPhone. The observed deployment stages were:

1. Build the SwiftPM product.
2. Plan deployment and wait for the USB device.
3. Unpack the app and prepare the device.
4. Provision, sign, and package the app.
5. Connect, install, and verify the app.

This confirms the project build-and-run workflow, including provisioning and signing. The imported-IPA signing flow and provisioning refresh behavior still need verification. Device identifiers and account details are intentionally omitted from this note.

### Verified: IPA install and on-device signing

On 16 October 2026, `xtool dev build --ipa` generated `MusicNative.ipa`. Running `xtool install --usb` on that IPA completed successfully. The install output showed provisioning, signing, packaging, installation, and verification on the connected iPhone.

This confirms xtool can take an IPA through its provisioning and signing pipeline and install it over USB. The test IPA came from the SwiftPM project; compatibility with third-party IPAs and provisioning refresh behavior remain to be tested.

### Parked: network discovery

With the iPhone unplugged and on the same Wi-Fi network, `xtool devices --network --no-wait` exited successfully but returned no devices. `idevice_id --network` could not retrieve a device list, while Avahi did see the iPhone's Apple device service on the LAN. This points to a gap between network service discovery and the Linux device transport; network installation is not yet verified. Raw service identifiers and authentication tags are not recorded here.

Wireless refresh is out of the current MVP. The chosen workflow uses a USB cable.

## MVP direction

- A clear device view for connection, pairing, Developer Mode, and install status.
- A guided flow for building a SwiftPM project or importing an IPA.
- Visible signing and installation progress with useful, shareable diagnostics.
- A per-app view of signing status and expiry, with a refresh workflow where Apple permits it.
- Automatic refresh before expiry when the iPhone is connected over USB; retry on reconnection and show the result.
- Secure use of xtool's Apple authentication flow; credentials must not be written to project files or logs.

## Desktop implementation

- Use Python 3 with GTK 4 for the Linux desktop shell and native file selection.
- Call xtool as a child process for USB device discovery and IPA installation; keep output streaming so progress stays visible.
- Use the compact Sideloadly-inspired layout, charcoal surfaces, gray controls, a purple Apple ID focus edge, and short fade transitions.
- Keep the first version dependency-light and runnable from the cloned repository.

### Current prototype

The GTK window uses a fixed 800 × 420 compact desktop layout with a thin titlebar and charcoal Sideloadly-inspired controls. It detects an iPhone over USB, lets you browse for or drop an IPA, and runs `xtool install --usb` while showing streamed deployment stages and sanitized logs. The Apple ID field shows the saved account, team, and token expiry. Sign-in opens xtool's login flow in a terminal, while sign-out runs through xtool; Xloader does not collect or store Apple ID passwords. Install results use concise dialogs, with full sanitized output available on request. Refreshing currently means selecting the IPA again and reinstalling it. Installed-app inventory and automatic refresh scheduling are future work.

## Project principles

- Use xtool/XKit where they provide the needed supported capability; keep device and signing integration behind a replaceable service boundary.
- Use Apple's developer provisioning rules. Do not promise permanent installs or capabilities that the selected account cannot grant.
- Prove the core workflow from Linux before committing to a desktop UI stack.
- Keep Xloader independent of the MusicNative app and its backend.

## Run from source

Requirements: Python 3, PyGObject with GTK 4.10 or newer, and a USB device service (`usbmuxd`). When running from a source checkout, `XLOADER_XTOOL` can explicitly select a development runtime; otherwise Xloader prefers a bundled runtime before checking `~/.local/bin/xtool` and `PATH`.

From the repository root:

```sh
python3 -m xloader
```

Set `XLOADER_XTOOL` to override the runtime path during development.

### Live development preview

Run the preview watcher while editing the interface:

```sh
python3 scripts/dev-preview.py
```

Stylesheet changes apply to the open window. Changes to Python files restart the window automatically. Close the app window to stop the watcher, or press `Ctrl+C` in the terminal. The signing engine is optional for previewing the interface; without xtool, install actions remain unavailable.

## Install on Arch Linux, Garuda, or Manjaro

Build a native package from this checkout:

```sh
./scripts/build-arch-package.sh
```

The package is written to `dist/`. It contains Xloader and the pinned xtool 1.22.2 Linux runtime. GTK 4, PyGObject, and `usbmuxd` are declared as package dependencies, so Pacman installs any missing system components when the package is installed. Install the generated package with:

```sh
sudo pacman -U dist/xloader-0.1.0-1-$(uname -m).pkg.tar.zst
```

Launch **Xloader** from the desktop app menu or run `xloader`. The bundled xtool release is downloaded from the official project and SHA-256 verified during package build. Xcode.xip is not included; it is only needed for building Swift projects, not for importing an IPA.

The package build needs `makepkg`, `curl`, `tar`, and `sha256sum`. Run it as a regular user, not as root.

## References

- [xtool](https://github.com/xtool-org/xtool) — cross-platform iOS build, signing, and device tooling.
- [xtool documentation](https://xtool.sh/documentation/xtool/) — setup and workflows.
- [Apple Developer account overview](https://developer.apple.com/help/account/basics/about-your-developer-account) — Personal Team limits and provisioning.
