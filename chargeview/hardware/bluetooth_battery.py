"""Read the Crush80 battery percentage reported to Windows over Bluetooth LE."""

import ctypes as C
from ctypes import wintypes as W
import re
import os
import subprocess
from pathlib import Path

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

_connection_query = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$info = [Windows.Devices.Enumeration.DeviceInformation,Windows.Devices.Enumeration,ContentType=WindowsRuntime]
$kind = [Windows.Devices.Enumeration.DeviceInformationKind,Windows.Devices.Enumeration,ContentType=WindowsRuntime]
$collection = [Windows.Devices.Enumeration.DeviceInformationCollection,Windows.Devices.Enumeration,ContentType=WindowsRuntime]
$ble = [Windows.Devices.Bluetooth.BluetoothLEDevice,Windows.Devices.Bluetooth,ContentType=WindowsRuntime]
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethodDefinition -and
    $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
$properties = [string[]]@('System.Devices.Aep.IsConnected','System.Devices.Aep.DeviceAddress')
$operation = $info::FindAllAsync($ble::GetDeviceSelectorFromPairingState($true), $properties, $kind::AssociationEndpoint)
$task = $asTask.MakeGenericMethod($collection).Invoke($null, @($operation))
$task.Wait()
foreach ($device in $task.Result) {
    $connected = $false
    $address = $null
    # Windows PowerShell exposes the WinRT property map as key/value entries.
    foreach ($entry in $device.Properties) {
        switch ($entry.Key) {
            'System.Devices.Aep.IsConnected' { $connected = $entry.Value -eq $true }
            'System.Devices.Aep.DeviceAddress' { $address = $entry.Value }
        }
    }
    if ($connected -and $address) {
        $address
    }
}
"""


def _connected_addresses():
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    try:
        result = subprocess.run(
            [str(powershell), "-NoProfile", "-NonInteractive", "-Command", _connection_query],
            capture_output=True, text=True, timeout=5, check=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return {line.strip().replace(":", "").upper() for line in result.stdout.splitlines()}


def _byte_property(node, key):
    kind, size, value = W.ULONG(), W.ULONG(1), C.c_ubyte()
    status = _get_property(node, C.byref(key), C.byref(kind), C.byref(value), C.byref(size), 0)
    if status == 0 and kind.value == 3 and size.value == 1:
        return value.value
    return None


def crush80_battery():
    """Return the battery percentage and confirmed Bluetooth connection state."""
    enumerator = "BTHLEDEVICE"
    flags = 0x101  # CM_GETIDLIST_FILTER_PRESENT | CM_GETIDLIST_FILTER_ENUMERATOR
    for _ in range(2):
        size = W.ULONG()
        if _list_size(C.byref(size), enumerator, flags) or size.value <= 1:
            return None, None
        ids = C.create_unicode_buffer(size.value)
        status = _list_ids(enumerator, ids, size.value, flags)
        if status != 0x1A:  # CR_BUFFER_SMALL when devices change during enumeration
            break
    if status:
        return None, None
    candidates = [device_id for device_id in ids[:].split("\0") if _battery_service.match(device_id)]
    if not candidates:
        return None, None
    connected = _connected_addresses()
    if connected is None:
        return None, None
    for device_id in candidates:
        address = device_id.split("\\")[1].rsplit("_", 1)[-1].upper()
        if address not in connected:
            continue
        service, device = W.DWORD(), W.DWORD()
        if _locate(C.byref(service), device_id, 0) or _parent(C.byref(device), service, 0):
            continue
        level = _byte_property(device, _battery_level)
        return (level if level is not None and level <= 100 else None), True
    return None, False
