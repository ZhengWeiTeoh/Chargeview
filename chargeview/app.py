import _tkinter
import argparse
import ctypes as C
from ctypes import wintypes as W
from datetime import datetime, timezone
from types import SimpleNamespace
import queue
import threading
import tkinter as tk
from tkinter import messagebox

from chargeview import APP_NAME, INTERVALS, NAMES, battery_estimates
from chargeview.hardware.bluetooth_battery import crush80_battery
from chargeview.hardware import windows_hid as hid
from chargeview import settings, windows_startup as startup
from chargeview.ui import windows_tray as native
from chargeview.ui.theme import FG

def dpi_aware():
    try:
        if hid.bind(hid.user, "SetProcessDpiAwarenessContext", W.BOOL, hid.P)(hid.P(-4)):
            return
    except AttributeError:
        pass
    hid.user.SetProcessDPIAware()


def mouse_read(paths, stop):
    path = hid.rapoo_path(paths)
    source = "Rapoo HID telemetry"
    if not path:
        return None, "Receiver disconnected", source, None
    value = hid.read_rapoo(path, stop)
    if value is None:
        return None, "No fresh report · move the mouse", source, None
    level, charging, x, y, _ = value
    return level, "Charging" if charging else "Connected", source, (x, y)


class Worker:
    def __init__(self, root, debug):
        self.root = root
        self.debug = debug
        self.stop = hid.event(None, True, False, None)
        if not self.stop:
            raise C.WinError(C.get_last_error())
        self.thread = None
        self.results = queue.Queue()
        self.closed = False

    def start(self, action, done):
        if self.closed or self.thread is not None:
            return False

        def run():
            try:
                self.results.put((action(self.stop), None))
            except Exception as error:
                self.results.put((None, error))

        def pump():
            if self.closed:
                return
            try:
                value, error = self.results.get_nowait()
            except queue.Empty:
                self.root.after(100, pump)
                return
            self.thread.join()
            self.thread = None
            if self.debug and error:
                print(error, flush=True)
            done(value, error)

        self.thread = threading.Thread(target=run, name="HID worker")
        self.thread.start()
        self.root.after(100, pump)
        return True

    def close(self):
        if self.closed:
            return
        self.closed = True
        hid.set_event(self.stop)
        if self.thread:
            self.thread.join()
        hid.close(self.stop)


