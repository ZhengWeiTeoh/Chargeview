import ctypes as C
from ctypes import wintypes as W
from contextlib import contextmanager
import re
import time
import uuid

kernel = C.WinDLL("kernel32", use_last_error=True)
user = C.WinDLL("user32", use_last_error=True)
hid = C.WinDLL("hid", use_last_error=True)
setup = C.WinDLL("setupapi", use_last_error=True)
shell = C.WinDLL("shell32", use_last_error=True)
gdi = C.WinDLL("gdi32", use_last_error=True)
P = C.c_void_p
UP = C.c_size_t
INVALID = P(-1).value


def bind(dll, name, result, *args):
    function = getattr(dll, name)
    function.restype = result
    function.argtypes = args
    return function


class GUID(C.Structure):
    _fields_ = [("bytes", C.c_ubyte * 16)]

    @classmethod
    def parse(cls, value):
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


class Interface(C.Structure):
    _fields_ = [("size", W.DWORD), ("guid", GUID), ("flags", W.DWORD), ("reserved", UP)]


class Caps(C.Structure):
    _fields_ = [(name, W.USHORT) for name in ("usage", "page", "input", "output", "feature")] + [
        ("reserved", W.USHORT * 17), ("counts", W.USHORT * 10)]


class Overlapped(C.Structure):
    _fields_ = [("internal", UP), ("high", UP), ("offset", W.DWORD),
                ("offset_high", W.DWORD), ("event", W.HANDLE)]


create_file = bind(kernel, "CreateFileW", W.HANDLE, W.LPCWSTR, W.DWORD, W.DWORD,
                   P, W.DWORD, W.DWORD, W.HANDLE)
close = bind(kernel, "CloseHandle", W.BOOL, W.HANDLE)
wait = bind(kernel, "WaitForSingleObject", W.DWORD, W.HANDLE, W.DWORD)
event = bind(kernel, "CreateEventW", W.HANDLE, P, W.BOOL, W.BOOL, W.LPCWSTR)
set_event = bind(kernel, "SetEvent", W.BOOL, W.HANDLE)
wait_many = bind(kernel, "WaitForMultipleObjects", W.DWORD, W.DWORD, P, W.BOOL, W.DWORD)
read_file = bind(kernel, "ReadFile", W.BOOL, W.HANDLE, P, W.DWORD, P, P)
result = bind(kernel, "GetOverlappedResult", W.BOOL, W.HANDLE, P, P, W.BOOL)
cancel = bind(kernel, "CancelIoEx", W.BOOL, W.HANDLE, P)
get_feature = bind(hid, "HidD_GetFeature", C.c_ubyte, W.HANDLE, P, W.ULONG)
set_feature = bind(hid, "HidD_SetFeature", C.c_ubyte, W.HANDLE, P, W.ULONG)
set_output = bind(hid, "HidD_SetOutputReport", C.c_ubyte, W.HANDLE, P, W.ULONG)
get_preparsed = bind(hid, "HidD_GetPreparsedData", C.c_ubyte, W.HANDLE, P)
free_preparsed = bind(hid, "HidD_FreePreparsedData", C.c_ubyte, P)
get_caps = bind(hid, "HidP_GetCaps", W.LONG, P, P)
get_product = bind(hid, "HidD_GetProductString", C.c_ubyte, W.HANDLE, P, W.ULONG)
get_devs = bind(setup, "SetupDiGetClassDevsW", W.HANDLE, P, W.LPCWSTR, W.HWND, W.DWORD)
enum_dev = bind(setup, "SetupDiEnumDeviceInterfaces", W.BOOL, W.HANDLE, P, P, W.DWORD, P)
detail_dev = bind(setup, "SetupDiGetDeviceInterfaceDetailW", W.BOOL, W.HANDLE, P, P, W.DWORD, P, P)
destroy_set = bind(setup, "SetupDiDestroyDeviceInfoList", W.BOOL, W.HANDLE)

HID_GUID = GUID.parse("4d1e55b2-f16f-11cf-88cb-001111000030")


@contextmanager
def opened(path, access=0, overlapped=False):
    handle = create_file(path, access, 3, None, 3, 0x40000000 if overlapped else 0, None)
    if handle == INVALID:
        raise C.WinError(C.get_last_error())
    try:
        yield handle
    finally:
        close(handle)


def interfaces(inspect=False):
    devices = get_devs(C.byref(HID_GUID), None, None, 0x12)
    if devices == INVALID:
        raise C.WinError(C.get_last_error())
    found = []
    try:
        index = 0
        while True:
            entry = Interface(size=C.sizeof(Interface))
            if not enum_dev(devices, None, C.byref(HID_GUID), index, C.byref(entry)):
                if C.get_last_error() != 259:
                    raise C.WinError(C.get_last_error())
                break
            index += 1
            size = W.DWORD()
            detail_dev(devices, C.byref(entry), None, 0, C.byref(size), None)
            if not size.value:
                continue
            data = C.create_string_buffer(size.value)
            C.cast(data, C.POINTER(W.DWORD))[0] = 8 if C.sizeof(P) == 8 else 6
            if detail_dev(devices, C.byref(entry), data, size, None, None):
                path = C.wstring_at(C.addressof(data) + 4)
                found.append(describe(path) if inspect else path)
    finally:
        destroy_set(devices)
    return found


