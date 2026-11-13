# Chargeview

**Battery status for your wireless mouse and keyboard in one Windows tray icon.**

`Windows` · `Python 3.10+` · `Tkinter + ctypes`

[Quick start](#quick-start) · [Features](#features) · [Compatibility](#compatibility) · [Calibration](#hid-diagnostics-and-calibration)

## Quick start

1. Install Python 3.10 or later with Tkinter support.
2. Extract the source ZIP or clone the repository.
3. Double-click `start.pyw`, or run `python start.pyw` in the project folder.

If Windows puts Chargeview under the **^** overflow arrow, drag its icon next to the clock.

## Features

- **One tray icon.** The mouse and keyboard have independent liquid fills and battery colors.
- **Two device cards.** See battery levels, estimated runtime, and live Rapoo DPI and polling rate. Use **Open Rapoo Web Hub** for mouse configuration.
- **Settings.** Use the gear beside Refresh to change startup and refresh preferences, open Windows tray settings, or access HID calibration.
- **Adjustable refresh.** Select 30s, 1min, 2min, 5min, or 10min. The default is 1min.

| Tray action | What opens |
| --- | --- |
| Hover | Device names, battery percentages, and estimates when available |
| Left-click | Device panel with the mouse on the left and keyboard on the right |
| Right-click | Compact battery menu and app controls |

Closing either popup leaves monitoring active. Use **Exit Chargeview** to stop the app.

## Compatibility

| Device | Connection or protocol | Verification |
| --- | --- | --- |
| Rapoo VT3 V2 | 2.4 GHz USB receiver `24AE:1462` | Battery, charging, active DPI slot, X/Y DPI, and polling rate verified on hardware. |
| WOBKEY Crush80 | Bluetooth LE | Shows the percentage reported to Windows while connected. Hides it when disconnected. |
| WOBKEY Crush80 | 2.4 GHz USB receiver `320F:5088` | Manual HID calibration is available. The receiver's battery protocol is still unverified. |

A dash means no percentage is available. After a missed reading, Chargeview marks any previously reported value as **Last known**.

## Reading the battery indicators

| Color | Meaning |
| --- | --- |
| Green | 60–100% |
| Yellow | 30–59% |
| Red | 0–29% |
| Blue | Charging |

**Time remaining** uses observed discharge and appears after at least 30 minutes of readings and a three-percentage-point drop. **Time to full** uses observed charging and appears after at least five minutes of readings and a two-point gain. While Chargeview is collecting data, the card and hover tooltip show **Estimating…**. The estimate replaces that label when it is ready. Both can change with actual usage and charge rate.

## HID diagnostics and calibration

Open **Settings → HID calibration**, double-click `debug.cmd`, or run:

```powershell
python start.pyw --debug
```

Select the keyboard interface and choose **Calibrate Feature** or **Calibrate Output → Input**. Use a battery report verified for your device and firmware. Enter the report ID or request, the expected response prefix if applicable, and the zero-based byte offset for the percentage. Save the calibration and refresh the tray.

## Source layout

```text
start.pyw                 Windows launcher
debug.cmd                 Open HID diagnostics
chargeview/
  app.py                  App lifecycle and battery refresh
  battery_estimates.py    Discharge and charging estimates
  settings.py             Local preferences and battery history
  windows_startup.py      Windows Startup shortcut
  hardware/
    bluetooth_battery.py  Crush80 battery via Windows Bluetooth LE
    windows_hid.py        Windows HID transport
    rapoo.py              Rapoo onboard settings
  ui/
    battery_card.py       Device battery card
    device_popup.py       Device popup and tray menu
    diagnostics.py       HID calibration and report tools
    popup_art.py         Scalable graphics
    theme.py             Shared UI colors and text styles
    windows_tray.py      Native tray icon and hover tooltip
```

Chargeview uses the Python standard library. Settings and battery history stay under `%LOCALAPPDATA%\DeskCharge`, a path retained for compatibility with earlier versions.

## Releases

Run `Chargeview.exe` for the standalone Windows release. The Crush80 battery reading is supported over Bluetooth LE.

## Credits and licensing

- [FerrisPulse](https://github.com/Ferris-echo/FerrisPulse) and [ClickSync](https://github.com/Nuitfanee/ClickSync) provided Rapoo protocol references.
- [Rapoo Web Hub](https://hub.rapoo.com/home) provided the active-profile register layout reference.
- [Voltide](https://github.com/sdparklab/Voltide) inspired the battery panel and tray menu.
- [2.4G-battery-viewer](https://github.com/yszyszysz233/2.4G-battery-viewer) provided a HID diagnostics reference.

See [THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt) for the retained rapoo-tray notice. A license for the original Chargeview source has yet to be selected.
