"""Pixel-sized art for the Tk popups. Text remains native Tk text."""
from functools import lru_cache
from math import atan2, cos, hypot, pi, sqrt

BOLT = ((.76, .07), (.94, .07), (.76, .42), (.93, .42),
        (.45, .94), (.56, .59), (.39, .59))


def rgb(color):
    return bytes.fromhex(color.lstrip("#"))


def ppm(width, height, data):
    return f"P6\n{width} {height}\n255\n".encode() + data


def blend(first, second, fraction):
    return bytes(round(a + (b-a)*fraction) for a, b in zip(first, second))


@lru_cache(maxsize=12)
def card_art(w, h, radius, background, level, hue):
    backdrop = rgb(background)
    ink, rim, dim, liquid = map(rgb, ("#17161e", "#333044", "#32313c", hue))
    points = [(x*w, y*h) for x, y in BOLT]
    edges = list(zip(points[-1:] + points[:-1], points))
    pixels = bytearray()

    def span(row, left, right, color):
        if right <= left:
            return
        start, end = int(left), min(w-1, int(right))
        if end > start + 1:
            row[(start+1)*3:end*3] = color * (end-start-1)
        for x in {start, end}:
            coverage = min(right, x+1) - max(left, x)
            if coverage > 0:
                offset = x*3
                row[offset:offset+3] = blend(row[offset:offset+3], color, coverage)

    def edge(y, inset):
        r = max(0, radius-inset)
        dy = max(radius-y, y-h+radius, 0)
        return inset + r - sqrt(max(0, r*r-dy*dy))

    for y in range(h):
        at = y+.5
        row = bytearray(backdrop*w)
        left = edge(at, 0)
        span(row, left, w-left, rim)
        if 1 <= y < h-1:
            left = edge(at, 1)
            span(row, left, w-left, ink)
        intersections = sorted(x1 + (x2-x1)*(at-y1)/(y2-y1)
                               for (x1,y1),(x2,y2) in edges
                               if min(y1,y2) <= at < max(y1,y2))
        surface = h*(.94-.87*(level or 0)/100)
        color = dim
        if level and at >= surface:
            amount = .96 - .36*min(1, (at-surface)/max(1, h*.94-surface))
            color = blend(ink, liquid, amount)
        for start, end in zip(intersections[::2], intersections[1::2]):
            span(row, start, end, color)
        pixels.extend(row)
    return ppm(w, h, pixels)


def distance(x, y, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    t = max(0, min(1, ((x-a[0])*dx + (y-a[1])*dy) / (dx*dx+dy*dy)))
    return hypot(x-a[0]-dx*t, y-a[1]-dy*t)


@lru_cache(maxsize=16)
def action_art(size, kind, background):
    base, ink = rgb(background), rgb("#f0edf8")

    def inside(x, y):
        if kind == "close":
            return min(distance(x,y,(.25,.25),(.75,.75)),
                       distance(x,y,(.75,.25),(.25,.75))) < .054
        angle = atan2(y-.5, x-.5)
        if kind == "settings":
            radius = hypot(x-.5, y-.5)
            return .14 <= radius <= (.35 if cos(8*angle) > .30 else .26)
        ring = abs(hypot(x-.5,y-.5)-.285) < .052 and not -pi < angle < -2.28
        arrow = min(distance(x,y,(.23,.48),(.14,.34)),
                    distance(x,y,(.23,.48),(.35,.38))) < .052
        return ring or arrow

    data = bytearray()
    for y in range(size):
        for x in range(size):
            coverage = sum(inside((x+(dx+.5)/4)/size, (y+(dy+.5)/4)/size)
                           for dy in range(4) for dx in range(4))/16
            data.extend(blend(base, ink, coverage))
    return ppm(size,size,data)

@lru_cache(maxsize=16)
def meter_art(width, height, background, color, level):
    base, track, fill = map(rgb, (background, "#4a4657", color))
    radius = height / 2
    end = radius + (width-height)*(level or 0)/100
    data = bytearray()
    for y in range(height):
        for x in range(width):
            counts = [0, 0, 0]
            for dy in range(4):
                for dx in range(4):
                    sx, sy = x+(dx+.5)/4, y+(dy+.5)/4
                    span = sqrt(max(0, radius*radius-(sy-radius)**2))
                    if level and radius-span <= sx <= end+span:
                        counts[2] += 1
                    elif radius-span <= sx <= width-radius+span:
                        counts[1] += 1
                    else:
                        counts[0] += 1
            data.extend(round(sum(shade[channel]*count for shade, count in
                                  zip((base,track,fill), counts))/16) for channel in range(3))
    return ppm(width, height, data)

@lru_cache(maxsize=16)
def switch_art(width, height, background, enabled):
    base = rgb(background)
    track = rgb("#39785b" if enabled else "#4b4558")
    thumb = rgb("#f5f2fb")
    radius = height / 2
    center = width - radius if enabled else radius
    data = bytearray()
    for y in range(height):
        for x in range(width):
            counts = [0, 0, 0]
            for dy in range(4):
                for dx in range(4):
                    sx, sy = x+(dx+.5)/4, y+(dy+.5)/4
                    if hypot(sx-center, sy-radius) < radius*.68:
                        counts[2] += 1
                    elif hypot(max(radius-sx, sx-width+radius, 0), sy-radius) < radius:
                        counts[1] += 1
                    else:
                        counts[0] += 1
            data.extend(round(sum(shade[channel]*count for shade, count in
                                  zip((base, track, thumb), counts))/16) for channel in range(3))
    return ppm(width, height, data)