def describe(path):
    caps = Caps()
    name = C.create_unicode_buffer(256)
    try:
        with opened(path) as handle:
            get_product(handle, name, C.sizeof(name))
            preparsed = P()
            if get_preparsed(handle, C.byref(preparsed)):
                try:
                    get_caps(preparsed, C.byref(caps))
                finally:
                    free_preparsed(preparsed)
    except OSError:
        pass
    return path, name.value, caps


def read_report(handle, length, stop, timeout):
    completed = event(None, True, False, None)
    if not completed:
        raise C.WinError(C.get_last_error())
    try:
        request = Overlapped(event=completed)
        buffer = (C.c_ubyte * length)()
        count = W.DWORD()
        if not read_file(handle, buffer, length, C.byref(count), C.byref(request)):
            error = C.get_last_error()
            if error != 997:
                raise C.WinError(error)
            events = (W.HANDLE * 2)(completed, stop)
            if wait_many(2, events, False, timeout) != 0:
                cancel(handle, C.byref(request))
                result(handle, C.byref(request), C.byref(count), True)
                return b""
            if not result(handle, C.byref(request), C.byref(count), False):
                raise C.WinError(C.get_last_error())
        return bytes(buffer[:count.value])
    finally:
        close(completed)


def rapoo_path(paths):
    return next((path for path in paths if re.search(
        r"vid_24ae&pid_(1462|4662)&mi_01&col09#", path, re.I)), None)


def decode_rapoo(data):
    if len(data) < 9 or data[0] != 7 or data[1] >> 4 not in (1, 2) or data[2] >= 6:
        return None
    x, y = int.from_bytes(data[3:5], "little"), int.from_bytes(data[5:7], "little")
    if min(x, y) < 50:
        return None
    charging = bool(data[7] & 2 or len(data) > 9 and data[9] in (1, 2))
    return (data[8] if data[8] <= 100 else None, charging, x, y, data[2])


def read_rapoo(path, stop):
    if not path:
        return None
    with opened(path, 0x80000000, True) as handle:
        deadline = time.monotonic() + 8
        while wait(stop, 0) == 258:
            remaining = int((deadline - time.monotonic()) * 1000)
            if remaining <= 0:
                break
            data = read_report(handle, 19, stop, remaining)
            if not data:
                break
            reading = decode_rapoo(data)
            if reading is not None:
                return reading
    return None


def feature(path, report_id, length):
    data = (C.c_ubyte * length)(report_id)
    with opened(path) as handle:
        if not get_feature(handle, data, length):
            raise C.WinError(C.get_last_error())
    return bytes(data)


def send_report(path, kind, data):
    caps = describe(path)[2]
    if caps.page < 0xFF00:
        raise ValueError("Select a vendor-defined interface for writes.")
    expected = caps.feature if kind == "Feature" else caps.output
    if not expected or len(data) != expected:
        raise ValueError(f"This interface requires a {expected}-byte {kind} report.")
    function = set_feature if kind == "Feature" else set_output
    buffer = (C.c_ubyte * len(data)).from_buffer_copy(data)
    with opened(path, 0x40000000) as handle:
        if not function(handle, buffer, len(data)):
            raise C.WinError(C.get_last_error())


@contextmanager
def rapoo_registers(paths, stop):
    status = rapoo_path(paths)
    if not status:
        raise ValueError("Connect the Rapoo receiver.")
    prefix, instance, _ = status.lower().split("#")[1:4]
    group = instance.rsplit("&", 1)[0]

    def collection(number):
        target = prefix.removesuffix("09") + number
        for path in paths:
            fields = path.lower().split("#")
            if len(fields) > 3 and fields[1] == target and fields[2].rsplit("&", 1)[0] == group:
                return path
        raise ValueError("The receiver control interface is unavailable.")

    output_path, feature_path = collection("05"), collection("06")
    if describe(output_path)[2].output != 33 or describe(feature_path)[2].feature != 33:
        raise ValueError("Unexpected receiver control interface.")

    with opened(output_path, 0x40000000) as output, opened(feature_path) as input_handle:
        def request(address, length, bank):
            if wait(stop, 0) == 0:
                raise ValueError("Device operation cancelled.")
            report = (C.c_ubyte * 33)(6, 0xA5, 0xA4, length, address, bank)
            if not set_output(output, report, 33):
                raise C.WinError(C.get_last_error())

        def read(address, length, bank=8):
            for _ in range(3):
                request(address, length, bank)
                for _ in range(5):
                    if wait(stop, 15) == 0:
                        raise ValueError("Read cancelled.")
                    response = (C.c_ubyte * 33)(8)
                    if get_feature(input_handle, response, 33):
                        offset = 4 if response[0] == 1 else 5 if response[:2] == [8, 1] else 0
                        if offset:
                            return bytes(response[offset:offset + length])
            raise ValueError("No reply from the mouse. Move it and try again.")

        yield read


def rapoo_dpi(paths, stop):
    from chargeview.hardware.rapoo import snapshot
    state = snapshot(paths, stop)
    return [x for x, _ in state["dpi"]], state["stage"]


def query_input(path, data, stop, prefix):
    caps = describe(path)[2]
    if not caps.input or not prefix:
        raise ValueError("This query needs an input report and an expected reply prefix.")
    with opened(path, 0x80000000, True) as reader:
        send_report(path, "Output", data)
        deadline = time.monotonic() + 1
        while wait(stop, 0) == 258:
            remaining = int((deadline - time.monotonic()) * 1000)
            if remaining <= 0:
                break
            reply = read_report(reader, caps.input, stop, remaining)
            if not reply or reply.startswith(prefix):
                return reply
    return b""
