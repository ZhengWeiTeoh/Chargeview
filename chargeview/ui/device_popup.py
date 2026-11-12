import ctypes as C
from ctypes import wintypes as W
import tkinter as tk
from time import monotonic
import os
import subprocess
import webbrowser

from chargeview import APP_NAME, INTERVALS, NAMES, windows_startup as startup
from chargeview.ui.battery_card import Card
from chargeview.ui.theme import ACCENT, BG, CARD, FG, MUTED, label
from chargeview.ui.windows_tray import battery_color
from chargeview.ui.popup_art import action_art, meter_art, switch_art
from chargeview.hardware import windows_hid as hid
from chargeview.hardware import rapoo

WEB_HUB = "https://hub.rapoo.com/home"


def work_area():
    rect = W.RECT()
    hid.bind(hid.user, "SystemParametersInfoW", W.BOOL, W.UINT, W.UINT, hid.P, W.UINT)(
        0x30, 0, C.byref(rect), 0)
    return rect


def round_widget(widget, radius, toplevel=False):
    ancestor = hid.bind(hid.user, "GetAncestor", W.HWND, W.HWND, W.UINT)
    bounds_for = hid.bind(hid.user, "GetWindowRect", W.BOOL, W.HWND, hid.P)
    create = hid.bind(hid.gdi, "CreateRoundRectRgn", W.HANDLE, C.c_int, C.c_int,
                      C.c_int, C.c_int, C.c_int, C.c_int)
    assign = hid.bind(hid.user, "SetWindowRgn", C.c_int, W.HWND, W.HANDLE, W.BOOL)
    release = hid.bind(hid.gdi, "DeleteObject", W.BOOL, W.HANDLE)
    applied = None

    def update(force=False):
        nonlocal applied
        if not widget.winfo_exists():
            return
        hwnd = widget.winfo_id()
        if toplevel:
            hwnd = ancestor(hwnd, 2)
        bounds = W.RECT()
        if not hwnd or not bounds_for(hwnd, C.byref(bounds)):
            return
        width, height = bounds.right-bounds.left, bounds.bottom-bounds.top
        key = hwnd, width, height
        if min(width, height) < 2 or (key == applied and not force):
            return
        diameter = min(radius*2, width, height)
        region = create(0, 0, width, height, diameter, diameter)
        if region:
            if assign(hwnd, region, True):
                applied = key
            else:
                release(region)

    def schedule(event):
        if event.widget is widget:
            widget.after_idle(update)

    widget.bind("<Map>", schedule, add="+")
    widget.bind("<Configure>", schedule, add="+")
    if toplevel:
        widget.apply_rounded_region = update


class PopupFade:
    def __init__(self, panel, window):
        self.window = window
        self.animations = panel.popup_animations
        self.job = None
        self.opacity = 0.0
        self.closing = False
        window.bind("<Destroy>", self.destroyed, add="+")

    def destroyed(self, event):
        if event.widget is self.window:
            self.cancel()

    def cancel(self):
        if self.job is not None:
            self.window.after_cancel(self.job)
            self.job = None
        self.animations.discard(self.window)

    def show(self):
        self.closing = False
        self.window.attributes("-alpha", self.opacity)
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()
        self.fade_to(1.0, .16)

    def close(self, after=None):
        if self.closing:
            return
        self.closing = True

        def done():
            self.window.destroy()
            if after:
                after()

        self.fade_to(0.0, .11, done)

    def fade_to(self, end, duration, done=None):
        self.cancel()
        origin, started = self.opacity, monotonic()
        self.animations.add(self.window)

        def step():
            self.job = None
            progress = min(1.0, (monotonic()-started)/duration)
            eased = 1 - (1-progress)**3 if end else progress**2
            self.opacity = origin + (end-origin)*eased
            try:
                self.window.attributes("-alpha", self.opacity)
                self.window.apply_rounded_region(force=True)
            except tk.TclError:
                self.opacity = end
                progress = 1.0
            if progress < 1.0:
                self.job = self.window.after(15, step)
            else:
                self.animations.discard(self.window)
                if done:
                    done()

        step()


