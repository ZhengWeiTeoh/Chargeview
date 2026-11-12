"""Read the VT3 V2's active onboard settings using Rapoo Web Hub's register layout."""
from chargeview.hardware.windows_hid import rapoo_registers

POLLING_RATES = {
    0x08: 125, 0x04: 250, 0x02: 500, 0x01: 1000,
    0x84: 2000, 0x82: 4000, 0x81: 8000,
}


def dpi_table(data):
    return [int.from_bytes(data[i:i + 2], "little") for i in range(0, len(data), 2)]


def read_state(read):
    for _ in range(2):
        # Web Hub: CONFIG_CURRENT is 0x010C. Each profile starts 0x0400
        # bytes after the previous one, with the DPI table in bank 0x08.
        profile = read(0x0C, 1, 0x01)[0]
        if not 0 <= profile < 8:
            raise ValueError("The mouse did not report a valid onboard profile.")
        bank = 0x08 + profile * 4
        slots = read(0x96, 3, bank)
        count = min(6, slots[0] + 1)
        stage = slots[2]
        if slots[0] > 6 or stage >= count:
            raise ValueError("The mouse did not report valid DPI slot data.")
        x = dpi_table(read(0x88, count * 2, bank))
        y = dpi_table(read(0xC8, count * 2, bank))
        if any(not 50 <= dpi <= 26000 for dpi in x + y):
            raise ValueError("The mouse did not report valid DPI values.")
        rate = POLLING_RATES.get(read(0x80, 1, bank)[0])
        if read(0x0C, 1, 0x01)[0] == profile:
            return {"dpi": list(zip(x, y)), "stage": stage, "rate": rate}
    raise ValueError("The mouse changed profiles while reading its settings.")


def snapshot(paths, stop):
    with rapoo_registers(paths, stop) as read:
        return read_state(read)
