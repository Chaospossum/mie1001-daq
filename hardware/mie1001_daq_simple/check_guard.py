#!/usr/bin/env python3
"""Leakage check for the pA input node (run in KiCad's Python from the project folder).

Sensitive nets: everything at the preamp input potential (COAX_IN, DET_IN, TIA_IN, TIA_REF).
For every sensitive pad/track it reports
  1. every copper item of another net closer than 1.0 mm, with the measured distance and
     what it is, except guard (VREF) and the feedback nets whose leakage only adds in
     parallel with the feedback resistor (TIA_OUT);
  2. whether VREF guard copper (pour or pad) is present within 0.6 mm on that layer, i.e.
     whether the guard actually hugs it.
  3. (rev E) a bare-board flood fill: on each copper layer, starting from the copper of the input
     nets, spread through every point of the board that carries no copper.  Guard copper (VREF) is
     a wall; so are TIA_OUT and TIA_REF, which belong to the amplifier itself (leakage into them
     only adds in parallel with the feedback resistor or goes to VREF through R7, LMP7721
     datasheet 10.1).  Touching copper of ANY other net, or leaving the window around the guard,
     means there is a surface-leakage path from the input that does not cross the guard: FAIL.
     This is the check that rev D failed (a gap under U3 along TIA_OUT led to GND and +5V).
Exit status 1 if any unexpected item is closer than 1.0 mm, if any sensitive item has no guard
copper within 0.6 mm, or if the flood fill reaches another net.  Expected exceptions are listed
in ALLOWED with the reason.
Usage: check_guard.py [board.kicad_pcb]   (default: the project board)
"""
import sys
from collections import Counter

import numpy as np
import pcbnew

b = pcbnew.LoadBoard(sys.argv[1] if len(sys.argv) > 1 else "mie1001_daq_simple.kicad_pcb")
SENS = {"/COAX_IN", "/DET_IN", "/TIA_IN", "/TIA_REF"}
FEEDBACK = {"/TIA_OUT"}
GUARD = "/VREF"
# (sensitive item, other item) pairs that are fixed by a part's own geometry
ALLOWED = {}   # the SMA centre pin clears its ground pins by 1.44 mm, so no exceptions
LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)


def name(i):
    if i.GetClass() == "PAD":
        return f"{i.GetParentFootprint().GetReference()}.{i.GetNumber() or 'peg'}"
    if i.GetClass() == "PCB_VIA":
        p = i.GetPosition()
        return f"via({pcbnew.ToMM(p.x) - 100:.1f},{100 - pcbnew.ToMM(p.y):.1f})"
    if i.GetClass() == "ZONE":
        return f"zone '{i.GetZoneName()}'"
    s = i.GetStart()
    return f"track({pcbnew.ToMM(s.x) - 100:.1f},{100 - pcbnew.ToMM(s.y):.1f})"


def items():
    for t in b.GetTracks():
        yield t
    for fp in b.GetFootprints():
        for p in fp.Pads():
            yield p
    for z in b.Zones():
        if not z.GetIsRuleArea():
            yield z


def dist(shape_a, other, lyr):
    """smallest clearance (mm, 0.05 resolution) between shape_a and item other on lyr, or None if > 3 mm"""
    if other.GetClass() == "ZONE":
        polys = other.GetFilledPolysList(lyr)
        if polys.OutlineCount() == 0:
            return None
        hit = lambda c: polys.Collide(shape_a, pcbnew.FromMM(c))
    else:
        sb = other.GetEffectiveShape(lyr)
        hit = lambda c: shape_a.Collide(sb, pcbnew.FromMM(c))
    if not hit(3.0):
        return None
    lo, hi = 0.0, 3.0
    while hi - lo > 0.05:
        mid = (lo + hi) / 2
        if hit(mid):
            hi = mid
        else:
            lo = mid
    return round(hi, 2)


all_items = list(items())
sens = [i for i in all_items if i.GetNetname() in SENS]
bad = 0
unguarded = []
for s in sens:
    for lyr in LAYERS:
        if not s.IsOnLayer(lyr):
            continue
        sa = s.GetEffectiveShape(lyr)
        guard_near = False
        for o in all_items:
            if o is s or not o.IsOnLayer(lyr):
                continue
            net = o.GetNetname()
            if net in SENS or net in FEEDBACK:
                continue
            d = dist(sa, o, lyr)
            if d is None:
                continue
            if net == GUARD:
                if d <= 0.6:
                    guard_near = True
                continue
            if d < 1.0:
                key = (name(s), name(o))
                why = ALLOWED.get(key)
                tag = "ok  " if why else "FAIL"
                if not why:
                    bad += 1
                print(f"{tag} {pcbnew.LayerName(lyr):5s} {s.GetNetname():9s} {name(s):22s} "
                      f"{d:4.2f} mm from {net or '<no net>':9s} {name(o)}" + (f"   ({why})" if why else ""))
        if not guard_near and s.GetClass() != "ZONE":
            unguarded.append(f"{pcbnew.LayerName(lyr)} {s.GetNetname()} {name(s)}")
if unguarded:
    print("\nFAIL: no VREF guard copper within 0.6 mm of:")
    for u in unguarded:
        print("  ", u)
print(f"\nproximity: {len(sens)} sensitive items, {bad} unexpected neighbours closer than 1.0 mm, "
      f"{len(unguarded)} without guard within 0.6 mm")

