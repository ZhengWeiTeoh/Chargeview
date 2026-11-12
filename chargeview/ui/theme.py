"""Shared popup colors and text styles."""
import tkinter as tk

BG = "#101014"
CARD = "#19191f"
FG = "#f3f7ff"
MUTED = "#b1afb8"
ACCENT = "#ff566d"


def label(parent, value, size=10, color=FG, bg=BG, bold=False):
    return tk.Label(parent, text=value, fg=color, bg=bg, anchor="w",
                    font=("Segoe UI", size, "bold" if bold else "normal"))
