import ctypes as C
from ctypes import wintypes as W
from uuid import UUID
from pathlib import Path
from math import sin, tau
import sys
from chargeview.hardware.windows_hid import bind, kernel, user, shell, gdi, P, UP

LRESULT = C.c_ssize_t
CALLBACK = C.WINFUNCTYPE(LRESULT, W.HWND, W.UINT, UP, LRESULT)
WM_TRAY = 0x8001
WM_STOP = 0x8002
WM_SHOW = 0x8003
ICON_RETRY_TIMER = 3
ICON_RETRY_LIMIT = 60


class WindowClass(C.Structure):
    _fields_ = [("style", W.UINT), ("proc", CALLBACK), ("cls_extra", C.c_int),
                ("win_extra", C.c_int), ("instance", W.HINSTANCE), ("icon", W.HICON),
                ("cursor", W.HANDLE), ("brush", W.HBRUSH), ("menu", W.LPCWSTR),
                ("name", W.LPCWSTR)]


class Notify(C.Structure):
    _fields_ = [("size", W.DWORD), ("window", W.HWND), ("id", W.UINT),
                ("flags", W.UINT), ("callback", W.UINT), ("icon", W.HICON),
                ("tip", W.WCHAR * 128), ("state", W.DWORD), ("mask", W.DWORD),
                ("info", W.WCHAR * 256), ("version", W.UINT), ("title", W.WCHAR * 64),
                ("info_flags", W.DWORD), ("guid", C.c_byte * 16), ("balloon", W.HICON)]


class Bitmap(C.Structure):
    _fields_ = [("size", W.DWORD), ("width", W.LONG), ("height", W.LONG),
                ("planes", W.WORD), ("bpp", W.WORD), ("remaining", W.DWORD * 6)]


class IconInfo(C.Structure):
    _fields_ = [("icon", W.BOOL), ("x", W.DWORD), ("y", W.DWORD),
                ("mask", W.HBITMAP), ("color", W.HBITMAP)]


notify = bind(shell, "Shell_NotifyIconW", W.BOOL, W.DWORD, P)
destroy_icon = bind(user, "DestroyIcon", W.BOOL, W.HICON)
create_icon = bind(user, "CreateIconIndirect", W.HICON, P)
dib = bind(gdi, "CreateDIBSection", W.HBITMAP, W.HDC, P, W.UINT, P, W.HANDLE, W.DWORD)
bitmap = bind(gdi, "CreateBitmap", W.HBITMAP, C.c_int, C.c_int, W.UINT, W.UINT, P)
delete = bind(gdi, "DeleteObject", W.BOOL, W.HANDLE)
metrics = bind(user, "GetSystemMetrics", C.c_int, C.c_int)
find_window = bind(user, "FindWindowW", W.HWND, W.LPCWSTR, W.LPCWSTR)
post = bind(user, "PostMessageW", W.BOOL, W.HWND, W.UINT, UP, LRESULT)
set_timer = bind(user, "SetTimer", UP, W.HWND, UP, W.UINT, P)
kill_timer = bind(user, "KillTimer", W.BOOL, W.HWND, UP)
def_proc = bind(user, "DefWindowProcW", LRESULT, W.HWND, W.UINT, UP, LRESULT)
destroy_window = bind(user, "DestroyWindow", W.BOOL, W.HWND)
post_quit = bind(user, "PostQuitMessage", None, C.c_int)
register = bind(user, "RegisterClassW", W.WORD, P)
unregister = bind(user, "UnregisterClassW", W.BOOL, W.LPCWSTR, W.HINSTANCE)
create_window = bind(user, "CreateWindowExW", W.HWND, W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD,
                     C.c_int, C.c_int, C.c_int, C.c_int, W.HWND, W.HMENU, W.HINSTANCE, P)
module_handle = bind(kernel, "GetModuleHandleW", W.HMODULE, W.LPCWSTR)
register_message = bind(user, "RegisterWindowMessageW", W.UINT, W.LPCWSTR)
CLASS = "DeskCharge.NativeTray.2"
FROZEN = getattr(sys, "frozen", False)
ICON_ID = 1
ICON_GUID = UUID("3d2e824e-8384-41c9-b6c8-deebbd311108" if FROZEN
                 else "5bfcf597-8d3c-4f38-8378-cc815cb2d319").bytes_le


def battery_color(level, charging=False):
    if charging:
        return "#67c6ff"
    if level is None:
        return "#a6b4c7"
    return "#71e2ab" if level >= 60 else "#ffcf70" if level >= 30 else "#ff8590"


