import ctypes as C
from ctypes import wintypes as W
from pathlib import Path
import os
import subprocess
import sys
import time
import winreg
import tempfile
from xml.sax.saxutils import escape

from chargeview.hardware.windows_hid import GUID, P, bind, shell

NAME = "\u7535\u91cf\u6258\u76d8"
APPROVAL = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder"
FROZEN = getattr(sys, "frozen", False)
ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "start.pyw"
PYTHONW = Path(sys.executable).with_name("pythonw.exe")
OLE = C.OleDLL("ole32")
CLS_LINK = GUID.parse("00021401-0000-0000-c000-000000000046")
IID_LINK = GUID.parse("000214f9-0000-0000-c000-000000000046")
IID_FILE = GUID.parse("0000010b-0000-0000-c000-000000000046")
FOLDER_STARTUP = GUID.parse("b97d20bb-f46a-4c97-ba10-5e3608430854")
FOLDER_DESKTOP = GUID.parse("b4bfcc3a-db2c-424c-b029-7fe99a87c641")


def known_folder(folder):
    value = P()
    get = bind(shell, "SHGetKnownFolderPath", C.HRESULT if hasattr(C, "HRESULT") else W.LONG, P, W.DWORD, W.HANDLE, P)
    if get(C.byref(folder), 0, None, C.byref(value)) < 0:
        raise OSError("Windows could not locate the requested folder.")
    try:
        return Path(C.wstring_at(value))
    finally:
        bind(OLE, "CoTaskMemFree", None, P)(value)


def method(obj, index, result, *types):
    table = C.cast(obj, C.POINTER(C.POINTER(P))).contents
    return C.WINFUNCTYPE(result, P, *types)(table[index])


def checked(result):
    if result < 0:
        raise OSError(f"Windows COM error 0x{result & 0xFFFFFFFF:08X}")


def save_link(path, target, arguments):
    initialized = bind(OLE, "CoInitializeEx", W.LONG, P, W.DWORD)(None, 2)
    if initialized < 0 and initialized != -2147417850:
        checked(initialized)
    link, file = P(), P()
    try:
        create = bind(OLE, "CoCreateInstance", W.LONG, P, P, W.DWORD, P, P)
        checked(create(C.byref(CLS_LINK), None, 1, C.byref(IID_LINK), C.byref(link)))
        for index, value in [(20, str(target)), (11, arguments), (9, str(ROOT)), (7, NAME)]:
            checked(method(link, index, W.LONG, W.LPCWSTR)(link, value))
        checked(method(link, 0, W.LONG, P, P)(link, C.byref(IID_FILE), C.byref(file)))
        checked(method(file, 6, W.LONG, W.LPCWSTR, W.BOOL)(file, str(path), True))
    finally:
        for obj in (file, link):
            if obj:
                method(obj, 2, W.ULONG)(obj)
        if initialized >= 0:
            bind(OLE, "CoUninitialize", None)()


def launch_command(*arguments):
    if FROZEN:
        return [sys.executable, *arguments]
    return [str(PYTHONW), str(SCRIPT), *arguments]


def link_target(path):
    initialized = bind(OLE, "CoInitializeEx", W.LONG, P, W.DWORD)(None, 2)
    if initialized < 0 and initialized != -2147417850:
        checked(initialized)
    link, file = P(), P()
    try:
        create = bind(OLE, "CoCreateInstance", W.LONG, P, P, W.DWORD, P, P)
        checked(create(C.byref(CLS_LINK), None, 1, C.byref(IID_LINK), C.byref(link)))
        checked(method(link, 0, W.LONG, P, P)(link, C.byref(IID_FILE), C.byref(file)))
        checked(method(file, 5, W.LONG, W.LPCWSTR, W.DWORD)(file, str(path), 0))
        buffer = C.create_unicode_buffer(32768)
        checked(method(link, 3, W.LONG, W.LPWSTR, C.c_int, P, W.DWORD)(
            link, buffer, len(buffer), None, 0))
        return Path(buffer.value)
    finally:
        for obj in (file, link):
            if obj:
                method(obj, 2, W.ULONG)(obj)
        if initialized >= 0:
            bind(OLE, "CoUninitialize", None)()


def startup_link():
    return known_folder(FOLDER_STARTUP) / (NAME + ".lnk")


def enabled():
    if not startup_link().is_file():
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPROVAL) as key:
            value = winreg.QueryValueEx(key, NAME + ".lnk")[0]
        return not value or value[0] & 1 == 0
    except FileNotFoundError:
        return True


def set_enabled(on):
    link = startup_link()
    target, *arguments = launch_command("--tray")
    if not link.exists() or on and FROZEN and link_target(link) != Path(target):
        save_link(link, target, subprocess.list2cmdline(arguments))
    state = (2 if on else 3).to_bytes(4, "little")
    state += (0 if on else 116444736000000000 + time.time_ns() // 100).to_bytes(8, "little")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, APPROVAL) as key:
        winreg.SetValueEx(key, NAME + ".lnk", 0, winreg.REG_BINARY, state)
    if on:
        install_signin_task()


def install_signin_task():
    """Install the early sign-in launcher when the user enables startup."""
    account = os.environ["USERDOMAIN"] + "\\" + os.environ["USERNAME"]
    target, *arguments = launch_command("--startup-tray")
    xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
<RegistrationInfo><Description>Starts Chargeview at sign-in when its Startup entry is enabled.</Description></RegistrationInfo>
<Triggers><LogonTrigger><Enabled>true</Enabled><UserId>{escape(account)}</UserId></LogonTrigger></Triggers>
<Principals><Principal id="User"><UserId>{escape(account)}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
<Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><ExecutionTimeLimit>PT0S</ExecutionTimeLimit></Settings>
<Actions Context="User"><Exec><Command>{escape(str(target))}</Command><Arguments>{escape(subprocess.list2cmdline(arguments))}</Arguments><WorkingDirectory>{escape(str(ROOT))}</WorkingDirectory></Exec></Actions>
</Task>"""
    descriptor, filename = tempfile.mkstemp(suffix=".xml")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-16") as stream:
            stream.write(xml)
        subprocess.run(
            [str(Path(os.environ["SystemRoot"]) / "System32/schtasks.exe"),
             "/Create", "/TN", "Chargeview-" + os.environ["USERNAME"],
             "/XML", filename, "/F"],
            check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except subprocess.CalledProcessError as error:
        raise OSError("Windows could not install the early sign-in task.") from error
    finally:
        Path(filename).unlink(missing_ok=True)


def setup_entries():
    if FROZEN:
        if not startup_link().exists():
            set_enabled(False)
        return
    desktop = known_folder(FOLDER_DESKTOP)
    folder = desktop / "DeskCharge Project"
    script = desktop / "DeskCharge.pyw"
    if not os.path.lexists(folder):
        try:
            folder.symlink_to(ROOT, target_is_directory=True)
        except OSError:
            subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(folder), str(ROOT)], check=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
    if not os.path.lexists(script):
        try:
            script.symlink_to(SCRIPT)
        except OSError:
            os.link(SCRIPT, script)
    if not startup_link().exists():
        set_enabled(False)


