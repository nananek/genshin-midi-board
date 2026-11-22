"""Grid router used by gen_pcb.py.

The board is rasterised at 0.1 mm.  All existing copper (pads, routed tracks,
vias) is stored in a single "copper" bitmap per layer.  A* searches run on a
centreline grid where the obstacle map is produced by dilating that copper map
with a morphological dilation, so a cell is free only if a track of the wanted
width keeps the required clearance.  The current net's own copper is removed
again with a smaller dilation so the search can leave its own pads.

Vias are always 0.5 / 0.3 mm through vias.  A via is only placed where the
annulus and the drill keep clearance to all copper of other nets and where no
pad (not even a pad of the same net) is nearby, which rules out via-in-pad.
"""

from __future__ import annotations

import heapq
from math import ceil, hypot, inf

import pcbnew

TOMM = pcbnew.ToMM

CLEAR = 0.2          # worst case clearance used by the power/USB classes
MIN_CLEAR = 0.127    # JLCPCB minimum
EDGE = 0.3
VIA_R = 0.25
DRILL_R = 0.15


def cells(mm, cell=0.1):
    return int(ceil(mm / cell - 1e-9))


class Router:
    def __init__(self, width, height, cell=0.1):
        self.cell = cell
        self.nx = int(round(width / cell)) + 1
        self.ny = int(round(height / cell)) + 1
        self.n = self.nx * self.ny
        self.full = (1 << (8 * self.n)) - 1
        self.copper = [bytearray(self.n), bytearray(self.n)]
        self.padguard = bytearray(self.n)     # pads grown by via radius+clearance
        self.pads = []                        # (net, x0, y0, x1, y1, layers)
        self.edge_masks = {}
        self.net_geom = {}
        self.via_cells = {}
        self.expansions = 0

    # ---------------------------------------------------------------- helpers
    def cx(self, x):
        return min(self.nx - 1, max(0, int(round(x / self.cell))))

    def cy(self, y):
        return min(self.ny - 1, max(0, int(round(y / self.cell))))

    def idx(self, ix, iy):
        return iy * self.nx + ix

    def _rect_cells(self, x0, y0, x1, y1):
        ix0, ix1 = self.cx(x0), self.cx(x1)
        iy0, iy1 = self.cy(y0), self.cy(y1)
        for iy in range(iy0, iy1 + 1):
            row = iy * self.nx
            for ix in range(ix0, ix1 + 1):
                yield row + ix

    def stamp_rect(self, bitmap, x0, y0, x1, y1, grow=0.0):
        for i in self._rect_cells(x0 - grow, y0 - grow, x1 + grow, y1 + grow):
            bitmap[i] = 1

    def stamp_disc(self, bitmap, x, y, r):
        for i in self._rect_cells(x - r, y - r, x + r, y + r):
            ix, iy = i % self.nx, i // self.nx
            dx = ix * self.cell - x
            dy = iy * self.cell - y
            if dx * dx + dy * dy <= (r + self.cell * 0.5) ** 2:
                bitmap[i] = 1

    def stamp_seg(self, bitmap, p0, p1, r):
        x0, y0 = p0
        x1, y1 = p1
        for i in self._rect_cells(min(x0, x1) - r, min(y0, y1) - r,
                                  max(x0, x1) + r, max(y0, y1) + r):
            ix, iy = i % self.nx, i // self.nx
            px, py = ix * self.cell, iy * self.cell
            dx, dy = x1 - x0, y1 - y0
            ll = dx * dx + dy * dy
            if ll <= 1e-12:
                t = 0.0
            else:
                t = ((px - x0) * dx + (py - y0) * dy) / ll
                t = 0.0 if t < 0 else (1.0 if t > 1 else t)
            qx, qy = x0 + t * dx, y0 + t * dy
            if (px - qx) ** 2 + (py - qy) ** 2 <= (r + self.cell * 0.5) ** 2:
                bitmap[i] = 1

    def _dilate(self, value, r):
        """Morphological dilation by r cells on a byte-per-cell bitmap int."""
        if r <= 0 or value == 0:
            return value
        nx = self.nx
        s8 = 8
        up, down = s8 * nx, s8 * nx
        for _ in range(r):
            value = (value | (value << s8) | (value >> s8) |
                     (value << up) | (value >> down) |
                     (value << (up + s8)) | (value >> (up + s8)) |
                     (value << (up - s8)) | (value >> (up - s8))) & self.full
        return value

    # -------------------------------------------------------------- geometry
    def set_outline(self, points):
        for width in (0.127, 0.15, 0.2, 0.25, 0.35, 0.5, 0.8, 1.0):
            mask = bytearray(self.n)
            for a, b in zip(points, points[1:] + points[:1]):
                self.stamp_seg(mask, a, b, EDGE + width / 2 + 0.02)
            self.edge_masks[width] = bytes(mask)

    def edge_mask(self, width):
        best = max(w for w in self.edge_masks if w <= width + 1e-9)
        return self.edge_masks[best]

    def add_pad(self, net, x0, y0, x1, y1, layers, clearance):
        self.pads.append((net, x0, y0, x1, y1, layers))
        extra = max(0.0, clearance - MIN_CLEAR)
        for layer in layers:
            lay = 0 if layer == "F" else 1
            self.stamp_rect(self.copper[lay], x0, y0, x1, y1, extra)
        self.stamp_rect(self.padguard, x0, y0, x1, y1, VIA_R + MIN_CLEAR + 0.03)

    def commit_track(self, net, layer, p0, p1, width, extra=0.0):
        lay = 0 if layer == "F" else 1
        self.stamp_seg(self.copper[lay], p0, p1, width / 2 + extra)
        self.net_geom.setdefault(net, []).append(("trk", layer, p0, p1, width))

    def commit_via(self, net, p):
        key = (self.cx(p[0]), self.cy(p[1]))
        seen = self.via_cells.setdefault(net, set())
        if key in seen:
            return False
        seen.add(key)
        self.stamp_disc(self.copper[0], p[0], p[1], VIA_R)
        self.stamp_disc(self.copper[1], p[0], p[1], VIA_R)
        self.net_geom.setdefault(net, []).append(("via", p))
        return True

    def _own_map(self, net, extra=0.0):
        """Copper of `net` only, as two bytearrays."""
        own = [bytearray(self.n), bytearray(self.n)]
        for (pnet, x0, y0, x1, y1, layers) in self.pads:
            if pnet != net:
                continue
            for layer in layers:
                lay = 0 if layer == "F" else 1
                self.stamp_rect(own[lay], x0, y0, x1, y1, extra)
        for item in self.net_geom.get(net, []):
            if item[0] == "trk":
                _, layer, p0, p1, w = item
                self.stamp_seg(own[0 if layer == "F" else 1], p0, p1, w / 2 + extra)
            else:
                p = item[1]
                self.stamp_disc(own[0], p[0], p[1], VIA_R)
                self.stamp_disc(own[1], p[0], p[1], VIA_R)
        return own

    # ---------------------------------------------------------------- routing
    def masks(self, net, width, clearance=MIN_CLEAR):
        extra = max(0.0, clearance - MIN_CLEAR)
        own = self._own_map(net, extra)
        # the copper stamps already include half a cell of slack
        r_route = max(1, int((width / 2 + clearance + 0.02 - 0.05) / self.cell) + 1)
        r_via = cells(VIA_R + 0.25 + 0.02 - 0.05, self.cell)
        edge = int.from_bytes(self.edge_mask(width), "little")
        viamask = int.from_bytes(bytes(self.padguard), "little")
        blocked = []
        for lay in range(2):
            others = (int.from_bytes(bytes(self.copper[lay]), "little") &
                      ~int.from_bytes(bytes(own[lay]), "little") & self.full)
            blocked.append((self._dilate(others, r_route) | edge)
                           .to_bytes(self.n, "little"))
            viamask |= self._dilate(others, r_via)
        return blocked, (viamask & self.full).to_bytes(self.n, "little")

    def search(self, blocked, viamask, src, dst, max_expand=400000, via_cost=30):
        nx, ny, n = self.nx, self.ny, self.n
        sx, sy = self.cx(src[0]), self.cy(src[1])
        dx, dy = self.cx(dst[0]), self.cy(dst[1])
        src_layers = [0] if src[2] == "F" else [0, 1]
        dst_layers = {0} if dst[2] == "F" else {0, 1}
        goals = {lay * n + self.idx(dx, dy) for lay in dst_layers}
        gdist = [inf] * (2 * n)
        prev = [-1] * (2 * n)
        heap = []
        for lay in src_layers:
            start = lay * n + self.idx(sx, sy)
            gdist[start] = 0.0
            heapq.heappush(heap, (hypot(sx - dx, sy - dy), 0.0, start))
        nb = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
              (1, 1, 1.4142), (1, -1, 1.4142), (-1, 1, 1.4142), (-1, -1, 1.4142))
        expand = 0
        while heap:
            f, g, cur = heapq.heappop(heap)
            if g > gdist[cur]:
                continue
            if cur in goals:
                self.expansions += expand
                return self._backtrack(prev, cur, n)
            expand += 1
            if expand > max_expand:
                break
            lay, cell = divmod(cur, n)
            iy, ix = divmod(cell, nx)
            bl = blocked[lay]
            for ddx, ddy, cost in nb:
                jx, jy = ix + ddx, iy + ddy
                if jx < 0 or jy < 0 or jx >= nx or jy >= ny:
                    continue
                ni = jy * nx + jx
                if bl[ni]:
                    continue
                if ddx and ddy:
                    if bl[iy * nx + jx] or bl[jy * nx + ix]:
                        continue
                ng = g + cost
                ncur = lay * n + ni
                if ng < gdist[ncur]:
                    gdist[ncur] = ng
                    prev[ncur] = cur
                    heapq.heappush(heap, (ng + hypot(jx - dx, jy - dy), ng, ncur))
            other = 1 - lay
            if not blocked[other][cell] and not viamask[cell]:
                ng = g + via_cost
                ncur = other * n + cell
                if ng < gdist[ncur]:
                    gdist[ncur] = ng
                    prev[ncur] = cur
                    heapq.heappush(heap, (ng + hypot(ix - dx, iy - dy), ng, ncur))
        self.expansions += expand
        return None

    def _backtrack(self, prev, cur, n):
        path = []
        while cur >= 0:
            lay, cell = divmod(cur, n)
            iy, ix = divmod(cell, self.nx)
            path.append((lay, ix, iy))
            cur = prev[cur]
        path.reverse()
        return path

    def emit(self, net, path, width, start_xy=None, end_xy=None, extra=0.0):
        points = [(self.cell * ix, self.cell * iy, lay) for lay, ix, iy in path]
        if start_xy is not None:
            points[0] = (start_xy[0], start_xy[1], points[0][2])
        if end_xy is not None:
            points[-1] = (end_xy[0], end_xy[1], points[-1][2])
        simple = [points[0]]
        for p in points[1:]:
            if len(simple) >= 2:
                a, b = simple[-2], simple[-1]
                if a[2] == b[2] == p[2]:
                    cross = (b[0] - a[0]) * (p[1] - b[1]) - (b[1] - a[1]) * (p[0] - b[0])
                    dot = (b[0] - a[0]) * (p[0] - b[0]) + (b[1] - a[1]) * (p[1] - b[1])
                    if abs(cross) < 1e-9 and dot >= 0:
                        simple[-1] = p
                        continue
            simple.append(p)
        tracks, vias = [], []
        run = [simple[0]]
        for p in simple[1:]:
            if p[2] != run[-1][2]:
                vias.append((p[0], p[1]))
                self.commit_via(net, (p[0], p[1]))
                self._commit_run(net, run, width, tracks, extra)
                run = [p]
            else:
                run.append(p)
        self._commit_run(net, run, width, tracks, extra)
        return tracks, vias

    def _commit_run(self, net, run, width, tracks, extra=0.0):
        if len(run) < 2:
            return
        for a, b in zip(run, run[1:]):
            lg = "F" if a[2] == 0 else "B"
            tracks.append((lg, (a[0], a[1]), (b[0], b[1]), width))
            self.commit_track(net, lg, (a[0], a[1]), (b[0], b[1]), width, extra)

    def connect(self, net, src, dst, width, clearance=MIN_CLEAR, via_cost=30):
        blocked, viamask = self.masks(net, width, clearance)
        for _ in range(4):
            path = self.search(blocked, viamask, src, dst, via_cost=via_cost)
            if path is None:
                return False
            vias = [(self.cell * ix, self.cell * iy) for lay, ix, iy in path]
            pts = [p for lay, ix, iy in path for p in [(self.cell * ix, self.cell * iy)]]
            vl = []
            prev = None
            for lay, ix, iy in path:
                if prev is not None and lay != prev:
                    vl.append((self.cell * ix, self.cell * iy))
                prev = lay
            clash = [(a, b) for i, a in enumerate(vl) for b in vl[i + 1:]
                     if hypot(a[0] - b[0], a[1] - b[1]) < 0.72]
            for a in vl:
                for other_net, cells in self.via_cells.items():
                    if other_net == net:
                        continue
                    for (cx, cy) in cells:
                        if hypot(a[0] - cx * self.cell,
                                 a[1] - cy * self.cell) < 0.72:
                            clash.append((a, (cx * self.cell, cy * self.cell)))
            if not clash:
                break
            viamask = bytearray(viamask)
            for a, b in clash:
                self.stamp_disc(viamask, a[0], a[1], 0.6)
                self.stamp_disc(viamask, b[0], b[1], 0.6)
            viamask = bytes(viamask)
        else:
            return False
        self.emit(net, path, width, src[:2], dst[:2],
                  max(0.0, clearance - MIN_CLEAR))
        return True

    # ------------------------------------------------------- plane connection
    def connect_to_plane(self, net, pad, width, clearance=MIN_CLEAR):
        x, y = pad[0], pad[1]
        extra = max(0.0, clearance - MIN_CLEAR)
        blocked, viamask = self.masks(net, width, clearance)
        xmax, ymax = self.nx * self.cell - 0.7, self.ny * self.cell - 0.7
        cands = []
        for r in (0.6, 0.75, 0.9, 1.05, 1.2, 1.35, 1.5, 1.7, 1.9, 2.1, 2.4, 2.8):
            for k in range(16):
                a = 6.283185307179586 * k / 16
                cx = x + r * __import__("math").cos(a)
                cy = y + r * __import__("math").sin(a)
                if cx < 0.7 or cy < 0.7 or cx > xmax or cy > ymax:
                    continue
                i = self.idx(self.cx(cx), self.cy(cy))
                if viamask[i]:
                    continue
                if not self._seg_clear(blocked[0], (x, y), (cx, cy)):
                    continue
                cands.append((r, (cx, cy)))
            if cands:
                break
        if not cands:
            return [], []
        (cx, cy) = min(cands, key=lambda c: c[0])[1]
        self.commit_track(net, "F", (x, y), (cx, cy), width, extra)
        self.commit_via(net, (cx, cy))
        return [("F", (x, y), (cx, cy), width)], [(cx, cy)]

    def _seg_clear(self, block, p0, p1):
        x0, y0 = p0
        x1, y1 = p1
        steps = int(hypot(x1 - x0, y1 - y0) / (self.cell * 0.5)) + 1
        for s in range(steps + 1):
            t = s / steps
            x = x0 + (x1 - x0) * t
            y = y0 + (y1 - y0) * t
            if block[self.idx(self.cx(x), self.cy(y))]:
                return False
        return True