class Panel:
    def __init__(self, root, args):
        self.root = root
        self.args = args
        self.config = settings.load()
        self.worker = Worker(root, args.debug)
        self.control_worker = Worker(root, args.debug)
        self.refresh_queued = False
        self.popup_animations = set()
        self.battery_cache = settings.load(settings.BATTERY_CACHE)
        self.scale = lambda n: round(self.root.winfo_fpixels("1i") * n / 96)
        self.readings = [SimpleNamespace(level=None, time=None, runtime=None, charging=False) for _ in NAMES]
        self.auto = tk.BooleanVar(root)
        self.rate = tk.IntVar(root, value=self.config.get("interval", 60))
        if self.rate.get() not in INTERVALS.values():
            self.rate.set(60)
        self.tray_actions = queue.SimpleQueue()
        self.tray = native.Tray(self.refresh, self.show_menu, self.quit, self.defer_tray_action, self.device_status)
        self.tray.interval(self.rate.get())
        for index, name in enumerate(NAMES):
            cached = self.battery_cache.get(name)
            level, stamp = None, None
            if isinstance(cached, dict):
                try:
                    candidate = cached["level"]
                    time = datetime.fromisoformat(cached["updated"])
                    if type(candidate) is int and 0 <= candidate <= 100 and time.tzinfo:
                        level, stamp = candidate, time
                except (TypeError, ValueError, KeyError):
                    pass
            source = "Rapoo HID telemetry" if index == 0 else "Calibrated HID protocol"
            runtime = battery_estimates.cached_text(cached) if stamp else None
            self.update_battery_icon(index, level if index == 0 else None,
                                     "Last known" if stamp and index == 0 else "Waiting for data",
                                     source, stamp, runtime)
        self.update_tray()
        self.refresh()

    def button(self, parent, title, action):
        from chargeview.ui.device_popup import round_widget
        button = tk.Button(parent, text=title, command=action, font=("Segoe UI", 9, "bold"),
                           bg="#2c2a34", fg=FG, activebackground="#49303c", activeforeground=FG,
                           relief="flat", bd=0, padx=self.scale(9), pady=self.scale(5), cursor="hand2")
        round_widget(button, self.scale(7))
        return button

    def open_windows(self, uri):
        import os
        os.startfile(uri)

    def defer_tray_action(self, action, *args):
        # The Win32 window procedure never calls Tk, even to schedule a callback.
        self.tray_actions.put((action, args))

    def run(self):
        wait_for_messages = hid.bind(hid.user, "MsgWaitForMultipleObjectsEx",
                                     W.DWORD, W.DWORD, hid.P, W.DWORD, W.DWORD, W.DWORD)
        while not self.worker.closed:
            while self.root.tk.dooneevent(_tkinter.DONT_WAIT):
                if self.worker.closed:
                    return
            while not self.worker.closed:
                try:
                    action, args = self.tray_actions.get_nowait()
                except queue.Empty:
                    break
                action(*args)
            if self.worker.closed:
                return
            active = (self.worker.thread is not None or self.control_worker.thread is not None
                      or self.root.winfo_viewable())
            # Hidden and idle, wait for Explorer messages or the native refresh timer.
            # Only a pending Tk worker/animation needs a bounded wait.
            timeout = 15 if self.popup_animations else 30 if active else 0xFFFFFFFF
            wait_for_messages(0, None, timeout, 0x04FF, 0x0004)

    def show_menu(self):
        from chargeview.ui.device_popup import show_tray_menu
        show_tray_menu(self)

    def read_startup(self):
        try:
            self.auto.set(startup.enabled())
        except OSError:
            self.auto.set(False)

    def toggle_startup(self):
        try:
            startup.set_enabled(self.auto.get())
        except OSError as error:
            messagebox.showerror(APP_NAME, str(error), parent=self.root)
        self.read_startup()

    def change_interval(self):
        seconds = self.rate.get()
        self.tray.interval(seconds)
        try:
            config = settings.load()
            config["interval"] = seconds
            settings.save(config)
        except OSError as error:
            messagebox.showerror(APP_NAME, str(error), parent=self.root)

    def refresh(self):
        def action(stop):
            paths = hid.interfaces()
            readings = []
            try:
                readings.append(mouse_read(paths, stop))
            except OSError as error:
                readings.append((None, f"Receiver error {error.winerror}", "Rapoo HID telemetry", None))
            profile = settings.load()
            calibrated_path = (profile.get("keyboard") or {}).get("path", "").lower()
            candidates = [hid.describe(path) for path in paths
                          if "vid_320f&pid_50" in path.lower() or path.lower() == calibrated_path]
            try:
                readings.append((*settings.keyboard_battery(candidates, profile, stop), None))
            except (OSError, ValueError, KeyError) as error:
                readings.append((None, str(error), "Calibrated HID protocol", None))
            if readings[1][0] is None:
                bluetooth_level, connected = crush80_battery()
                if connected is not None:
                    status = ("Connected" if bluetooth_level is not None else "Battery unavailable") if connected else "Disconnected"
                    readings[1] = (bluetooth_level, status, "Windows Bluetooth LE", None)
            return readings

        if not self.worker.start(action, self.refreshed):
            self.refresh_queued = True

    def update_battery_icon(self, index, level, status, source, recorded_at=None, runtime=None):
        reading = self.readings[index]
        charging = status == "Charging"
        if index == 1 and level is None:
            reading.level = reading.time = reading.runtime = None
        elif level is not None:
            reading.level = level
            reading.time = recorded_at or datetime.now(timezone.utc)
            reading.runtime = runtime
        elif charging:
            reading.level = reading.time = reading.runtime = None
        elif reading.charging:
            reading.runtime = None
        stale = reading.level is not None and (level is None or recorded_at is not None)
        reading.stale, reading.charging = stale, charging
        reading.status, reading.source = status, source
        if reading.level is not None and not stale and not reading.runtime:
            reading.runtime = "Estimating…"
        stamp = reading.time
        runtime = reading.runtime
        value = "—" if reading.level is None else f"{reading.level}%"
        detail_card = getattr(self, "mouse_card" if index == 0 else "keyboard_card", None)
        if detail_card is not None and detail_card.box.winfo_exists():
            detail_card.render(reading)
        return value, stamp

    def update_tray(self):
        devices, lines = [], []
        for name, reading in zip(NAMES, self.readings):
            devices.append((reading.level, native.battery_color(reading.level, reading.charging)))
            if reading.status in ("Disconnected", "Keyboard disconnected", "Calibrated interface disconnected"):
                lines.append(f"{name}: Disconnected")
                continue
            value = "—" if reading.level is None else f"{reading.level}%"
            details = []
            if reading.level is None:
                details.append("Charging" if reading.charging else "Unavailable")
            else:
                if reading.charging:
                    details.append("Charging")
                if not reading.stale:
                    details.append(reading.runtime or "Estimating…")
            if reading.stale:
                details.append("Last known")
            lines.append(f"{name}: {value} · {' · '.join(details)}")
        self.tray.update(tuple(devices), "\n".join(lines))

    def refreshed(self, readings, error):
        cache_changed = False
        if not error:
            for index, (level, status, source, dpi) in enumerate(readings):
                name = NAMES[index]
                runtime = None
                if level is not None:
                    observed = datetime.now(timezone.utc)
                    charging = status == "Charging"
                    history = battery_estimates.update_history(
                        self.battery_cache.get(name), observed, level, charging, self.rate.get())
                    self.battery_cache[name] = {
                        "level": level, "updated": observed.isoformat(), "runtime": history,
                        "charging": charging}
                    if charging:
                        runtime = battery_estimates.time_to_full(level, history)
                    else:
                        runtime = battery_estimates.remaining_text(level, history)
                    cache_changed = True
                value, stamp = self.update_battery_icon(index, level, status, source, runtime=runtime)
                if level is None and status == "Charging" and name in self.battery_cache:
                    del self.battery_cache[name]
                    cache_changed = True
                if self.args.debug:
                    print(f"{name}: {value} | {source} | {status}", flush=True)
        else:
            for index, card in enumerate(self.readings):
                if card.level is not None:
                    source = "Rapoo HID telemetry" if index == 0 else "Calibrated HID protocol"
                    self.update_battery_icon(index, None, "Refresh failed", source)
        if cache_changed:
            try:
                settings.save(self.battery_cache, settings.BATTERY_CACHE)
            except OSError as cache_error:
                if self.args.debug:
                    print(cache_error, flush=True)
        self.update_tray()
        self.after_job()

    def after_job(self):
        if self.refresh_queued:
            self.refresh_queued = False
            self.refresh()

    def device_status(self):
        from chargeview.ui.device_popup import show_device_status
        show_device_status(self)

    def quit(self):
        if self.worker.closed:
            return
        self.root.withdraw()
        self.tray.close()
        self.worker.close()
        self.control_worker.close()
        self.root.quit()


