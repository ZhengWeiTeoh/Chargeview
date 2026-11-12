import tkinter as tk
from tkinter import ttk, messagebox

from chargeview.hardware import windows_hid as hid
from chargeview import settings


def show_debug(root, worker):
    root.title("Chargeview · HID diagnostics")
    root.geometry("1040x650")
    root.minsize(780, 520)
    body = ttk.Frame(root, padding=14)
    body.pack(fill="both", expand=True)
    tree = ttk.Treeview(body, columns=("name", "id", "usage", "reports"), show="headings", height=12)
    for column, caption, width in [("name", "Product", 235), ("id", "VID:PID", 110),
                                   ("usage", "Page / Usage", 145), ("reports", "Input / Output / Feature", 170)]:
        tree.heading(column, text=caption)
        tree.column(column, width=width)
    scrollbar = ttk.Scrollbar(body, command=tree.yview)
    tree.config(yscrollcommand=scrollbar.set)
    tree.grid(row=0, column=0, sticky="nsew")
    scrollbar.grid(row=0, column=1, sticky="ns")
    path_label = ttk.Label(body, wraplength=930)
    path_label.grid(row=1, column=0, sticky="ew", pady=(5, 10))
    fields = ttk.Frame(body)
    fields.grid(row=2, column=0, sticky="ew")
    report_id = tk.StringVar(value="0")
    first = tk.StringVar(value="0")
    last = tk.StringVar(value="15")
    offset = tk.StringVar(value="1")
    signature = tk.StringVar()
    kind = tk.StringVar(value="Output")
    payload = tk.StringVar()
    output = tk.Text(body, height=9, state="disabled", font=("Consolas", 10), wrap="word")
    output.grid(row=5, column=0, sticky="nsew", pady=(10, 0))
    body.rowconfigure(0, weight=1)
    body.rowconfigure(5, weight=1)
    body.columnconfigure(0, weight=1)
    devices = []

    def log(text):
        output.config(state="normal")
        output.insert("end", str(text) + "\n")
        output.see("end")
        output.config(state="disabled")
        print(text, flush=True)

    def selected():
        if not tree.selection():
            raise ValueError("Select a HID interface first.")
        return devices[int(tree.selection()[0])]

    def show_path(_):
        if tree.selection():
            path_label.config(text=selected()[0])

    tree.bind("<<TreeviewSelect>>", show_path)

    def submit(action, done=log):
        if not worker.start(action, lambda value, error: log(error) if error else done(value)):
            log("A request is already in progress.")

    def list_devices():
        def show(items):
            devices[:] = items
            tree.delete(*tree.get_children())
            path_label.config(text="")
            for index, (path, name, caps) in enumerate(devices):
                import re
                match = re.search(r"vid_([0-9a-f]{4})&pid_([0-9a-f]{4})", path, re.I)
                product_id = ":".join(match.groups()).upper() if match else "—"
                tree.insert("", "end", iid=str(index), values=(name or "(unnamed)", product_id,
                            f"{caps.page:04X} / {caps.usage:04X}", f"{caps.input} / {caps.output} / {caps.feature}"))
            log(f"{len(devices)} HID interfaces.")
        submit(lambda _: hid.interfaces(True), show)

    def number(value):
        text = value.get().strip()
        return int(text, 16 if text.lower().startswith("0x") else 10)

    def form_action(action):
        def run():
            try:
                action()
            except (ValueError, OSError) as error:
                log(error)
        return run

    def feature_selection():
        path, _, caps = selected()
        if not caps.feature:
            raise ValueError("This interface declares no Feature Report.")
        return path, caps.feature

    def dump():
        path, length = feature_selection()
        report = number(report_id)
        if not 0 <= report <= 255:
            raise ValueError("Report ID must be 0–255.")
        submit(lambda _: hid.feature(path, report, length).hex(" ").upper())

    def probe():
        path, length = feature_selection()
        low, high = number(first), number(last)
        if not 0 <= low <= high <= 255:
            raise ValueError("Select a report ID range within 0–255.")

        def scan(stop):
            replies = []
            for report in range(low, high + 1):
                if hid.wait(stop, 0) == 0:
                    break
                try:
                    data = hid.feature(path, report, length)
                    replies.append(f"0x{report:02X}: {data.hex(' ').upper()}")
                except OSError:
                    continue
            return "\n".join(replies) or "No Feature Reports returned in this range."
        submit(scan)

    def send():
        path, _, caps = selected()
        data = bytes.fromhex(payload.get())
        report_kind = kind.get()
        if caps.page < 0xFF00 or not data:
            raise ValueError("Select a vendor interface and enter a full hex report.")
        if messagebox.askokcancel("Send HID command", "This sends the exact bytes to the selected device. Proceed?",
                                  parent=root):
            def action(_):
                hid.send_report(path, report_kind, data)
                return "Report accepted by Windows."
            submit(action)

    def calibrate(query=False):
        path, _, caps = selected()
        length = caps.input if query else caps.feature
        report, byte = (0 if query else number(report_id)), number(offset)
        prefix = bytes.fromhex(signature.get())
        request = bytes.fromhex(payload.get()) if query else b""
        if query and (kind.get() != "Output" or not prefix or not request):
            raise ValueError("Select Output and enter a complete request and reply prefix.")
        if query and not messagebox.askokcancel("Test battery query", "Send this battery query once to test it?", parent=root):
            return
        if not 0 <= report <= 255 or not 0 <= byte < length:
            raise ValueError("Check the report ID and zero-based byte offset.")

        def inspect(stop):
            data = hid.query_input(path, request, stop, prefix) if query else hid.feature(path, report, length)
            if len(data) <= byte or not data.startswith(prefix) or data[byte] > 100:
                raise ValueError("The sample does not match the signature or contain 0–100 at that offset.")
            return data[byte]

        def apply(percent):
            if messagebox.askokcancel("Calibrate Crush80", f"Sample reads {percent}%. Save this interface for the Crush80?",
                                      parent=root):
                config = settings.load()
                config["keyboard"] = {"path": path, "report": report, "offset": byte, "signature": prefix.hex(), "request": request.hex()}
                try:
                    settings.save(config)
                    log("Crush80 calibration saved. Refresh the tray app to load it.")
                except OSError as error:
                    log(error)
        submit(inspect, apply)

    def entry(parent, title, variable, width):
        ttk.Label(parent, text=title).pack(side="left", padx=(8, 3))
        ttk.Entry(parent, textvariable=variable, width=width).pack(side="left")

    ttk.Button(fields, text="Scan devices", command=list_devices).pack(side="left")
    entry(fields, "Report ID", report_id, 5)
    ttk.Button(fields, text="Dump Feature", command=form_action(dump)).pack(side="left", padx=5)
    entry(fields, "First ID", first, 5)
    entry(fields, "Last ID", last, 5)
    ttk.Button(fields, text="Probe IDs", command=form_action(probe)).pack(side="left", padx=5)
    commands = ttk.Frame(body)
    commands.grid(row=3, column=0, sticky="ew", pady=7)
    ttk.Combobox(commands, textvariable=kind, values=("Output", "Feature"), state="readonly", width=9).pack(side="left")
    entry(commands, "Full report (hex)", payload, 55)
    ttk.Button(commands, text="Send report", command=form_action(send)).pack(side="left", padx=6)
    calibration = ttk.Frame(body)
    calibration.grid(row=4, column=0, sticky="ew")
    entry(calibration, "Battery byte offset", offset, 6)
    entry(calibration, "Expected prefix (hex)", signature, 22)
    ttk.Button(calibration, text="Calibrate Feature", command=form_action(calibrate)).pack(side="left", padx=6)

    ttk.Button(calibration, text="Calibrate Output → Input", command=form_action(lambda: calibrate(True))).pack(side="left", padx=6)

    def close():
        worker.close()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    list_devices()