def icon_button(parent, scale, kind, command):
    background, hover = parent.cget("bg"), "#443a60"
    size = scale(21)
    images = [tk.PhotoImage(master=parent, data=action_art(size, kind, color), format="PPM")
              for color in (background, hover)]
    title = {"refresh": "Refresh battery readings", "close": "Close popup", "settings": "Settings"}[kind]
    button = tk.Button(parent, image=images[0], text=title, command=command,
                       bg=background, activebackground=hover, relief="flat", bd=0,
                       highlightthickness=1, highlightbackground=background,
                       highlightcolor="#ad9bd3", takefocus=True, cursor="hand2",
                       padx=scale(5), pady=scale(4))
    button.images = images
    tip = None

    def leave(_=None):
        nonlocal tip
        if tip is not None:
            tip.destroy()
            tip = None
        if button.winfo_exists():
            button.config(image=images[0], bg=background)

    def enter(_):
        nonlocal tip
        if tip is not None:
            return
        button.config(image=images[1], bg=hover)
        tip = tk.Toplevel(button, bg="#292437")
        tip.withdraw()
        tip.overrideredirect(True)
        tip.attributes("-topmost", True)
        label(tip, title, 9, FG, "#292437").pack(padx=scale(7), pady=scale(3))
        tip.update_idletasks()
        area = work_area()
        x = max(area.left, min(button.winfo_rootx(), area.right-tip.winfo_reqwidth()))
        y = button.winfo_rooty()-tip.winfo_reqheight()-scale(4)
        tip.geometry(f"+{x}+{max(area.top, y)}")
        tip.deiconify()

    button.bind("<Enter>", enter)
    button.bind("<Leave>", leave)
    button.bind("<Destroy>", lambda _: tip.destroy() if tip is not None and tip.winfo_exists() else None)
    button.bind("<Return>", lambda _: button.invoke())
    round_widget(button, scale(8))
    return button


def startup_switch(panel, parent, px, dark):
    startup_row = tk.Frame(parent, bg=dark, padx=px(13), pady=px(8))
    startup_row.pack(fill="x")
    label(startup_row, "Start with Windows", 10, FG, dark).pack(side="left")
    panel.read_startup()
    toggle = tk.Button(startup_row, command=lambda: set_startup(), bg=dark,
                       activebackground=dark, relief="flat", bd=0, cursor="hand2",
                       highlightthickness=1, highlightbackground=dark,
                       highlightcolor="#ad9bd3", takefocus=True)
    toggle.pack(side="right")
    toggle.bind("<Return>", lambda _: toggle.invoke())
    toggle.images = {on: tk.PhotoImage(master=parent, format="PPM",
                                       data=switch_art(px(38), px(20), dark, on))
                     for on in (False, True)}

    def show_startup():
        panel.read_startup()
        on = panel.auto.get()
        toggle.config(image=toggle.images[on],
                      text="Start with Windows: On" if on else "Start with Windows: Off")

    def set_startup():
        panel.auto.set(not panel.auto.get())
        panel.toggle_startup()
        show_startup()

    show_startup()
    return show_startup


