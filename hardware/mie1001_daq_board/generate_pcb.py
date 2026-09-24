#!/usr/bin/env python3
"""Generate the MIE1001 Team 5 DAQ shield PCB (Arduino UNO R3 shield) from the schematic.

Run inside KiCad's Python (flatpak), after the schematic is final:
    flatpak run --command=kicad-cli org.kicad.KiCad sch export netlist \\
        --format kicadsexpr -o build/net.net mie1001_daq_board.kicad_sch
    flatpak run --command=python3 org.kicad.KiCad generate_pcb.py

Like generate_schematic.py, this OVERWRITES mie1001_daq_board.kicad_pcb, so make
layout changes here, not in the GUI.

Coordinates are "Uno coordinates" in mm, relative to the UNO header pin NC (pad 1
of the power header).  x grows away from the USB jack, y grows from the power
header towards the digital header, i.e. UP when the board is seen from the top,
exactly as on the Arduino A000066 drawing.  P() turns that into KiCad's y-down frame.
Board edge: x -27.94..40.64, y -2.54..50.80.

Rev E fix: KiCad's Module:Arduino_UNO_R3 footprint is drawn as seen from the BACK
(kicad-footprints issue #864).  Rev D used it as-is and came out as a mirror image of
a real UNO.  The footprint is now flipped top/bottom and every coordinate goes through
P(), so the shield matches the real board.  Check with a 1:1 print on a real UNO.

Tracks are laid by a small grid router (A*, two layers, 45-degree moves) in the
order given in ROUTE_ORDER.  Ground is two poured planes; the TIA input node
(LMP7721) sits inside a VREF guard pour on both layers.
"""
import heapq
import math
import os
import re
import sys

import numpy as np
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
FPROOT = "/app/extensions/Library/Footprints/footprints"
NETLIST = os.path.join(HERE, "build", "net.net")
OUT = os.path.join(HERE, "mie1001_daq_board.kicad_pcb")

OX, OY = 100.0, 100.0          # where Uno (0,0) lands on the KiCad page
MM = pcbnew.FromMM

# design rules (JLCPCB standard 2-layer allows 0.127/0.127 mm, 0.3 mm drill)
TRACK = 0.20                    # 0.2 lets tracks leave the 0.5 mm-pitch ADS1115 pads with margin
CLEAR = 0.20
VIA_D, VIA_DRILL = 0.60, 0.30
EDGE_CLEAR = 0.50
ZONE_CLEAR = 0.25


def P(x, y):
    """Uno coordinates (y up, as seen from the top) -> KiCad board coordinates (y down)."""
    return pcbnew.VECTOR2I(MM(OX + x), MM(OY - y))


# ---------------------------------------------------------------- netlist
def read_netlist(path):
    t = open(path).read()
    comps = {}
    for m in re.finditer(r'\(comp\s+\(ref "([^"]+)"\)(.*?)\(libsource', t, re.S):
        body = m.group(2)
        val = re.search(r'\(value "([^"]*)"\)', body).group(1)
        fp = re.search(r'\(footprint "([^"]*)"\)', body).group(1)
        ts = re.findall(r'\(tstamps "([^"]*)"\)', t[m.start():m.start() + 4000])
        fields = re.findall(r'\(field\s+\(name "([^"]+)"\)\s+"([^"]*)"\)', body)
        comps[m.group(1)] = (val, fp, ts[-1] if ts else "", fields)
    pads = {}
    nets = t[t.index("(nets"):]
    for blk in re.split(r'\n\s*\(net\s', nets)[1:]:
        name = re.search(r'\(name "([^"]*)"\)', blk).group(1)
        for ref, pin in re.findall(r'\(node\s+\(ref "([^"]+)"\)\s+\(pin "([^"]+)"\)', blk):
            pads[(ref, pin)] = name
    return comps, pads


