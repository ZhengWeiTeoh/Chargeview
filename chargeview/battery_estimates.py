"""Estimate battery runtime and time to full from observed readings."""
from datetime import datetime

HISTORY_HOURS = 168
MIN_SECONDS = 30 * 60
MIN_DROP = 2


def update_history(previous, now, level, charging, interval):
    if not previous or bool(previous.get("charging", False)) != charging:
        return []
    try:
        last_level = previous["level"]
        last_seen = datetime.fromisoformat(previous["updated"])
        elapsed = (now - last_seen).total_seconds()
        change = level - last_level if charging else last_level - level
        if change < 0 or elapsed <= 0:
            return []
        hour = int(now.timestamp() // 3600)
        history_hours = 2 if charging else HISTORY_HOURS
        buckets = [[key, seconds, drop] for key, seconds, drop in previous.get("runtime", [])
                   if hour - history_hours < key <= hour and seconds >= 0 and drop >= 0]
    except (KeyError, TypeError, ValueError):
        return []

    # A long gap gives no reliable rate and may conceal a charger disconnect.
    if elapsed > max(180, interval * 3) and charging:
        return []
    if elapsed <= max(180, interval * 3):
        if not buckets or buckets[-1][0] != hour:
            buckets.append([hour, 0, 0])
        buckets[-1][1] += elapsed
        buckets[-1][2] += change
    return buckets


def remaining_text(level, history):
    if level == 0:
        return "Charge now"
    elapsed = sum(seconds for _, seconds, _ in history)
    drop = sum(points for _, _, points in history)
    if elapsed < MIN_SECONDS or drop < MIN_DROP:
        return None
    hours = level * elapsed / (drop * 3600)
    if hours < 1:
        return "Under 1 h left"
    rounded = max(1, round(hours))
    days, rest = divmod(rounded, 24)
    if not days:
        return f"~{rest} h left"
    return f"~{days} d {rest} h left" if rest else f"~{days} d left"


def time_to_full(level, history):
    if level >= 100:
        return "Fully charged"
    elapsed = sum(seconds for _, seconds, _ in history)
    gain = sum(points for _, _, points in history)
    if elapsed < 5 * 60 or gain < 2:
        return None
    minutes = (100 - level) * elapsed / (gain * 60)
    if minutes < 5:
        return "Under 5 min to full"
    hours, remainder = divmod(max(5, round(minutes / 5) * 5), 60)
    if not hours:
        return f"~{remainder} min to full"
    return f"~{hours} h {remainder} min to full" if remainder else f"~{hours} h to full"


def cached_text(reading):
    try:
        if reading.get("charging"):
            return None
        return remaining_text(reading["level"], reading.get("runtime", []))
    except (KeyError, ValueError, TypeError):
        return None
