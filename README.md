# Saitek/Logitech X-56 HOTAS PyQt6 RGB utility
A Python GUI for Saitek/Logitech X-56 HOTAS, RGB control with per-device selection, all-devices apply, refresh, and quick presets.

Currently working with these devices:  
0738:a221 Mad Catz, Inc. Saitek Pro Flight X-56 Rhino Throttle
0738:2221 Mad Catz, Inc. Saitek Pro Flight X-56 Rhino Stick

### Requirements

- Python 3.10+
- `libusb-1.0` installed on the system
- Python packages from [requirements.txt](requirements.txt)

### Install

#### Ubuntu / Debian

Install system dependencies:

`sudo apt update`

`sudo apt install -y python3 python3-venv libusb-1.0-0`

Create virtual environment and install Python dependencies:

`python3 -m venv .venv`

`source .venv/bin/activate`

`pip install -r requirements.txt`

#### Arch Linux (AUR)

Planned: package will be added later.


### Run

From the repository root:

`python3 -m venv .venv`

`source .venv/bin/activate`

`pip install -r requirements.txt`

`python3 -m x56gui`

On Linux, the GUI should detects missing X-56 udev rules and prompts to install them via `pkexec`.
If your user still does not have USB access, run with appropriate permissions or configure udev rules manually for devices `0738:2221` and `0738:a221`.

### Tray and startup

- The app can run in the system tray.
- Closing the window keeps the app running in tray.
- Tray menu includes `Show/Hide`, `Apply Defaults Now`, `Start on login`, and `Quit`.
- `Start on login` creates/removes `~/.config/autostart/x56gui.desktop`.
- On Arch Linux, autostart uses system Python (`/usr/bin/python`).
- On other distros, autostart prefers project `.venv/bin/python` if present, otherwise falls back to the current Python interpreter.

### Color calibration

The GUI includes per-device color calibration.

- Open `Calibration` in the main window.
- Select a device and choose a target color (Orange, Purple, Pink, etc).
- Move per-channel offsets (`R/G/B`) up or down until the visual color matches.
- Use `Preview Target` to test quickly on the selected device.
- Save calibration and it is applied automatically on future color changes.
- Calibration is stored per controller type (Joystick/Throttle), so it applies consistently after reconnects.
- In the main RGB panel, use `Calibration target` to force which profile is used (for example force `Orange` when applying `255,85,0`).

Calibration profiles are stored in:

- `~/.config/x56gui/calibration.json`

### Default profiles

The main window includes `Default Profiles` for each controller type (Joystick/Throttle).

- Save per-controller default RGB values.
- Optional default effect per controller (`Off`, `Rainbow`) with speed/brightness.
- Enable profile and it auto-applies on app load and when newly detected devices appear.

Default profiles are stored in:

- `~/.config/x56gui/profiles.json`