def show_device_status(panel, settings=False):
    current = getattr(panel, "device_window", None)
    if current is not None and current.winfo_exists():
        current.show_settings(settings)
        if current.fade.closing:
            current.fade.show()
        else:
            current.lift()
            current.focus_force()
        return

    window = panel.device_window = tk.Toplevel(panel.root, bg=BG)
    window.withdraw()
    window.title(APP_NAME)
    window.resizable(False, False)
    window.overrideredirect(True)
    fade = window.fade = PopupFade(panel, window)
    window.bind("<Escape>", lambda _: fade.close())
    scale = panel.scale
    round_widget(window, scale(18), toplevel=True)
    backdrop = "#171429"
    shell = tk.Frame(window, bg=backdrop, padx=scale(16), pady=scale(12),
                     highlightbackground="#302849", highlightthickness=1)
    shell.pack(fill="both", expand=True)
    header = tk.Frame(shell, bg=backdrop)
    header.pack(fill="x", pady=(0, scale(12)))
    heading = label(header, APP_NAME.upper(), 17, FG, backdrop, True)
    heading.pack(side="left")
    icon_button(header, scale, "close", fade.close).pack(side="right")
    refresh_button = icon_button(header, scale, "refresh", panel.refresh)
    refresh_button.pack(side="right", padx=scale(5))
    icon_button(header, scale, "settings", lambda: show_settings(not showing_settings)).pack(side="right")

    devices = tk.Frame(shell, bg=backdrop)
    layout = tk.Frame(devices, bg=backdrop)
    layout.pack(fill="both")
    body = tk.Frame(layout, bg=backdrop)
    keyboard = tk.Frame(layout, bg=backdrop)
    for column, side in enumerate((body, keyboard)):
        layout.columnconfigure(column, weight=1, uniform="devices")
        side.grid(row=0, column=column, sticky="nsew", padx=(0, scale(6)) if column == 0 else (scale(6), 0))
    panel.mouse_card = Card(body, "Rapoo VT3 V2", "MOUSE", scale)
    panel.keyboard_card = Card(keyboard, "WOBKEY Crush80", "KEYBOARD", scale)
    for i, card in enumerate((panel.mouse_card, panel.keyboard_card)):
        card.box.pack(fill="x")
        card.render(panel.readings[i])

    live = tk.Frame(devices, bg=CARD, padx=scale(13), pady=scale(9), highlightthickness=1,
                    highlightbackground="#35333d")
    live.pack(fill="x", pady=(scale(9), 0))
    round_widget(live, scale(10))
    panel.button(live, "Open Rapoo Web Hub", lambda: webbrowser.open(WEB_HUB)).pack(
        side="right", padx=(scale(8), 0))
    label(live, "ONBOARD SETUP", 8, ACCENT, CARD, True).pack(anchor="w")
    active = label(live, "Reading active settings…", 11, FG, CARD, True)
    active.pack(fill="x")
    polling = label(live, "", 10, FG, CARD)
    polling.pack(fill="x")
    status = label(live, "", 9, MUTED, CARD)
    status.pack(fill="x")
    preferences = tk.Frame(shell, bg=backdrop)
    choices = tk.Frame(preferences, bg=backdrop)
    choices.pack(fill="x", pady=(0, scale(8)))
    label(choices, "Refresh interval", 9, MUTED, backdrop).pack(side="left", padx=(0, scale(7)))
    quick = []
    for caption, seconds in INTERVALS.items():
        option = tk.Radiobutton(choices, text=caption, variable=panel.rate, value=seconds,
                                command=panel.change_interval, bg=backdrop, fg=MUTED,
                                activebackground=backdrop, activeforeground=FG, selectcolor="#242031",
                                highlightthickness=0, bd=0, cursor="hand2", font=("Segoe UI", 9))
        option.pack(side="left", padx=scale(2))
        quick.append((seconds, option))

    def display_interval(*_):
        for value, option in quick:
            option.config(fg="#87dfa7" if value == panel.rate.get() else MUTED)

    trace = panel.rate.trace_add("write", display_interval)
    window.bind("<Destroy>", lambda event: panel.rate.trace_remove("write", trace)
                if event.widget is window else None, add="+")
    display_interval()
    showing_settings = False
    refresh_startup = startup_switch(panel, preferences, scale, backdrop)
    panel.button(preferences, "Windows tray settings",
                 lambda: panel.open_windows("ms-settings:taskbar")).pack(fill="x", pady=(scale(6), 0))
    panel.button(preferences, "HID calibration", lambda: subprocess.Popen(
        startup.launch_command("--debug"), cwd=startup.ROOT,
        env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"})).pack(fill="x", pady=(scale(6), 0))
    panel.button(preferences, "Back to devices", lambda: show_settings(False)).pack(
        fill="x", pady=(scale(12), 0))

    def show_settings(open_settings):
        nonlocal showing_settings
        showing_settings = open_settings
        hidden, visible = (devices, preferences) if open_settings else (preferences, devices)
        hidden.pack_forget()
        visible.pack(fill="x")
        heading.config(text="SETTINGS" if open_settings else APP_NAME.upper())
        if open_settings:
            refresh_startup()

    window.show_settings = show_settings
    show_settings(settings)

    def read_setup():
        if showing_settings or not window.winfo_exists() or not window.winfo_viewable():
            return

        def done(state, error):
            if showing_settings or not window.winfo_exists() or not window.winfo_viewable():
                return
            if error:
                active.config(text="Onboard setup unavailable")
                polling.config(text="")
                status.config(text="Wake the mouse to refresh.")
                return
            stage = state["stage"]
            x, y = state["dpi"][stage]
            rate = f'{state["rate"]} Hz' if state["rate"] else "Polling rate unavailable"
            active.config(text=f"Slot {stage + 1}  ·  {x} × {y} DPI")
            polling.config(text=f"Polling rate: {rate}" if state["rate"] else rate)
            status.config(text="Live from mouse")

        panel.control_worker.start(
            lambda stop: rapoo.snapshot(hid.interfaces(), stop), done)

    def visibility(event):
        if event.widget is not window:
            return
        if event.type == tk.EventType.Map:
            # The window can map before the nested device cards are viewable.
            panel.tray.watch_settings(read_setup)
            window.after_idle(read_setup)
        else:
            panel.tray.watch_settings(None)

    for sequence in ("<Map>", "<Unmap>", "<Destroy>"):
        window.bind(sequence, visibility)
    get_ancestor = hid.bind(hid.user, "GetAncestor", W.HWND, W.HWND, W.UINT)
    get_bounds = hid.bind(hid.user, "GetWindowRect", W.BOOL, W.HWND, hid.P)
    move = hid.bind(hid.user, "SetWindowPos", W.BOOL, W.HWND, W.HWND,
                    C.c_int, C.c_int, C.c_int, C.c_int, W.UINT)
    last_size = None

    def position(event):
        nonlocal last_size
        if event.widget is not window or not window.winfo_viewable():
            return
        size = event.width, event.height
        if size == last_size:
            return
        hwnd = get_ancestor(window.winfo_id(), 2)
        bounds = W.RECT()
        if not hwnd or not get_bounds(hwnd, C.byref(bounds)):
            return
        last_size = size
        area, margin = work_area(), scale(12)
        x = max(area.left, area.right - (bounds.right - bounds.left) - margin)
        y = max(area.top, area.bottom - (bounds.bottom - bounds.top) - margin)
        if (x, y) != (bounds.left, bounds.top):
            move(hwnd, None, x, y, 0, 0, 0x0015)  # NOSIZE | NOZORDER | NOACTIVATE

    window.bind("<Configure>", position)
    fade.show()

def show_tray_menu(panel):
    current = getattr(panel, "tray_menu_window", None)
    if current is not None and current.winfo_exists():
        current.destroy()

    px = panel.scale
    dark = "#131217"
    divider = "#282631"
    window = panel.tray_menu_window = tk.Toplevel(panel.root, bg=dark,
                                                 highlightbackground="#534a6a", highlightthickness=1)
    window.withdraw()
    window.overrideredirect(True)
    window.attributes("-topmost", True)
    round_widget(window, px(14), toplevel=True)
    fade = window.fade = PopupFade(panel, window)
    window.bind("<Escape>", lambda _: fade.close())
    header = tk.Frame(window, bg="#302650", padx=px(13), pady=px(5))
    header.pack(fill="x")
    label(header, APP_NAME.upper(), 9, FG, "#302650", True).pack(side="left")
    icon_button(header, px, "close", fade.close).pack(side="right")
    icon_button(header, px, "refresh", lambda: fade.close(panel.refresh)).pack(side="right")
    icon_button(header, px, "settings", lambda: fade.close(
        lambda: show_device_status(panel, settings=True))).pack(side="right", padx=px(6))

    def separate():
        tk.Frame(window, bg=divider, height=1).pack(fill="x")

    def open_status(_):
        fade.close(panel.device_status)

    for name, reading in zip(NAMES, panel.readings):
        separate()
        row = tk.Frame(window, bg=dark, padx=px(13), pady=px(10), cursor="hand2")
        row.pack(fill="x")
        row.columnconfigure(0, weight=1)
        color = MUTED if reading.stale else battery_color(reading.level, reading.charging)
        name_label = label(row, name, 11, MUTED if reading.stale else FG, dark)
        name_label.grid(row=0, column=0, sticky="w", padx=(0, px(12)))
        width, height = px(72), px(9)
        image = tk.PhotoImage(master=row, data=meter_art(width, height, dark, color, reading.level),
                              format="PPM")
        bar = tk.Label(row, image=image, bg=dark, bd=0)
        bar.image = image
        bar.grid(row=0, column=1, padx=(0, px(10)))
        value = label(row, "—" if reading.level is None else f"{reading.level}%", 12, color, dark, True)
        value.config(width=5, anchor="e")
        value.grid(row=0, column=2, sticky="e")
        for widget in (row, name_label, bar, value):
            widget.bind("<ButtonRelease-1>", open_status)

    separate()
    exit_button = tk.Button(window, text=f"Exit {APP_NAME}", command=lambda: fade.close(panel.quit),
                            bg=dark, fg="#ef9aa6", activebackground="#392731",
                            activeforeground=FG, relief="flat", bd=0,
                            anchor="w", padx=px(13), pady=px(8), cursor="hand2")
    exit_button.pack(fill="x")

    def dismiss(_):
        def check_focus():
            if window.winfo_exists():
                focus = window.focus_get()
                if focus is None or focus.winfo_toplevel() is not window:
                    fade.close()
        window.after_idle(check_focus)

    window.bind("<FocusOut>", dismiss)
    window.update_idletasks()
    area = work_area()
    width, height = window.winfo_reqwidth(), window.winfo_reqheight()
    pointer_x, pointer_y = window.winfo_pointerxy()
    x = max(area.left, min(pointer_x-width//2, area.right-width))
    y = max(area.top, min(pointer_y-height-px(5), area.bottom-height))
    window.geometry(f"+{x}+{y}")
    fade.show()
