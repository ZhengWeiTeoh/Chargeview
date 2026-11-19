# Chargeview

A compact Windows tray app for Rapoo VT3 V2 and WOBKEY Crush80 battery status.

Version 2 uses C#, WinForms, Windows HID APIs, and the Windows Bluetooth API. The executable uses the .NET Framework installed with Windows 10 and Windows 11. Python is unnecessary. The release build is approximately 167 KB.

## Run

Download `Chargeview.Native.exe` from Releases and open it. When building from source, the executable is written to `dist/Chargeview.Native.exe`.

- Left-click the tray icon to open the two device cards.
- Right-click for refresh, settings, and exit.
- Hover for device names, battery percentages, and estimates.
- Close the popup to keep monitoring in the tray.
- Enable **Start with Windows** in Settings for a per-user sign-in task. Windows Task Manager can disable its Startup folder entry.

Version 2 has its own startup entry, single-instance lock, and preferences folder. When switching from the Python version, turn off its **Start with Windows** setting and exit it, then enable startup in version 2.

## Features

- Independent mouse and keyboard battery fills in one tray icon.
- Green at 60–100%, yellow at 30–59%, red below 30%, blue while charging.
- Crush80 Bluetooth connection checks without starting PowerShell.
- Disconnected keyboard percentages are hidden.
- Rapoo onboard DPI slot, X/Y DPI, and polling rate. Onboard settings refresh while the device panel is open.
- Rapoo Web Hub link.
- Refresh intervals of 30 seconds, 1 minute, 2 minutes, 5 minutes, or 10 minutes.
- Battery runtime and charging estimates, learned from observed readings.
- Reuses compatible battery history from the Python version on its first run. It stores its own preferences and learned rates under `%LOCALAPPDATA%\ChargeviewNative`.
- HID interface inventory and read-only Feature Report inspection.

## Compatibility

| Device | Connection | Hardware verification |
| --- | --- | --- |
| Rapoo VT3 V2 | 2.4 GHz receiver | Battery, active DPI slot, X/Y DPI, and polling rate verified. |
| WOBKEY Crush80 | Bluetooth LE | Connected battery percentage and disconnected behavior verified. |

The Crush80 battery query over its 2.4 GHz receiver remains unverified.

HID diagnostics list device interfaces and read selected Feature Reports. Sending arbitrary test commands and saving custom battery-reading rules are available in the earlier Python implementation. Runtime and charging estimates depend on observed battery changes, and their long-term accuracy is still being evaluated.

The native interface redraws the Python version's lightning battery cards, purple panels, header icons, settings slider, refresh options, tray artwork, right-click menu, and fade animation using Windows graphics APIs.

Text is rasterized at the display's physical pixel size. Card artwork and header icons are drawn without fractional resampling, and tray artwork uses the taskbar's icon size.

## Build

Run `powershell -NoProfile -ExecutionPolicy Bypass -File build.ps1` on 64-bit Windows. The script uses the Windows .NET Framework compiler and Windows Runtime metadata installed with Windows. It writes `dist/Chargeview.Native.exe`.

The default build targets 32-bit Windows processes to reduce memory use on 64-bit Windows. To build a 64-bit executable, pass `-Platform x64`. Popup artwork is released when the panel closes and regenerated when needed.

No packages are installed by the build script.

## Source

- `src/Program.cs` — tray, device cards, settings, and app lifecycle
- `src/Appearance.cs` — original Chargeview artwork and popup layouts
- `src/Hardware.cs` — HID enumeration, mouse telemetry, and onboard settings
- `src/BluetoothBattery.cs` — Bluetooth connection and battery reading
- `src/Battery.cs` — preferences and battery estimates
- `src/Startup.cs` — startup shortcut and sign-in task
- `src/Diagnostics.cs` — HID inventory and Feature Report inspection
- `src/TrayTooltip.cs` — extended tray tooltip
- `src/SelfTest.cs` — explicit hardware verification command

## Credits

Rapoo register layouts follow the same protocol research used by the Python Chargeview project, including FerrisPulse, ClickSync, and Rapoo Web Hub. See `THIRD-PARTY-NOTICES.txt`.