# ------------------------------------------------------------- placement
# ref: (x, y, rotation_deg); None rotation = oriented by orient() in main()
# Central block, in a "screen" frame (y down) = rev D's layout frame.  Mapped to Uno
# coordinates by CL() below: the whole block moves rigidly, nothing inside it changes.
CLUSTER = {
    # ---- detector input + electrometer TIA, tight around the BNC (right end)
    "J1":  (26.19, 15.10, None),     # BNC centre pin; shell pins at (26.19, 12.56/17.64), (28.73, 15.10)
    "R14": (23.10, 15.10, 0),        # 10k anti-surge 0603, series protection at the centre pin
    "R4":  (23.30, 12.80, 90),
    "D1":  (22.90, 17.90, None),     # VREF clamp, common pin facing the DET_IN node
    "U4":  (17.40, 16.90, 0),        # LMP7721
    "R17": (13.90, 13.40, 180),      # 1k into IN+ (pin 1); TIA_REF end faces U4
    "JP1": (21.00, 3.00, None),
    "R1":  (17.00, 3.00, 0),
    "R2":  (16.80, 8.08, 0),
    "C1":  (17.60, 11.40, 0),
    "C8":  (20.80, 22.20, 0),        # at V+ (pin 6), outside the guard
    "R3":  (14.50, 21.60, 90),
    "C2":  (16.60, 23.40, 90),
    # ---- ADC
    "U2":  (12.50, 26.00, 180),
    "C5":  (8.60, 26.60, 90),
    "R11": (20.60, 27.60, 90),
    "R13": (8.60, 23.20, 0),
    "R16": (18.60, 25.20, 90),       # 1k into AIN1, matches AIN0's 1k
    "C10": (20.40, 24.60, 90),
    "J3":  (3.00, 21.00, None),
    # ---- op-amp buffers (A = DAC, B = VREF), VREF divider and VREF decoupling
    "U3":  (7.00, 15.50, 0),
    "C6":  (8.30, 11.20, 0),
    "R15": (11.40, 11.20, 0),        # VREF buffer isolation resistor
    "C9":  (11.20, 9.40, 0),         # VREF bulk decoupling
    "R7":  (12.30, 18.40, 90),
    "R8":  (12.30, 21.50, 90),
    "C3":  (10.40, 20.60, 90),       # 10 uF on the divider
    # ---- DAC
    "U1":  (1.20, 16.50, 180),
    "C4":  (1.20, 13.50, 0),
    "R12": (2.00, 11.20, 0),
}
CLUSTER_Y = 29.60
def CL(x, y):
    """cluster frame (y down) -> Uno coordinates (y up)"""
    return x, CLUSTER_Y - y

PLACE = {
    "A1":  (0.00, 0.00, 0),
    # ---- digital: I2C pull-ups by SDA/SCL, trigger parts by D8
    "R5":  (-6.60, 43.40, 90),
    "R6":  (-9.14, 43.40, 90),
    "R9":  (13.72, 43.40, 90),
    "R10": (11.18, 43.40, 90),
    # ---- power entry
    "C7":  (6.30, 3.00, 90),
    # ---- edge connectors, left end between the DC jack and the USB jack (pin 1 on top)
    "J2":  (-24.30, 16.40, None),    # QPS command out: pin 1 at y 16.40, pin 2 at 12.90
    "J4":  (-24.30, 25.20, None),    # trigger in:      pin 1 at y 25.20, pin 2 at 21.70
}
for _r, (_x, _y, _rot) in CLUSTER.items():
    PLACE[_r] = (*CL(_x, _y), _rot)
# Around the ADC, in Uno coordinates: in the real orientation its I2C/VDD pins face the
# power header, so C5 and R13 move up to leave them an escape to the left.
PLACE["C5"] = (7.80, 6.40, 0)
PLACE["R13"] = (7.00, 9.60, 0)
PLACE["C7"] = (6.30, 3.00, 90)
# Uno R3 mounting holes (Arduino A000066 datasheet), in Uno coordinates.  Two of the
# Uno's four holes are left out: at (38.10, 5.08) an M3 head would sit under the BNC
# flange, and at (-12.70, 48.26) it would hit the stacking header of the R3 SCL pin.
HOLES = [(-13.97, 0.00), (38.10, 33.02)]
# Parts of the Uno taller than the gap under the shield: no bottom copper and
# no through-hole leads above them.  The shield rests on the USB-B shell.
KEEPOUT = {
    "USB-B jack":  [(-27.94, 28.80), (-17.40, 28.80), (-17.40, 42.30), (-27.94, 42.30)],
    "DC jack":     [(-27.94, -2.54), (-16.00, -2.54), (-16.00, 10.50), (-27.94, 10.50)],
    "ICSP header": [(34.00, 21.40), (39.90, 21.40), (39.90, 29.60), (34.00, 29.60)],
    "ICSP1 (16U2)": [(-13.60, 40.40), (-4.90, 40.40), (-4.90, 46.60), (-13.60, 46.60)],
}
# VREF guard: poured on both layers around the TIA input node (LMP7721 datasheet 10.1)
# The finger at the right wraps the BNC centre pin between its grounded shell pins.
# (cluster frame, mapped like the parts)
GUARD = [CL(x, y) for x, y in [(12.60, 1.60), (25.20, 1.60), (25.20, 13.30), (28.00, 13.30),
                               (28.00, 16.90), (25.20, 16.90), (25.20, 21.30), (12.60, 21.30)]]
# Nets at the TIA input potential, and nets allowed near them (guard + feedback, whose
# leakage only adds in parallel with the feedback resistor).  Every other net keeps
# SENS_HALO mm away from sensitive copper: enforced by the router, verified by check_guard.py.
SENS_NETS = {"/BNC_IN", "/DET_IN", "/TIA_IN", "/TIA_REF"}
NEAR_OK = SENS_NETS | {"/VREF", "/TIA_OUT", "/RF_2M2", "/RF_100M"}
SENS_HALO = 1.2

