"""Battery card for the device popup."""
import tkinter as tk

from chargeview.ui.popup_art import card_art
from chargeview.ui.theme import FG
from chargeview.ui.windows_tray import battery_color


class Card:
    def __init__(self, parent, name, kind, scale):
        self.name, self.kind = name, kind
        self.scale = scale
        self.reading = None
        self.art_key = None
        self.box = tk.Canvas(parent, width=scale(255), height=scale(224),
                             bg=parent.cget("bg"), highlightthickness=0)
        self.box.bind("<Configure>", lambda _: self.draw())

    def draw(self):
        canvas, reading = self.box, self.reading
        canvas.delete("text")
        w, h = canvas.winfo_width(), canvas.winfo_height()
        if reading is None or min(w, h) < 2:
            return
        px = self.scale
        hue = battery_color(reading.level, reading.charging)
        key = w, h, px(21), canvas.cget("bg"), reading.level, hue
        if key != self.art_key:
            self.art = tk.PhotoImage(master=canvas, data=card_art(*key), format="PPM")
            canvas.delete("art")
            item = canvas.create_image(0, 0, image=self.art, anchor="nw", tags="art")
            canvas.tag_lower(item)
            self.art_key = key
        x = px(17)
        canvas.create_text(x, px(17), text=self.kind, anchor="nw", fill="#a9a2bf",
                           tags="text", font=("Segoe UI", 8, "bold"))
        canvas.create_text(x, px(34), text=self.name, anchor="nw", fill=FG,
                           tags="text", font=("Segoe UI", 12, "bold"))
        value = "—" if reading.level is None else f"{reading.level}%"
        canvas.create_text(x, px(57), text=value, anchor="nw", fill=hue,
                           tags="text", font=("Segoe UI", 33, "bold"))
        canvas.create_text(x, px(116), text=reading.runtime or reading.status, anchor="nw",
                           fill=FG, width=w-px(34), tags="text", font=("Segoe UI", 10, "bold"))
        if reading.runtime:
            canvas.create_text(x, px(140), text=reading.status, anchor="nw",
                               fill="#b9b4c9", width=w-px(34), tags="text", font=("Segoe UI", 9))
        source = reading.source
        if reading.stale:
            source += f"  ·  {reading.time.astimezone():%b %d %H:%M}"
        canvas.create_text(x, h-px(22), text=source, anchor="sw", fill="#c2bccd",
                           width=w-px(34), tags="text", font=("Segoe UI", 8))

    def render(self, reading):
        self.reading = reading
        self.draw()