def main():
    parser = argparse.ArgumentParser()
    for name in ("tray", "debug", "setup", "stop", "probe"):
        parser.add_argument("--" + name, action="store_true")
    parser.add_argument("--startup-tray", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.startup_tray:
        if not startup.enabled():
            return
        args.tray = True
    if args.setup:
        startup.setup_entries()
        if args.debug:
            print("Desktop links and startup entry are ready.", flush=True)
        return
    if args.stop:
        existing = native.find_window(native.CLASS, native.CLASS)
        if existing:
            native.post(existing, native.WM_STOP, 0, 0)
        return
    if args.probe and args.debug:
        paths = hid.interfaces()
        print("HID interfaces:", len(paths), flush=True)
        stop = hid.event(None, True, False, None)
        try:
            print("Mouse:", mouse_read(paths, stop), flush=True)
            print("DPI:", hid.rapoo_dpi(paths, stop), flush=True)
        finally:
            hid.close(stop)
        return
    if args.debug:
        from chargeview.ui.diagnostics import show_debug
        dpi_aware()
        root = tk.Tk()
        show_debug(root, Worker(root, True))
        root.mainloop()
        return

    create_mutex = hid.bind(hid.kernel, "CreateMutexW", W.HANDLE, hid.P, W.BOOL, W.LPCWSTR)
    mutex = create_mutex(None, False, r"Local\DeskCharge.Notification.2")
    if not mutex:
        raise C.WinError(C.get_last_error())
    if C.get_last_error() == 183:
        hid.close(mutex)
        existing = native.find_window(native.CLASS, native.CLASS)
        if existing and not args.tray:
            native.post(existing, native.WM_SHOW, 0, 0)
        return
    try:
        dpi_aware()
        root = tk.Tk()
        root.withdraw()
        panel = Panel(root, args)
        if not args.tray:
            panel.device_status()
        try:
            panel.run()
        finally:
            panel.quit()
            root.destroy()
    finally:
        hid.close(mutex)