def tray_icon_size():
    taskbar = find_window("Shell_TrayWnd", None)
    if taskbar:
        try:
            dpi_for_window = bind(user, "GetDpiForWindow", W.UINT, W.HWND)
            metric_for_dpi = bind(user, "GetSystemMetricsForDpi", C.c_int, C.c_int, W.UINT)
            dpi = dpi_for_window(taskbar)
            size = metric_for_dpi(49, dpi) if dpi else 0  # SM_CXSMICON
            if size:
                return size
        except AttributeError:
            pass
    return metrics(49) or 16


def rounded_rect(x, y, box, radius):
    left, top, right, bottom = box
    if not (left <= x < right and top <= y < bottom):
        return False
    dx = max(left + radius - x, x - right + radius, 0)
    dy = max(top + radius - y, y - bottom + radius, 0)
    return dx * dx + dy * dy <= radius * radius


def battery_pixels(size, index, level, color):
    mouse = index == 1
    outer = (.22, .055, .78, .945) if mouse else (.035, .245, .965, .755)
    inset = .064 if mouse else .060
    radius = .26 if mouse else .105
    left, top, right, bottom = outer
    inner = left + inset, top + inset, right - inset, bottom - inset
    fill = bytes.fromhex(color[1:])
    depth = inner[3] - inner[1]
    surface = inner[3] - depth * (level or 0) / 100
    wave = min(.035, surface - inner[1], inner[3] - surface)
    surfaces = [surface + wave * sin(tau * (i + .5) / (size * 4))
                for i in range(size * 4)]
    details = [((.465, .23, .535, .40), .032)] if mouse else [
        ((x, y, x + .098, y + .068), .022)
        for y in (.365, .48) for x in (.16, .35, .55, .74)
    ] + [((.31, .60, .69, .665), .026)]

    def sample(x, y, waterline):
        if not rounded_rect(x, y, outer, radius):
            return None
        if not rounded_rect(x, y, inner, radius - inset):
            return (213, 220, 231)
        for box, corner in details:
            if rounded_rect(x, y, box, corner):
                return (228, 235, 246)
        if level is None:
            if .39 <= x < .61 and .47 <= y < .53:
                return fill
        elif y >= min(waterline, inner[3] - .04):
            if y - waterline < .055:
                return tuple(round(channel * .78 + 255 * .22) for channel in fill)
            shade = 1 - .16 * (y - inner[1]) / depth
            return tuple(round(channel * shade) for channel in fill)
        return (27, 34, 47)

    pixels = []
    # Average premultiplied samples so translucent edges blend into the taskbar.
    for y in range(size):
        for x in range(size):
            alpha = red = green = blue = 0
            for dy in range(4):
                for dx in range(4):
                    col = x * 4 + dx
                    rgb = sample((col + .5) / (size * 4),
                                 (y + (dy + .5) / 4) / size, surfaces[col])
                    if rgb is not None:
                        alpha += 255
                        red += rgb[0]
                        green += rgb[1]
                        blue += rgb[2]
            pixels.append((round(alpha / 16) << 24) | (round(red / 16) << 16)
                          | (round(green / 16) << 8) | round(blue / 16))
    return pixels


def combined_pixels(size, devices):
    pixels = [0] * (size*size)
    # Place the mouse above the keyboard, with independent battery fills.
    for index, (level, color) in enumerate(devices, 1):
        if index == 1:
            tile, left, top = round(size*.69), round(size*.36), -round(size*.03)
        else:
            tile, left, top = size, 0, round(size*.22)
        art = battery_pixels(tile, index, level, color)
        for y in range(max(0, -top), min(tile, size-top)):
            for x in range(max(0, -left), min(tile, size-left)):
                value = art[y*tile+x]
                if value:
                    pixels[(top+y)*size+left+x] = value
    return pixels


