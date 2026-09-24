#!/usr/bin/env python3
"""Leakage check for the pA input node (run in KiCad's Python from the project folder).

Sensitive nets: everything at the TIA input potential (BNC_IN, DET_IN, TIA_IN, TIA_REF).
For every sensitive pad/track it reports
  1. every copper item of another net closer than 1.0 mm, with the measured distance and
     what it is, except guard (VREF) and the feedback nets whose leakage only adds in
     parallel with the feedback resistor (TIA_OUT, RF_2M2, RF_100M);
  2. whether VREF guard copper (pour or pad) is present within 0.6 mm on that layer, i.e.
     whether the guard actually hugs it.
Exit status 1 if any unexpected item is closer than 1.0 mm.  Expected exceptions are
listed in ALLOWED with the reason.
"""
import sys

import pcbnew

b = pcbnew.LoadBoard("mie1001_daq_board.kicad_pcb")
SENS = {"/BNC_IN", "/DET_IN", "/TIA_IN", "/TIA_REF"}
FEEDBACK = {"/TIA_OUT", "/RF_2M2", "/RF_100M"}
GUARD = "/VREF"
# (sensitive item, other item) pairs that are fixed by a part's own geometry
ALLOWED = {
    ("J1.1", "J1.2"): "BNC centre pin vs its own shell pin (connector geometry, 0.94 mm)",
    ("J1.1", "J1.3"): "BNC centre pin vs its own shell pin (connector geometry)",
    ("J1.1", "J1.4"): "BNC centre pin vs its own shell pin (connector geometry)",
}
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
    print("\nno VREF guard copper within 0.6 mm (check these by eye):")
    for u in unguarded:
        print("  ", u)
print(f"\nguard check: {len(sens)} sensitive items, {bad} unexpected neighbours closer than 1.0 mm")
sys.exit(1 if bad else 0)
