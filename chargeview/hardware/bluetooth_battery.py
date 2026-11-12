"""Read the Crush80 battery percentage reported to Windows over Bluetooth LE."""

import ctypes as C
from ctypes import wintypes as W
import re

from chargeview.hardware.windows_hid import GUID, P, bind


class PropertyKey(C.Structure):
    _fields_ = [("format", GUID), ("id", W.DWORD)]


_config = C.WinDLL("cfgmgr32")
_list_size = bind(_config, "CM_Get_Device_ID_List_SizeW", W.ULONG, P, W.LPCWSTR, W.ULONG)
_list_ids = bind(_config, "CM_Get_Device_ID_ListW", W.ULONG, W.LPCWSTR, P, W.ULONG, W.ULONG)
_locate = bind(_config, "CM_Locate_DevNodeW", W.ULONG, P, W.LPCWSTR, W.ULONG)
_parent = bind(_config, "CM_Get_Parent", W.ULONG, P, W.DWORD, W.ULONG)
_get_property = bind(_config, "CM_Get_DevNode_PropertyW", W.ULONG, W.DWORD, P, P, P, P, W.ULONG)

_battery_service = re.compile(
    r"BTHLEDEVICE\\\{0000180F-0000-1000-8000-00805F9B34FB\}_DEV_VID&\d{2}245A_PID&8276_", re.I
)
_battery_level = PropertyKey(GUID.parse("104ea319-6ee2-4701-bd47-8ddbf425bbe5"), 2)
_connection_state = PropertyKey(GUID.parse("995ef0b0-7eb3-4a8b-b9ce-068bb3f4af69"), 4)


def _byte_property(node, key):
    kind, size, value = W.ULONG(), W.ULONG(1), C.c_ubyte()
    status = _get_property(node, C.byref(key), C.byref(kind), C.byref(value), C.byref(size), 0)
    if status == 0 and kind.value == 3 and size.value == 1:
        return value.value
    return None


def crush80_level():
    enumerator = "BTHLEDEVICE"
    flags = 0x101  # CM_GETIDLIST_FILTER_PRESENT | CM_GETIDLIST_FILTER_ENUMERATOR
    for _ in range(2):
        size = W.ULONG()
        if _list_size(C.byref(size), enumerator, flags) or size.value <= 1:
            return None
        ids = C.create_unicode_buffer(size.value)
        status = _list_ids(enumerator, ids, size.value, flags)
        if status != 0x1A:  # CR_BUFFER_SMALL when devices change during enumeration
            break
    if status:
        return None
    for device_id in ids[:].split("\0"):
        if not _battery_service.match(device_id):
            continue
        service, device = W.DWORD(), W.DWORD()
        if _locate(C.byref(service), device_id, 0) or _parent(C.byref(device), service, 0):
            continue
        if _byte_property(device, _connection_state) != 1:
            continue
        level = _byte_property(device, _battery_level)
        if level is not None and level <= 100:
            return level
    return None