def battery_icon(devices, size=None):
    size = tray_icon_size() if size is None else size
    pixels = P()
    info = Bitmap(size=C.sizeof(Bitmap), width=size, height=-size, planes=1, bpp=32)
    picture = dib(None, C.byref(info), 0, C.byref(pixels), None, 0)
    if not picture:
        return None
    mask = None
    try:
        data = (C.c_uint32 * (size*size)).from_address(pixels.value)
        data[:] = combined_pixels(size, devices)
        stride = ((size+15)//16)*2
        mask_data = bytearray(stride*size)
        for y in range(size):
            for x in range(size):
                if not data[y*size+x]:
                    mask_data[y*stride+x//8] |= 0x80 >> (x%8)
        mask = bitmap(size, size, 1, 1, bytes(mask_data))
        if not mask:
            return None
        icon = IconInfo(icon=True, mask=mask, color=picture)
        return create_icon(C.byref(icon))
    finally:
        if mask:
            delete(mask)
        delete(picture)


class Tray:
    def __init__(self, refresh, show, stop, defer, activate):
        self.refresh, self.show, self.stop = refresh, show, stop
        self.activate = activate
        self.defer = defer
        self.icons = {}
        self.pending_icon = None
        self.icon_retries = 0
        self.sync_callback = None
        self.callback = CALLBACK(self.dispatch)
        self.taskbar_created = register_message("TaskbarCreated")
        self.instance = module_handle(None)
        window_class = WindowClass(proc=self.callback, instance=self.instance, name=CLASS)
        if not register(C.byref(window_class)):
            raise C.WinError(C.get_last_error())
        self.hwnd = create_window(0, CLASS, CLASS, 0, 0, 0, 0, 0, None, None, self.instance, None)
        if not self.hwnd:
            unregister(CLASS, self.instance)
            raise C.WinError(C.get_last_error())

    def dispatch(self, hwnd, message, wparam, lparam):
        if message == 2:
            post_quit(0)
            return 0
        if message == WM_SHOW:
            self.defer(self.activate)
            return 0
        if message == WM_STOP:
            self.defer(self.stop)
            return 0
        if message == self.taskbar_created:
            for _, data in self.icons.values():
                notify(0, C.byref(data))
            if self.pending_icon is not None:
                self.defer(self.retry_icon)
            return 0
        if message == 0x113 and wparam == 1:
            self.defer(self.refresh)
            return 0
        if message == 0x113 and wparam == 2 and self.sync_callback:
            self.defer(self.run_settings_sync)
            return 0
        if message == 0x113 and wparam == ICON_RETRY_TIMER:
            self.defer(self.retry_icon)
            return 0
        if message == WM_TRAY:
            if lparam == 0x202 and wparam == ICON_ID:
                self.defer(self.activate)
            elif lparam == 0x205:
                self.defer(self.show)
            return 0
        return def_proc(hwnd, message, wparam, lparam)

    def run_settings_sync(self):
        if self.sync_callback is not None:
            self.sync_callback()

    def retry_icon(self):
        if self.pending_icon is None:
            return
        if self.icon_retries < ICON_RETRY_LIMIT:
            self.icon_retries += 1
        self.update(*self.pending_icon)
        if self.icon_retries >= ICON_RETRY_LIMIT:
            kill_timer(self.hwnd, ICON_RETRY_TIMER)

    def update(self, devices, tip):
        previous = self.icons.get(ICON_ID)
        size = tray_icon_size()
        key = devices, tip, size
        if previous and previous[0] == key:
            return
        same_image = previous and (previous[0][0], previous[0][2]) == (devices, size)
        icon = previous[1].icon if same_image else battery_icon(devices, size)
        if not icon:
            return
        data = Notify(size=C.sizeof(Notify), window=self.hwnd, id=ICON_ID,
                      flags=7, callback=WM_TRAY, icon=icon, tip=tip[:126])
        persistent = (bool(previous[1].flags & 0x20) if previous
                      else FROZEN or Path(sys.executable).name.lower() == "pythonw.exe")
        if persistent:
            data.flags |= 0x20
            C.memmove(C.byref(data, Notify.guid.offset), ICON_GUID, 16)
        operation = 1 if previous else 0
        accepted = notify(operation, C.byref(data))
        if not accepted and not previous and data.flags & 0x20:
            data.flags &= ~0x20
            accepted = notify(operation, C.byref(data))
        if not accepted:
            if not same_image:
                destroy_icon(icon)
            if not previous:
                if self.pending_icon is None:
                    set_timer(self.hwnd, ICON_RETRY_TIMER, 500, None)
                self.pending_icon = devices, tip
            return
        if previous and not same_image:
            destroy_icon(previous[1].icon)
        self.icons[ICON_ID] = key, data
        if self.pending_icon is not None:
            kill_timer(self.hwnd, ICON_RETRY_TIMER)
            self.pending_icon = None
            self.icon_retries = 0

    def interval(self, seconds):
        if not set_timer(self.hwnd, 1, seconds * 1000, None):
            raise C.WinError(C.get_last_error())

    def watch_settings(self, callback):
        if callback is None:
            kill_timer(self.hwnd, 2)
            self.sync_callback = None
        else:
            if not set_timer(self.hwnd, 2, 1400, None):
                raise C.WinError(C.get_last_error())
            self.sync_callback = callback

    def close(self):
        self.watch_settings(None)
        kill_timer(self.hwnd, ICON_RETRY_TIMER)
        self.pending_icon = None
        kill_timer(self.hwnd, 1)
        for _, data in self.icons.values():
            notify(2, C.byref(data))
            destroy_icon(data.icon)
        self.icons.clear()
        destroy_window(self.hwnd)
        unregister(CLASS, self.instance)