# nets routed in this order; GND is handled by planes + via stubs
ROUTE_ORDER = [
    "/BNC_IN", "/TIA_IN", "/DET_IN", "/TIA_REF", "/RF_2M2", "/RF_100M", "/TIA_OUT", "/ADC_IN",
    "/VREF", "/VREF_BUF", "/VREF_DIV", "/AIN1", "/DAC_OUT", "/BUF_OUT", "/QPS_OUT", "/AIN2",
    "/AIN3", "/RDY", "/SDA", "/SCL", "/TRIG", "/TRIG_EXT", "+5V",
]


# ------------------------------------------------------------------ helpers
def load_fp(lib_fp):
    lib, name = lib_fp.split(":")
    return pcbnew.FootprintLoad(os.path.join(FPROOT, lib + ".pretty"), name)


def orient(fp, pad_from, pad_to, want):
    """Rotate fp so the vector pad_from->pad_to points along want=(dx,dy)."""
    for deg in (0, 90, 180, 270):
        fp.SetOrientationDegrees(deg)
        a = fp.FindPadByNumber(pad_from).GetPosition()
        b = fp.FindPadByNumber(pad_to).GetPosition()
        dx, dy = b.x - a.x, b.y - a.y
        if dx * want[0] + dy * want[1] > 0 and abs(dx * want[1] - dy * want[0]) <= MM(0.01):
            return deg
    raise RuntimeError("cannot orient %s" % fp.GetReference())


def netinfo(board, cache, name):
    if name not in cache:
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        cache[name] = ni
    return cache[name]


def polygon_zone(board, pts, layer, net=None, rule_area=False, name="", priority=0, hole=None):
    z = pcbnew.ZONE(board)
    if rule_area:
        z.SetIsRuleArea(True)
        z.SetDoNotAllowTracks(True); z.SetDoNotAllowVias(True); z.SetDoNotAllowPads(True)
        z.SetDoNotAllowZoneFills(True); z.SetDoNotAllowFootprints(True)
    z.SetLayer(layer)
    if name:
        z.SetZoneName(name)
    if net is not None:
        z.SetNet(net)
        z.SetAssignedPriority(priority)
        z.SetLocalClearance(MM(ZONE_CLEAR))
        z.SetMinThickness(MM(0.2))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)   # SMD solid, THT thermal
        z.SetThermalReliefGap(MM(0.3))
        z.SetThermalReliefSpokeWidth(MM(0.35))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    o = z.Outline()
    o.NewOutline()
    for x, y in pts:
        o.Append(MM(OX + x), MM(OY - y))
    if hole:
        hi = o.NewHole()                      # explicit (outline 0, hole hi): plain Append
        for x, y in hole:                     # would extend the outer outline instead
            o.Append(MM(OX + x), MM(OY - y), 0, hi)
    board.Add(z)
    return z


# From the UNO footprint's own fab outline (= A000066 drawing): vertical to y 0, then the chamfer.
BOARD_PTS = [(-27.94, -2.54), (38.10, -2.54), (38.10, 0.00), (40.64, 2.54), (40.64, 35.31),
             (38.10, 37.85), (38.10, 49.28), (36.58, 50.80), (-27.94, 50.80)]


def outline(board):
    for a, b in zip(BOARD_PTS, BOARD_PTS[1:] + BOARD_PTS[:1]):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(P(*a)); s.SetEnd(P(*b))
        s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(MM(0.1))
        board.Add(s)


def poly_mask(xs, ys, pts):
    """Vectorised point-in-polygon over the grid."""
    inside = np.zeros(xs.shape, bool)
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        if y1 == y2:
            continue
        cond = (y1 > ys) != (y2 > ys)
        xint = (x2 - x1) * (ys - y1) / (y2 - y1) + x1
        inside ^= cond & (xs < xint)
    return inside


# ------------------------------------------------------------------ router
G = 0.1                                   # grid pitch, mm
X0, Y0 = -28.00, -2.60                    # on the 0.1 mm grid, so 0.5 mm-pitch pads land on cells
NX = int(round((40.70 - X0) / G)) + 1
NY = int(round((50.90 - Y0) / G)) + 1
FREE, BLOCK = -1, -2