# ------------------------------------------------------------------ 3. bare-board flood fill
FLOOD_START = {"/COAX_IN", "/DET_IN", "/TIA_IN", "/TIA_REF"}
FLOOD_OK = {GUARD, "/TIA_OUT"}          # walls that are allowed to be touched
RES = 0.04                              # mm per cell; the narrowest gap on the board is 0.30 mm
gz = [z for z in b.Zones() if not z.GetIsRuleArea() and z.GetNetname() == GUARD]
bb = gz[0].GetBoundingBox()
for z in gz[1:]:
    bb.Merge(z.GetBoundingBox())
X0, X1 = pcbnew.ToMM(bb.GetX()) - 3, pcbnew.ToMM(bb.GetRight()) + 3
Y0, Y1 = pcbnew.ToMM(bb.GetY()) - 3, pcbnew.ToMM(bb.GetBottom()) + 3
nx, ny = int((X1 - X0) / RES), int((Y1 - Y0) / RES)
XX, YY = np.meshgrid(X0 + RES * (np.arange(nx) + .5), Y0 + RES * (np.arange(ny) + .5))


def pip(poly):
    ins = np.zeros(XX.shape, bool)
    mn, mx = poly.min(0), poly.max(0)
    m = (XX >= mn[0]) & (XX <= mx[0]) & (YY >= mn[1]) & (YY <= mx[1])
    if not m.any():
        return ins
    xi, yi = XX[m], YY[m]
    r = np.zeros(xi.shape, bool)
    j = len(poly) - 1
    for i in range(len(poly)):
        (xa, ya), (xb, yb) = poly[i], poly[j]
        r ^= ((ya > yi) != (yb > yi)) & (xi < (xb - xa) * (yi - ya) / ((yb - ya) if yb != ya else 1e-12) + xa)
        j = i
    ins[m] = r
    return ins


def painted(sps):
    m = np.zeros(XX.shape, bool)
    for k in range(sps.OutlineCount()):
        for o in [sps.Outline(k)] + [sps.Hole(k, h) for h in range(sps.HoleCount(k))]:
            m ^= pip(np.array([[pcbnew.ToMM(o.CPoint(i).x), pcbnew.ToMM(o.CPoint(i).y)]
                               for i in range(o.PointCount())]))
    return m


leaks = 0
edge = pcbnew.SHAPE_POLY_SET()
b.GetBoardPolygonOutlines(edge, False)
onboard = painted(edge)
for L in LAYERS:
    lab = np.zeros(XX.shape, np.int32)
    names = {}
    def paint(net, sps):
        lab[painted(sps)] = names.setdefault(net or "<no net>", len(names) + 1)
    for z in b.Zones():
        if not z.GetIsRuleArea() and z.IsOnLayer(L):
            paint(z.GetNetname(), z.GetFilledPolysList(L))
    for it in [t for t in b.GetTracks() if t.IsOnLayer(L)] + \
              [p for f in b.GetFootprints() for p in f.Pads() if p.IsOnLayer(L)] + \
              [g for f in b.GetFootprints() for g in f.GraphicalItems() if g.GetLayer() == L]:
        s = pcbnew.SHAPE_POLY_SET()
        it.TransformShapeToPolygon(s, L, 0, pcbnew.FromMM(0.005), pcbnew.ERROR_INSIDE)
        paint(it.GetNetname() if hasattr(it, "GetNetname") else "", s)
    inv = {v: k for k, v in names.items()}
    start = np.isin(lab, [names[n] for n in FLOOD_START if n in names])
    free = (lab == 0) & onboard
    reach = start.copy()
    while True:                                   # 4-connected flood through bare board
        g = reach.copy()
        g[1:] |= reach[:-1]; g[:-1] |= reach[1:]; g[:, 1:] |= reach[:, :-1]; g[:, :-1] |= reach[:, 1:]
        g &= free | start
        if (g == reach).all():
            break
        reach = g
    ring = reach.copy()
    ring[1:] |= reach[:-1]; ring[:-1] |= reach[1:]; ring[:, 1:] |= reach[:, :-1]; ring[:, :-1] |= reach[:, 1:]
    touched = Counter(inv[v] for v in lab[ring & ~reach & (lab > 0)])
    esc = reach[0].any() or reach[-1].any() or reach[:, 0].any() or reach[:, -1].any()
    foreign = {n: c for n, c in touched.items() if n not in FLOOD_OK and n not in FLOOD_START}
    for n in foreign:
        i, j = np.argwhere(ring & ~reach & (lab == names[n]))[0]
        print(f"FAIL {pcbnew.LayerName(L)}: bare board from the input reaches {n} "
              f"(near {XX[i, j] - 100:.2f}, {100 - YY[i, j]:.2f})")
    if esc:
        print(f"FAIL {pcbnew.LayerName(L)}: bare board from the input leaves the guard window")
    leaks += len(foreign) + bool(esc)
    print(f"flood {pcbnew.LayerName(L)}: input region touches " +
          ", ".join(f"{n} ({c * RES:.1f} mm of edge)" for n, c in sorted(touched.items())) +
          ("" if foreign or esc else "  -> enclosed"))

fail = bad + len(unguarded) + leaks
print(f"\nguard check: {'PASS' if not fail else 'FAIL'}  ({bad} close neighbours, "
      f"{len(unguarded)} unguarded items, {leaks} leakage paths)")
sys.exit(1 if fail else 0)