class Router:
    """Two-layer grid router.  trk[l][i,j] says which net may put a track
    centreline in that cell (FREE = anyone, BLOCK = nobody); via[i,j] the same
    for a via centre.  Committed copper stamps its clearance halo with its net."""

    def __init__(self):
        self.sens_ids, self.nearok_ids = set(), set()
        self.senszone = [np.zeros((NX, NY), bool) for _ in range(2)]
        self.trk = [np.full((NX, NY), FREE, np.int32) for _ in range(2)]
        self.via = np.full((NX, NY), FREE, np.int32)
        self.hard = [np.full((NX, NY), FREE, np.int32) for _ in range(2)]  # pad copper
        xs = X0 + np.arange(NX) * G
        ys = Y0 + np.arange(NY) * G
        self.XX, self.YY = np.meshgrid(xs, ys, indexing="ij")

    def cell(self, x, y):
        return int(round((x - X0) / G)), int(round((y - Y0) / G))

    def xy(self, i, j):
        return round(X0 + i * G, 4), round(Y0 + j * G, 4)

    @staticmethod
    def _stamp(arr, mask, net):
        cur = arr[mask]
        arr[mask] = np.where((cur == FREE) | (cur == net), net, BLOCK)

    def _halo(self, d, layers, net):
        if net in self.sens_ids:
            for l in layers:
                self.senszone[l] |= d <= SENS_HALO + TRACK / 2
        for l in layers:
            self._stamp(self.trk[l], d <= TRACK / 2 + CLEAR + 0.01, net)
        self._stamp(self.via, d <= VIA_D / 2 + CLEAR + 0.01, net)

    def add_rect(self, layers, cx, cy, hx, hy, net, rot=0.0):
        c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        dx, dy = self.XX - cx, self.YY - cy
        u, v = dx * c + dy * s, -dx * s + dy * c
        d = np.hypot(np.maximum(np.abs(u) - hx, 0), np.maximum(np.abs(v) - hy, 0))
        self._halo(d, layers, net)
        for l in layers:
            self.hard[l][d <= 0.0] = net

    def add_disc(self, layers, cx, cy, r, net):
        d = np.hypot(self.XX - cx, self.YY - cy) - r
        self._halo(d, layers, net)
        for l in layers:
            self.hard[l][d <= 0] = net

    def add_segment_copper(self, l, a, b, net):
        ax, ay = a; bx, by = b
        vx, vy = bx - ax, by - ay
        L2 = vx * vx + vy * vy or 1e-9
        t = np.clip(((self.XX - ax) * vx + (self.YY - ay) * vy) / L2, 0, 1)
        d = np.hypot(self.XX - (ax + t * vx), self.YY - (ay + t * vy)) - TRACK / 2
        self._halo(d, (l,), net)

    def add_via_copper(self, x, y, net):
        d = np.hypot(self.XX - x, self.YY - y) - VIA_D / 2
        self._halo(d, (0, 1), net)

    def usable(self, l, i, j, net):
        o = self.trk[l][i, j]
        return o == FREE or o == net or self.hard[l][i, j] == net

    def route(self, net, sources, targets, bottom_cost=4.0, via_cost=12.0, limit=2_000_000):
        tset = set(targets)
        if not tset:
            return None
        tl = np.array([self.xy(i, j) for (_, i, j) in tset])
        cx, cy = tl.mean(axis=0)
        rad = float(np.max(np.hypot(tl[:, 0] - cx, tl[:, 1] - cy)))
        def h(i, j):
            x, y = self.xy(i, j)
            return max(0.0, math.hypot(x - cx, y - cy) - rad) / G
        openq, came, gbest = [], {}, {}
        for s in sources:
            gbest[s] = 0.0
            heapq.heappush(openq, (h(s[1], s[2]), 0.0, s, None))
        steps = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
                 (1, 1, 1.4142), (1, -1, 1.4142), (-1, 1, 1.4142), (-1, -1, 1.4142)]
        n = 0
        trk, hard, via = self.trk, self.hard, self.via
        restricted = net not in self.nearok_ids
        sz = self.senszone
        while openq:
            f, gc, cur, par = heapq.heappop(openq)
            if cur in came:
                continue
            came[cur] = par
            if cur in tset:
                path = [cur]
                while came[path[-1]] is not None:
                    path.append(came[path[-1]])
                return path[::-1]
            n += 1
            if n > limit:
                return None
            l, i, j = cur
            lc = bottom_cost if l == 1 else 1.0
            tl_, hl_ = trk[l], hard[l]
            for di, dj, c in steps:
                ni, nj = i + di, j + dj
                if not (0 <= ni < NX and 0 <= nj < NY):
                    continue
                o = tl_[ni, nj]
                if not (o == FREE or o == net or hl_[ni, nj] == net):
                    continue
                if restricted and sz[l][ni, nj] and hl_[ni, nj] != net:
                    continue
                if di and dj:
                    o1, o2 = tl_[i + di, j], tl_[i, j + dj]
                    if not ((o1 == FREE or o1 == net or hl_[i + di, j] == net) and
                            (o2 == FREE or o2 == net or hl_[i, j + dj] == net)):
                        continue
                nxt = (l, ni, nj)
                ng = gc + c * lc
                if ng < gbest.get(nxt, 1e18):
                    gbest[nxt] = ng
                    heapq.heappush(openq, (ng + h(ni, nj), ng, nxt, cur))
            vo = via[i, j]
            if (vo == FREE or vo == net) and not (restricted and (sz[0][i, j] or sz[1][i, j])):
                nl = 1 - l
                o = trk[nl][i, j]
                if o == FREE or o == net or hard[nl][i, j] == net:
                    nxt = (nl, i, j)
                    ng = gc + via_cost
                    if ng < gbest.get(nxt, 1e18):
                        gbest[nxt] = ng
                        heapq.heappush(openq, (ng + h(i, j), ng, nxt, cur))
        return None


def simplify(path):
    """cells -> list of (layer, [cells]) runs, keeping only corner cells."""
    runs = []
    cur_l, pts = path[0][0], [path[0]]
    for c in path[1:]:
        if c[0] != cur_l:
            runs.append((cur_l, pts)); cur_l, pts = c[0], [c]
        else:
            pts.append(c)
    runs.append((cur_l, pts))
    out = []
    for l, pts in runs:
        keep = [pts[0]]
        for k in range(1, len(pts) - 1):
            a, b, c = pts[k - 1], pts[k], pts[k + 1]
            d1 = (b[1] - a[1], b[2] - a[2]); d2 = (c[1] - b[1], c[2] - b[2])
            if d1 != d2:
                keep.append(b)
        if len(pts) > 1:
            keep.append(pts[-1])
        out.append((l, keep))
    return out


# -------------------------------------------------------------------- main
def main():
    comps, padnet = read_netlist(NETLIST)
    board = pcbnew.BOARD()
    ds = board.GetDesignSettings()
    ds.SetCopperLayerCount(2)
    ds.m_TrackMinWidth = MM(0.15)
    ds.m_MinClearance = MM(0.15)
    ds.m_ViasMinSize = MM(VIA_D)
    ds.m_MinThroughDrill = MM(VIA_DRILL)
    ds.m_CopperEdgeClearance = MM(EDGE_CLEAR)
    ds.m_TentViasFront = True        # vias sit above the UNO's ICSP headers: keep them masked
    ds.m_TentViasBack = True
    nc = ds.m_NetSettings.GetDefaultNetclass()
    nc.SetClearance(MM(0.15)); nc.SetTrackWidth(MM(TRACK))   # router itself keeps CLEAR
    nc.SetViaDiameter(MM(VIA_D)); nc.SetViaDrill(MM(VIA_DRILL))
    outline(board)

    nets, fps = {}, {}
    for ref, (val, fpname, uuid, fields) in sorted(comps.items()):
        fp = load_fp(fpname)
        fp.SetFPID(pcbnew.LIB_ID(*fpname.split(":")))
        fp.SetReference(ref); fp.SetValue(val)
        for k, v in fields:                      # Rating / MPN / Digi-Key / LCSC / Note
            fp.SetField(k, v)
            fp.GetField(k).SetVisible(False)
        if uuid:   # link to the schematic symbol, so KiCad's schematic-parity check and
            fp.SetPath(pcbnew.KIID_PATH("/" + uuid))   # "Update PCB from Schematic" both work
        board.Add(fp)
        fps[ref] = fp
        for pad in fp.Pads():
            n = padnet.get((ref, pad.GetNumber()))
            if n and not n.startswith("unconnected"):
                pad.SetNet(netinfo(board, nets, n))
    missing = set(fps) - set(PLACE)
    if missing:
        sys.exit("not placed: %s" % sorted(missing))
    for ref, (x, y, rot) in PLACE.items():
        if rot is not None:
            fps[ref].SetOrientationDegrees(rot)
    orient(fps["J1"], "1", "3", (1, 0))     # BNC opening faces +x (off the right edge)
    orient(fps["J2"], "1", "2", (0, 1))     # terminal blocks: pins along y, pin 1 on top
    orient(fps["J4"], "1", "2", (0, 1))
    orient(fps["JP1"], "1", "2", (0, 1))
    orient(fps["J3"], "1", "2", (0, 1))
    orient(fps["D1"], "2", "1", (1, 0))     # VREF pins 1/2 side by side, common pin 3 up
    for ref, (x, y, rot) in PLACE.items():
        fps[ref].SetPosition(P(x, y))
    # The library UNO footprint is a back view: mirror it top/bottom about its pad 1.
    fps["A1"].Flip(P(0, 0), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)
    # BNC mounting pegs are unnumbered pads with no schematic pin; they stay unconnected
    # (netting them would break schematic parity).  The shell reaches GND via pins 2-4.
    # BNC shell pins: solid to the ground planes (the guard finger leaves room for one spoke only)
    for pad in fps["J1"].Pads():
        if pad.GetNumber() in ("2", "3", "4"):
            pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
    # The UNO footprint draws the whole Uno (silk + courtyard); the Uno is under the
    # shield, not on it, so only its header pads matter.  Silk is dropped, the courtyard
    # is parked on User.1 for reference.
    for g in list(fps["A1"].GraphicalItems()):
        if g.GetClass() != "PCB_SHAPE":
            continue
        if g.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            g.SetLayer(pcbnew.User_2)
        elif g.GetLayer() in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
            g.SetLayer(pcbnew.User_1)
    # ---- silkscreen: refs of machine-placed SMD parts go to the fab (assembly) layer;
    # hand-soldered connectors keep a readable ref and get plain-language labels.
    HAND = {"J1", "J2", "J3", "J4", "JP1"}
    for ref, fp in fps.items():
        rf, vf = fp.Reference(), fp.Value()
        vf.SetVisible(False)
        if ref == "A1":
            rf.SetVisible(False)
        elif ref not in HAND:
            rf.SetLayer(pcbnew.F_Fab)
        else:
            rf.SetTextSize(pcbnew.VECTOR2I(MM(1.0), MM(1.0))); rf.SetTextThickness(MM(0.15))
    # silkscreen positions: cluster items in the cluster frame (CL), the rest in Uno coordinates
    REFPOS = {"J1": CL(37.0, 25.2), "J2": (-19.4, 18.3), "J4": (-19.4, 27.1),
              "JP1": CL(18.4, 5.54), "J3": (-1.6, 10.6)}
    # connector outlines that cross the board edge (the parts overhang it on purpose) -> fab layer
    for ref in ("J1", "J2", "J4"):
        for g in list(fps[ref].GraphicalItems()):
            if g.GetClass() == "PCB_SHAPE" and g.GetLayer() == pcbnew.F_SilkS:
                bb = g.GetBoundingBox()
                x1, x2 = pcbnew.ToMM(bb.GetX()) - OX, pcbnew.ToMM(bb.GetRight()) - OX
                if x1 < -27.4 or x2 > 24.8:
                    g.SetLayer(pcbnew.F_Fab)
    for ref, (x, y) in REFPOS.items():
        fps[ref].Reference().SetPosition(P(x, y)); fps[ref].Reference().SetTextAngleDegrees(0)
        if ref == "JP1": fps[ref].Reference().SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_RIGHT)
    def silk(txt, x, y, size=1.0, angle=0, just=None):  # just: None | "left" | "right"
        s = pcbnew.PCB_TEXT(board)
        s.SetText(txt); s.SetLayer(pcbnew.F_SilkS)
        s.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size))); s.SetTextThickness(MM(0.16 * size))
        s.SetPosition(P(x, y)); s.SetTextAngleDegrees(angle)
        if just == "left":
            s.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
        elif just == "right":
            s.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_RIGHT)
        board.Add(s)
    # JLCPCB legible minimum: 1.0 mm text, 0.15 mm stroke
    for txt, (x, y), sz, ang, j in [
        ("DET IN", CL(31.8, 25.2), 1.2, 0, None),
        ("QPS OUT 0-5V", (-17.4, 19.6), 1.0, 0, "left"),
        ("OUT", (-20.0, 16.4), 1.0, 0, "left"), ("GND", (-20.0, 12.9), 1.0, 0, "left"),
        ("TRIG IN", (-17.4, 28.2), 1.0, 0, "left"),
        ("IN", (-20.0, 25.2), 1.0, 0, "left"), ("GND", (-20.0, 21.7), 1.0, 0, "left"),
        ("2M2", CL(22.3, 3.0), 1.0, 0, "left"), ("100M", CL(22.3, 8.08), 1.0, 0, "left"),
        ("VREF", CL(1.2, 21.0), 1.0, 0, "right"), ("AIN3", CL(1.2, 23.54), 1.0, 0, "right"),
        ("GND", CL(1.2, 26.08), 1.0, 0, "right"),
        ("MIE1001 Team 5 DAQ shield  rev E  2026-09", (-9.0, 37.8), 1.2, 0, "left"),
        ("ADS1115 0x48   MCP4725 0x60   RDY=D2   TRIG=D8", (-9.0, 35.6), 1.0, 0, "left"),
        ("Guard area: clean off all flux, handle by the edges", (-9.0, 33.6), 1.0, 0, "left"),
    ]:
        silk(txt, x, y, sz, ang, j)

    for i, (x, y) in enumerate(HOLES, 1):
        h = load_fp("MountingHole:MountingHole_3.2mm_M3")
        h.SetReference("H%d" % i); h.SetPosition(P(x, y)); h.SetBoardOnly(True)
        h.Reference().SetVisible(False); h.Value().SetVisible(False)
        h.SetAttributes(h.GetAttributes() | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
        board.Add(h)
        fps["H%d" % i] = h

    # ------------------------------------------------------------ router setup
    nid = {n: k for k, n in enumerate(sorted(nets))}
    R = Router()
    R.sens_ids = {nid[n] for n in SENS_NETS}
    R.nearok_ids = {nid[n] for n in NEAR_OK}
    xs, ys = R.XX, R.YY
    inside = poly_mask(xs, ys, BOARD_PTS)
    edge_d = np.full((NX, NY), 1e9)
    for (ax, ay), (bx, by) in zip(BOARD_PTS, BOARD_PTS[1:] + BOARD_PTS[:1]):
        vx, vy = bx - ax, by - ay
        t = np.clip(((xs - ax) * vx + (ys - ay) * vy) / (vx * vx + vy * vy), 0, 1)
        edge_d = np.minimum(edge_d, np.hypot(xs - (ax + t * vx), ys - (ay + t * vy)))
    bad = (~inside) | (edge_d < EDGE_CLEAR + TRACK / 2 + 0.05)
    R.trk[0][bad] = BLOCK; R.trk[1][bad] = BLOCK
    R.via[(~inside) | (edge_d < EDGE_CLEAR + VIA_D / 2 + 0.05)] = BLOCK
    for name, pts in KEEPOUT.items():
        m = poly_mask(xs, ys, pts)
        ko_d = np.full((NX, NY), 1e9)
        for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
            vx, vy = bx - ax, by - ay
            tt = np.clip(((xs - ax) * vx + (ys - ay) * vy) / (vx * vx + vy * vy), 0, 1)
            ko_d = np.minimum(ko_d, np.hypot(xs - (ax + tt * vx), ys - (ay + tt * vy)))
        R.trk[1][m | (ko_d < TRACK / 2 + 0.05)] = BLOCK
        R.via[m | (ko_d < VIA_D / 2 + 0.05)] = BLOCK
    gmask = poly_mask(xs, ys, GUARD)
    R.trk[1][gmask] = nid["/VREF"]
    near_input = np.zeros((NX, NY), bool)
    for ref, fp in fps.items():
        for pad in fp.Pads():
            if pad.GetNetname() in ("/TIA_IN", "/DET_IN", "/BNC_IN", "/TIA_REF"):
                q = pad.GetPosition()
                near_input |= np.hypot(xs - (pcbnew.ToMM(q.x) - OX), ys - (OY - pcbnew.ToMM(q.y))) < 2.0
    R.via[gmask & near_input] = nid["/VREF"]
    for ref, fp in fps.items():
        for pad in fp.Pads():
            pos = pad.GetPosition()
            cx, cy = pcbnew.ToMM(pos.x) - OX, OY - pcbnew.ToMM(pos.y)
            n = pad.GetNetname()
            net = nid.get(n, BLOCK)
            sz = pad.GetSize()
            hx, hy = pcbnew.ToMM(sz.x) / 2, pcbnew.ToMM(sz.y) / 2
            attr = pad.GetAttribute()
            tht = attr in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH)
            layers = (0, 1) if tht else (0,)
            if pad.GetShape() == pcbnew.PAD_SHAPE_CIRCLE or attr == pcbnew.PAD_ATTRIB_NPTH:
                r = max(hx, pcbnew.ToMM(pad.GetDrillSize().x) / 2)
                R.add_disc(layers, cx, cy, r, net)
            else:
                R.add_rect(layers, cx, cy, hx, hy, net, rot=-pad.GetOrientationDegrees())
            if tht:
                R.via[np.hypot(xs - cx, ys - cy) < max(hx, hy) + VIA_D / 2 + CLEAR + 0.05] = BLOCK

    padcache = {}
    def pad_cells(pad, net):
        """Grid cells inside THIS pad's copper (KiCad hit test), usable by its net."""
        key = (pad.GetParentFootprint().GetReference(), pad.GetNumber())
        if key in padcache:
            return list(padcache[key])
        pos = pad.GetPosition()
        cx, cy = pcbnew.ToMM(pos.x) - OX, OY - pcbnew.ToMM(pos.y)
        ls = (0, 1) if pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH else (0,)
        i0, j0 = R.cell(cx, cy)
        out = []
        for di in range(-14, 15):
            for dj in range(-14, 15):
                i, j = i0 + di, j0 + dj
                if not (0 <= i < NX and 0 <= j < NY):
                    continue
                x, y = R.xy(i, j)
                if pad.HitTest(P(x, y), 0):
                    for l in ls:
                        if R.trk[l][i, j] in (FREE, net) or R.hard[l][i, j] == net:
                            out.append((l, i, j))
        padcache[key] = out
        return list(out)

    netpads = {}
    for ref, fp in fps.items():
        for pad in fp.Pads():
            if pad.GetNetname() in nid:
                netpads.setdefault(pad.GetNetname(), []).append(pad)

    def commit(path, name, net):
        for l, pts in simplify(path):
            xyl = [R.xy(i, j) for (_, i, j) in pts]
            for a, b in zip(xyl, xyl[1:]):
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(P(*a)); t.SetEnd(P(*b)); t.SetWidth(MM(TRACK))
                t.SetLayer(pcbnew.F_Cu if l == 0 else pcbnew.B_Cu)
                t.SetNet(nets[name]); board.Add(t)
                R.add_segment_copper(l, a, b, net)
        for (l1, i1, j1), (l2, i2, j2) in zip(path, path[1:]):
            if l1 != l2:
                add_via(R.xy(i1, j1), name, net)

    via_at = []
    def add_via(xy, name, net):
        if any(n == name and math.hypot(xy[0] - x, xy[1] - y) < VIA_D + 0.2 for x, y, n in via_at):
            return
        via_at.append((xy[0], xy[1], name))
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(P(*xy)); v.SetWidth(MM(VIA_D)); v.SetDrill(MM(VIA_DRILL))
        v.SetNet(nets[name]); board.Add(v)
        R.add_via_copper(xy[0], xy[1], net)

    failures = []
    gnet = nid["GND"]
    def gnd_stub(pad):
        src = pad_cells(pad, gnet)
        pos = pad.GetPosition()
        i0, j0 = R.cell(pcbnew.ToMM(pos.x) - OX, OY - pcbnew.ToMM(pos.y))
        tg = []
        for di in range(-90, 91):
            for dj in range(-90, 91):
                i, j = i0 + di, j0 + dj
                if not (0 <= i < NX and 0 <= j < NY):
                    continue
                if R.via[i, j] in (FREE, gnet) and R.trk[0][i, j] in (FREE, gnet) \
                        and R.trk[1][i, j] in (FREE, gnet) and R.hard[0][i, j] != gnet:
                    tg.append((0, i, j))
        path = R.route(gnet, src, tg, bottom_cost=99, via_cost=999)
        if path is None:
            failures.append("GND via for %s.%s" % (pad.GetParentFootprint().GetReference(), pad.GetNumber()))
            return
        if len(path) > 1:
            commit(path, "GND", gnet)
        add_via(R.xy(path[-1][1], path[-1][2]), "GND", gnet)
    smd_gnd = [p for p in netpads["GND"] if p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD]
    # fine-pitch ADC and the two ground pins inside the guard get their escape first
    FIRST = ("U2", "U4", "C8")
    for pad in smd_gnd:
        if pad.GetParentFootprint().GetReference() in FIRST:
            gnd_stub(pad)
    for name in ROUTE_ORDER:
        net = nid[name]
        pads = list(netpads[name])
        tree = pad_cells(pads[0], net)
        todo = pads[1:]
        while todo:
            tx = np.mean([R.xy(c[1], c[2]) for c in tree], axis=0)
            todo.sort(key=lambda p: math.hypot(pcbnew.ToMM(p.GetPosition().x) - OX - tx[0],
                                               OY - pcbnew.ToMM(p.GetPosition().y) - tx[1]))
            pad = todo.pop(0)
            path = R.route(net, tree, pad_cells(pad, net))
            if path is None:
                failures.append("%s -> %s.%s" % (name, pad.GetParentFootprint().GetReference(), pad.GetNumber()))
                continue
            commit(path, name, net)
            tree += path
        print("routed", name, flush=True)

    # ---- GND: a short stub + via from every other SMD ground pad into the bottom plane
    for pad in smd_gnd:
        if pad.GetParentFootprint().GetReference() not in FIRST:
            gnd_stub(pad)

    # ------------------------------------------------------------ zones
    ring = [(-27.64, -2.24), (37.80, -2.24), (37.80, 0.12), (40.34, 2.66), (40.34, 35.20),
            (37.80, 37.75), (37.80, 49.15), (36.45, 50.50), (-27.64, 50.50)]
    polygon_zone(board, GUARD, pcbnew.F_Cu, nets["/VREF"], priority=2, name="guard top")
    polygon_zone(board, GUARD, pcbnew.B_Cu, nets["/VREF"], priority=2, name="guard bottom")
    # the guard area is cut out of the ground pours: no ground copper inside it at all
    polygon_zone(board, ring, pcbnew.F_Cu, nets["GND"], priority=0, name="GND top", hole=GUARD)
    polygon_zone(board, ring, pcbnew.B_Cu, nets["GND"], priority=0, name="GND bottom", hole=GUARD)
    for name, pts in KEEPOUT.items():
        polygon_zone(board, pts, pcbnew.B_Cu, rule_area=True, name=name)
    # stitching vias tie the top and bottom guard pours together
    vnet = nid["/VREF"]
    stitched = 0
    for x, y in [CL(*v) for v in [(13.8, 2.1), (24.7, 2.1), (13.8, 20.8), (24.7, 20.8), (24.7, 9.0), (13.8, 10.6)]]:
        i0, j0 = R.cell(x, y)
        spots = sorted(((di * di + dj * dj, i0 + di, j0 + dj) for di in range(-12, 13) for dj in range(-12, 13)))
        for _, i, j in spots:
            if gmask[i, j] and R.via[i, j] in (FREE, vnet) and R.trk[0][i, j] in (FREE, vnet) \
                    and R.trk[1][i, j] in (FREE, vnet):
                add_via(R.xy(i, j), "/VREF", vnet); stitched += 1
                break
    print("guard stitching vias:", stitched)

    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    board.Save(OUT)
    print("wrote", OUT)
    print("tracks+vias", len(board.GetTracks()))
    if failures:
        print("UNROUTED:")
        for f in failures:
            print("  ", f)


if __name__ == "__main__":
    main()
