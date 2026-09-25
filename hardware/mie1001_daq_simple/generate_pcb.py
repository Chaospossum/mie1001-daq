#!/usr/bin/env python3
"""Generate the SIMPLE MIE1001 Team 5 DAQ shield PCB (through-hole only, breakouts plug in).

Run inside KiCad's Python (flatpak), after the schematic:
    flatpak run --command=kicad-cli org.kicad.KiCad sch export netlist \\
        --format kicadsexpr -o build/net.net mie1001_daq_simple.kicad_sch
    flatpak run --command=python3 org.kicad.KiCad generate_pcb.py

Reuses the UNO geometry (real orientation, flipped library footprint), keep-outs and the grid
router of ../mie1001_daq_board/generate_pcb.py.  Coordinates are Uno coordinates: mm from the
power-header NC pin, y UP as seen from the top.  This script OVERWRITES the .kicad_pcb.
"""
import math
import os
import sys

import numpy as np
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "mie1001_daq_board"))
import generate_pcb as gp          # noqa: E402  (UNO outline, P(), router, helpers)

# amateur-friendly rules: fat tracks, wide gaps, big vias (JLCPCB minimum is 0.127/0.127/0.3)
gp.TRACK, gp.CLEAR, gp.VIA_D, gp.VIA_DRILL, gp.EDGE_CLEAR = 0.50, 0.30, 0.80, 0.40, 0.50
DRC_CLEAR = gp.CLEAR
gp.CLEAR = 0.36        # the router checks a 0.1 mm grid (a diagonal step cuts corners): aim wide of the 0.30 mm rule
MM, P = gp.MM, gp.P
NETLIST = os.path.join(HERE, "build", "net.net")
OUT = os.path.join(HERE, "mie1001_daq_simple.kicad_pcb")

PLACE = {   # ref: (x, y, rotation or None if oriented below)
    "ARD1": (0.00, 0.00, 0),
    "U1": (-12.00, 12.00, None),   # ADS1115 breakout socket, pin 1 (VDD) at the left, row along +x
    "U2": (19.50, 33.00, None),    # MCP4725 breakout socket, pin 1 (OUT) at the top, column down
    "J1": (-24.30, 16.40, None),   # SIGNAL IN   (left edge, between the DC and USB jacks)
    "J3": (-24.30, 25.20, None),   # TRIG IN
    "J2": (37.00, 12.00, None),    # QPS OUT     (right edge)
    "J4": (16.00, 12.00, None),    # spare A1-A3 + GND, right of the ADS1115 row
    "R1": (-12.00, 29.60, 0),      # 1k axial on the trigger, above the ADS1115 outline
    "R2": (-12.00, 33.40, 0),      # 4k7 axial in series with SIGNAL IN, second row
    "R3": (7.00, 29.60, None),     # 100k standing pull-down on D8, pads along +x
    # clamp + filter on the ADS1115 input, in the free band under its socket (near pin A0)
    "CR1": (-2.00, 3.60, None),     # 1N4148 up to +5V   (cathode pad on the right, towards the 5V pin)
    "C1": (2.50, 3.60, None),      # 100n to GND
    "CR2": (8.00, 3.60, None),      # 1N4148 down to GND (cathode pad on the left, towards A0)
    # ---- rev D preamp, in the band under the digital header (input on the right, VREF on the left)
    "J5": (30.40, 41.00, 0),        # SMA centre pin; ground pins at +-2.54 diagonally
    "R4": (24.60, 41.00, None),     # 10k standing: pad 1 (COAX_IN, under the body) at the SMA side
    "CR3": (23.00, 37.20, 0),       # BAV199: pin 3 (DET_IN) up, pins 1/2 (VREF) down
    "R5": (18.60, 41.90, None),     # 1k DET_IN -> TIA_IN
    "U3": (14.40, 38.20, 0),        # LMP7721: IN- (8) top right, IN+ (1) top left, OUT (4) bottom left
    "C2": (14.40, 41.70, None),     # 10p feedback, just above the input pins
    "R6": (14.40, 43.60, None),     # 100M feedback
    "R7": (9.20, 40.40, None),      # 1k VREF -> IN+
    "C3": (20.00, 37.60, None),     # 100n at V+ (pin 6), outside the guard
    "R11": (9.20, 36.30, None),     # 1k output filter
    "C6": (6.40, 36.90, None),      # 1u output filter to GND
    "U4": (3.00, 41.80, 0),         # MCP6002 VREF buffer
    "R8": (0.40, 37.90, None),      # 10k +5V -> VREF_DIV
    "R9": (0.40, 36.10, None),      # 10k VREF_DIV -> GND
    "C4": (3.80, 37.00, None),      # 10u on VREF_DIV
    "R10": (1.20, 45.60, None),     # 100R buffer isolation
    "C5": (4.60, 45.60, None),      # 1u VREF reservoir
    "C7": (7.80, 43.20, None),      # 100n at the MCP6002 VDD
    "JP1": (27.40, 14.00, None),    # rev E: QPS read-back solder jumper (bridged), AIN2 left, QPS right
}
# VREF guard, poured on both layers around every node at the preamp input potential, >= 1 mm clear of
# it on all sides, with an octagon around the SMA centre pin.  The ground pours are cut out under it.
_c, _r = (30.40, 41.00), 2.30
_o = [(round(_c[0] + _r * math.cos(math.radians(a)), 3), round(_c[1] + _r * math.sin(math.radians(a)), 3))
      for a in (112.5, 67.5, 22.5, -22.5, -67.5, -112.5)]
GUARD = ([(8.40, 45.60), (26.90, 45.60), (26.90, 42.40), (_o[0][0], 42.40)] + _o +
         [(_o[-1][0], 39.60), (26.90, 39.60), (26.90, 36.30), (20.90, 36.30), (20.90, 38.20), (8.40, 38.20)])
SENS_NETS = {"/COAX_IN", "/DET_IN", "/TIA_IN", "/TIA_REF"}
NEAR_OK = SENS_NETS | {"/VREF", "/TIA_OUT"}
HOLES = [(-13.97, 0.00), (38.10, 5.08), (38.10, 33.02)]
SMD_REFS = {"R5", "R6", "R7", "R8", "R9", "R10", "R11", "C2", "C3", "C4", "C5", "C6", "C7", "CR3", "U3", "U4"}
# DET_IN and TIA_OUT are laid by hand (rev E): TIA_OUT leaves the guard on the bottom layer only
ROUTE_ORDER = ["/TIA_IN", "/TIA_REF", "/PRE_OUT", "/VREF", "/VREF_BUF",
               "/VREF_DIV", "/BUF_B",
               "/SIG_EXT", "/SIG", "/QPS", "/RDY", "/SDA", "/SCL", "/TRIG", "/TRIG_EXT", "/AIN2", "+5V", "GND"]

# breakout outlines on the silkscreen (where each board sits when plugged in)
ADS_OUTLINE = (-14.54, 9.97, 13.40, 27.24)    # 1.10" x 0.68", header 0.08" from the bottom edge
MCP_OUTLINE = (18.23, 19.03, 33.47, 34.27)   # 0.6" x 0.6"; header 0.05" in from the left edge (SparkFun .brd)


# --------------------------------------------------------------------- possum
def possum(board, cx, cy, s=1.0, w=0.20):
    """A possum in silkscreen line art, facing left, ~15 x 7 mm at s = 1."""
    def seg(a, b):
        sh = pcbnew.PCB_SHAPE(board)
        sh.SetShape(pcbnew.SHAPE_T_SEGMENT)
        sh.SetStart(P(cx + a[0] * s, cy + a[1] * s)); sh.SetEnd(P(cx + b[0] * s, cy + b[1] * s))
        sh.SetLayer(pcbnew.F_SilkS); sh.SetWidth(MM(w)); board.Add(sh)
    def poly(pts, closed=False):
        for a, b in zip(pts, pts[1:] + (pts[:1] if closed else [])):
            seg(a, b)
    def dot(x, y, r):
        sh = pcbnew.PCB_SHAPE(board)
        sh.SetShape(pcbnew.SHAPE_T_CIRCLE)
        sh.SetCenter(P(cx + x * s, cy + y * s)); sh.SetEnd(P(cx + (x + r) * s, cy + y * s))
        sh.SetLayer(pcbnew.F_SilkS); sh.SetWidth(MM(w)); sh.SetFilled(True); board.Add(sh)
    body = [(4.2 * math.cos(t), 2.4 * math.sin(t)) for t in np.linspace(0.35, 2 * math.pi - 0.2, 26)]
    poly(body)                                                       # round body
    poly([(-3.9, 1.6), (-4.6, 2.3), (-5.6, 2.0), (-7.6, 0.6), (-5.9, -0.2), (-4.1, -0.9)])  # head + snout
    poly([(-4.4, 2.2), (-4.2, 3.1), (-3.6, 2.9), (-3.7, 2.0)])      # ear
    dot(-5.4, 1.2, 0.22)                                             # eye
    dot(-7.6, 0.6, 0.30)                                             # nose
    for a, b in [((-7.3, 0.7), (-8.4, 1.1)), ((-7.3, 0.5), (-8.4, 0.2))]:
        seg(a, b)                                                    # whiskers
    for x0, x1 in [(-2.3, -2.8), (-1.0, -1.1), (1.8, 1.5), (3.0, 3.5)]:
        seg((x0, -2.1), (x1, -3.4)); seg((x1, -3.4), (x1 - 0.5, -3.4))   # legs + feet
    poly([(4.1, 0.6), (5.4, 1.0), (6.6, 0.5), (7.1, -0.6), (6.7, -1.6), (5.8, -1.7), (5.5, -1.0),
          (6.0, -0.6)])                                              # curly tail


def main():
    comps, padnet = gp.read_netlist(NETLIST)
    board = pcbnew.BOARD()
    ds = board.GetDesignSettings()
    ds.SetCopperLayerCount(2)
    ds.m_TrackMinWidth = MM(0.3); ds.m_MinClearance = MM(DRC_CLEAR)
    ds.m_ViasMinSize = MM(gp.VIA_D); ds.m_MinThroughDrill = MM(gp.VIA_DRILL)
    ds.m_CopperEdgeClearance = MM(gp.EDGE_CLEAR)
    ds.m_SilkClearance = MM(0.15)      # 0 makes a clean silk DRC meaningless
    ds.m_TentViasFront = True; ds.m_TentViasBack = True
    nc = ds.m_NetSettings.GetDefaultNetclass()
    nc.SetClearance(MM(DRC_CLEAR)); nc.SetTrackWidth(MM(gp.TRACK))
    nc.SetViaDiameter(MM(gp.VIA_D)); nc.SetViaDrill(MM(gp.VIA_DRILL))
    gp.outline(board)
    tb = board.GetTitleBlock()
    tb.SetTitle("SIMPLE DAQ shield for Arduino UNO R3 - class breakout boards + Faraday-cup preamp")
    tb.SetRevision("E"); tb.SetDate("2026-09-25")
    tb.SetCompany("MIE1001 Team 5 - Maastricht University (FSE, M4I)")

    nets, fps = {}, {}
    for ref, (val, fpname, uuid, fields) in sorted(comps.items()):
        fp = gp.load_fp(fpname)
        fp.SetFPID(pcbnew.LIB_ID(*fpname.split(":")))
        fp.SetReference(ref); fp.SetValue(val)
        if uuid:
            fp.SetPath(pcbnew.KIID_PATH("/" + uuid))
        for k, v in fields:
            fp.SetField(k, v); fp.GetField(k).SetVisible(False)
        board.Add(fp); fps[ref] = fp
        for pad in fp.Pads():
            n = padnet.get((ref, pad.GetNumber()))
            if n and not n.startswith("unconnected"):
                pad.SetNet(gp.netinfo(board, nets, n))
    for ref, (x, y, rot) in PLACE.items():
        if rot is not None:
            fps[ref].SetOrientationDegrees(rot)
    gp.orient(fps["U1"], "1", "2", (1, 0))     # screen frame: row along +x
    gp.orient(fps["U2"], "1", "2", (0, 1))     # column downwards, pin 1 on top
    gp.orient(fps["J1"], "1", "2", (0, 1))     # left-edge terminals: entry faces -x
    gp.orient(fps["J3"], "1", "2", (0, 1))
    gp.orient(fps["J2"], "1", "2", (0, -1))    # right-edge terminal: entry faces +x, pin 1 low
    gp.orient(fps["J4"], "1", "2", (1, 0))
    gp.orient(fps["R3"], "1", "2", (1, 0))
    gp.orient(fps["CR1"], "1", "2", (-1, 0))    # pad 1 = cathode -> +5V, on the right
    gp.orient(fps["CR2"], "1", "2", (1, 0))     # pad 1 = cathode -> the signal, on the left
    gp.orient(fps["C1"], "1", "2", (1, 0))
    # preamp (orient() works in KiCad's screen frame: +y is DOWN)
    gp.orient(fps["R4"], "1", "2", (-1, 0))    # pad 1 (COAX_IN) towards the SMA
    gp.orient(fps["CR3"], "1", "2", (1, 0))    # KiCad's SOT-23 has pin 3 on the side: this puts it on top
    gp.orient(fps["R5"], "1", "2", (-1, 0))    # DET_IN right, TIA_IN left
    gp.orient(fps["C2"], "2", "1", (1, 0))     # pad 1 (TIA_IN) on the right, by IN- (pin 8)
    gp.orient(fps["R6"], "2", "1", (1, 0))
    gp.orient(fps["R7"], "1", "2", (1, 0))     # VREF left, TIA_REF right (IN+)
    gp.orient(fps["C3"], "1", "2", (0, 1))     # +5V up, GND down
    gp.orient(fps["R11"], "2", "1", (1, 0))    # TIA_OUT right (pin 4), PRE_OUT left
    gp.orient(fps["C6"], "1", "2", (0, 1))     # PRE_OUT up, GND down
    gp.orient(fps["R8"], "1", "2", (1, 0))     # +5V left, VREF_DIV right
    gp.orient(fps["R9"], "2", "1", (1, 0))     # VREF_DIV right, GND left (room for its via)
    gp.orient(fps["C4"], "1", "2", (0, 1))     # VREF_DIV up, GND down
    gp.orient(fps["R10"], "1", "2", (1, 0))    # VREF_BUF left, VREF right
    gp.orient(fps["C5"], "1", "2", (1, 0))     # VREF left, GND right
    gp.orient(fps["C7"], "1", "2", (0, 1))     # +5V up, GND down
    gp.orient(fps["JP1"], "1", "2", (1, 0))    # AIN2 left, QPS right
    for ref, (x, y, rot) in PLACE.items():
        fps[ref].SetPosition(P(x, y))
    fps["ARD1"].Flip(P(0, 0), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)     # library UNO is a back view
    for pad in fps["J5"].Pads():          # SMA ground pins: solid into the pours (the guard leaves one side)
        if pad.GetNumber() == "2":
            pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
    for g in list(fps["ARD1"].GraphicalItems()):
        if g.GetClass() == "PCB_SHAPE":
            if g.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
                g.SetLayer(pcbnew.User_2)
            elif g.GetLayer() in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
                g.SetLayer(pcbnew.User_1)
    for ref in ("J1", "J2", "J3"):      # terminal outlines that cross the edge -> fab
        for g in list(fps[ref].GraphicalItems()):
            if g.GetClass() == "PCB_SHAPE" and g.GetLayer() == pcbnew.F_SilkS:
                bb = g.GetBoundingBox()
                x1, x2 = pcbnew.ToMM(bb.GetX()) - gp.OX, pcbnew.ToMM(bb.GetRight()) - gp.OX
                if x1 < -27.4 or x2 > 40.1:
                    g.SetLayer(pcbnew.F_Fab)
    for i, (x, y) in enumerate(HOLES, 1):
        h = gp.load_fp("MountingHole:MountingHole_3.2mm_M3")
        h.SetReference("H%d" % i); h.SetPosition(P(x, y)); h.SetBoardOnly(True)
        h.Reference().SetVisible(False); h.Value().SetVisible(False)
        h.SetAttributes(h.GetAttributes() | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
        board.Add(h); fps["H%d" % i] = h

    # ------------------------------------------------------------ silkscreen
    for ref, fp in fps.items():
        fp.Value().SetVisible(False)
        rf = fp.Reference()
        rf.SetTextSize(pcbnew.VECTOR2I(MM(1.2), MM(1.2))); rf.SetTextThickness(MM(0.18))
        if ref == "ARD1" or ref.startswith("H"):
            rf.SetVisible(False)
        elif ref in SMD_REFS:
            rf.SetLayer(pcbnew.F_Fab)
    def silk(txt, x, y, size=1.0, angle=0, just=None, bold=False):
        s = pcbnew.PCB_TEXT(board)
        s.SetText(txt); s.SetLayer(pcbnew.F_SilkS)
        s.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size))); s.SetTextThickness(MM((0.22 if bold else 0.16) * size))
        s.SetPosition(P(x, y)); s.SetTextAngleDegrees(angle)
        if just == "left":
            s.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
        elif just == "right":
            s.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_RIGHT)
        board.Add(s)
    def tri(tip, base_c, half, w=0.2):
        """filled pin-1 triangle: tip at the pin, base centred on base_c"""
        (tx, ty), (bx, by) = tip, base_c
        dx, dy = bx - tx, by - ty; L = math.hypot(dx, dy); nx, ny = -dy / L * half, dx / L * half
        sh = pcbnew.PCB_SHAPE(board); sh.SetShape(pcbnew.SHAPE_T_POLY)
        sh.SetPolyPoints([P(tx, ty), P(bx + nx, by + ny), P(bx - nx, by - ny)])
        sh.SetFilled(True); sh.SetLayer(pcbnew.F_SilkS); sh.SetWidth(MM(w)); board.Add(sh)
    def rect(x1, y1, x2, y2, w=0.2):
        pts = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        for a, b in zip(pts, pts[1:] + pts[:1]):
            sh = pcbnew.PCB_SHAPE(board); sh.SetShape(pcbnew.SHAPE_T_SEGMENT)
            sh.SetStart(P(*a)); sh.SetEnd(P(*b)); sh.SetLayer(pcbnew.F_SilkS); sh.SetWidth(MM(w))
            board.Add(sh)
    for ref, (x, y) in {"U1": (11.0, 19.0), "U2": (28.6, 24.0), "J1": (-19.6, 18.2),
                        "J3": (-19.6, 27.0), "J2": (36.4, 9.6), "J4": (19.8, 9.5), "R1": (-0.1, 29.6),
                        "R2": (-0.1, 33.4), "R3": (5.4, 31.8),
                        "CR1": (-5.8, 1.3), "C1": (3.75, 1.3), "CR2": (17.0, 3.6),
                        "J5": (36.0, 39.5), "R4": (23.3, 43.3)}.items():
        fps[ref].Reference().SetPosition(P(x, y)); fps[ref].Reference().SetTextAngleDegrees(0)
        if ref in ("CR1", "CR2", "C1", "R4"):
            fps[ref].Reference().SetTextSize(pcbnew.VECTOR2I(MM(1.0), MM(1.0)))
        if ref in ("R1", "R2", "CR2"):
            fps[ref].Reference().SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
    silk("1k", 3.0, 29.6, 1.0, just="left"); silk("4k7", 3.0, 33.4, 1.0, just="left")
    silk("100k", 10.0, 31.8, 1.0)
    tri((-12.0, 5.3), (-12.0, 4.0), 0.7)      # pin 1 (VDD) of the ADS1115 socket
    tri((19.5, 34.7), (19.5, 36.0), 0.7)      # pin 1 (OUT) of the MCP4725 socket
    rect(*ADS_OUTLINE)
    x1, y1, x2, y2 = MCP_OUTLINE          # left side = the socket's own silk; start clear of it
    for a, b in [((21.4, y2), (x2, y2)), ((x2, y2), (x2, y1)), ((x2, y1), (21.4, y1))]:
        sh = pcbnew.PCB_SHAPE(board); sh.SetShape(pcbnew.SHAPE_T_SEGMENT)
        sh.SetStart(P(*a)); sh.SetEnd(P(*b)); sh.SetLayer(pcbnew.F_SilkS); sh.SetWidth(MM(0.2))
        board.Add(sh)
    silk("ADS1115 breakout goes here", -0.6, 24.6, 1.0)
    silk("(components up)", -0.6, 22.6, 1.0)
    silk("its VDD pin on the left", -0.6, 20.6, 1.0)
    silk("MCP4725", 28.6, 30.2, 1.2, bold=True); silk("breakout", 28.6, 28.2, 1.0)
    silk("OUT pin", 27.4, 21.9, 1.0); silk("on top", 27.4, 20.3, 1.0)
    for k, name in enumerate(["VDD", "GND", "SCL", "SDA", "ADDR", "ALRT", "A0", "A1", "A2", "A3"]):
        silk(name, -12.0 + 2.54 * k, 7.9, 1.0, angle=90)
    for k, name in enumerate(["OUT", "GND", "SCL", "SDA", "VCC", "GND"]):
        silk(name, 16.9, 33.0 - 2.54 * k, 1.0, just="right")
    for k, name in enumerate(["PRE", "A2", "VREF", "GND"]):
        silk(name, 16.0 + 2.54 * k, 15.4, 1.0, angle=90)
    silk("SIGNAL IN", -15.8, 14.6, 1.0, angle=90)
    silk("IN", -20.2, 16.4, 1.0, just="left"); silk("GND", -20.2, 12.9, 1.0, just="left")
    silk("TRIG IN", -15.8, 23.4, 1.0, angle=90)
    silk("IN", -20.2, 25.2, 1.0, just="left"); silk("GND", -20.2, 21.7, 1.0, just="left")
    silk("QPS OUT", 33.4, 17.2, 1.0, just="right")
    silk("OUT", 33.4, 12.0, 1.0, just="right"); silk("GND", 33.4, 15.5, 1.0, just="right")
    silk("simple DAQ shield  rev E", -26.2, 45.4, 1.0, just="left", bold=True)
    silk("MIE1001 SUFFERING", -26.2, 43.0, 1.4, just="left", bold=True)
    silk("WE PRAY TO THE", -25.5, 40.8, 1.0, just="left")
    silk("MIGHTY MACHINE GODS", -25.5, 39.2, 1.0, just="left")
    silk("ADS 0x48  MCP 0x60", -25.5, 37.2, 1.0, just="left")
    silk("RDY->D2  TRIG->D8", -25.5, 35.6, 1.0, just="left")
    silk("N.D", -25.5, 34.0, 0.9, just="left")
    silk("DET IN", 30.4, 46.2, 1.0)
    silk("PREAMP", 14.4, 34.6, 1.0, bold=True)
    for txt, y in [("MIE1001 Team 5  simple DAQ  rev E", 26.0),
                   ("ADS 0x48  MCP 0x60  RDY->D2  TRIG->D8", 24.0),
                   ("Preamp: read A1 - A3,  1 nA = 0.1 V", 22.0),
                   ("J5 = Faraday cup (SMA).  Clean all flux", 20.0),
                   ("off the preamp guard area on both sides.", 18.4)]:
        b = pcbnew.PCB_TEXT(board)
        b.SetText(txt); b.SetLayer(pcbnew.B_SilkS); b.SetMirrored(True)
        b.SetTextSize(pcbnew.VECTOR2I(MM(1.0), MM(1.0))); b.SetTextThickness(MM(0.16))
        b.SetPosition(P(0.5, y)); board.Add(b)
    possum(board, 27.0, 5.6)
    fps["JP1"].Reference().SetPosition(P(27.4, 15.9)); fps["JP1"].Reference().SetTextAngleDegrees(0)
    fps["JP1"].Reference().SetTextSize(pcbnew.VECTOR2I(MM(0.8), MM(0.8)))
    fps["JP1"].Reference().SetTextThickness(MM(0.13))
    silk("A2=QPS", 29.75, 14.0, 0.8, angle=90)

    # ------------------------------------------------------------ router
    nid = {n: k for k, n in enumerate(sorted(nets))}
    R = gp.Router()
    R.sens_ids = {nid[n] for n in SENS_NETS}
    R.nearok_ids = {nid[n] for n in NEAR_OK}
    xs, ys = R.XX, R.YY
    inside = gp.poly_mask(xs, ys, gp.BOARD_PTS)
    edge_d = np.full((gp.NX, gp.NY), 1e9)
    for (ax, ay), (bx, by) in zip(gp.BOARD_PTS, gp.BOARD_PTS[1:] + gp.BOARD_PTS[:1]):
        vx, vy = bx - ax, by - ay
        t = np.clip(((xs - ax) * vx + (ys - ay) * vy) / (vx * vx + vy * vy), 0, 1)
        edge_d = np.minimum(edge_d, np.hypot(xs - (ax + t * vx), ys - (ay + t * vy)))
    bad = (~inside) | (edge_d < gp.EDGE_CLEAR + gp.TRACK / 2 + 0.05)
    R.trk[0][bad] = gp.BLOCK; R.trk[1][bad] = gp.BLOCK
    R.via[(~inside) | (edge_d < gp.EDGE_CLEAR + gp.VIA_D / 2 + 0.05)] = gp.BLOCK
    for name, pts in gp.KEEPOUT.items():
        m = gp.poly_mask(xs, ys, pts)
        ko = np.full((gp.NX, gp.NY), 1e9)
        for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
            vx, vy = bx - ax, by - ay
            t = np.clip(((xs - ax) * vx + (ys - ay) * vy) / (vx * vx + vy * vy), 0, 1)
            ko = np.minimum(ko, np.hypot(xs - (ax + t * vx), ys - (ay + t * vy)))
        R.trk[1][m | (ko < gp.TRACK / 2 + 0.05)] = gp.BLOCK
        R.via[m | (ko < gp.VIA_D / 2 + 0.05)] = gp.BLOCK
    gmask = gp.poly_mask(xs, ys, GUARD)
    R.trk[1][gmask] = nid["/VREF"]                    # bottom layer inside the guard: guard only
    near_input = np.zeros((gp.NX, gp.NY), bool)
    for fp in fps.values():
        for pad in fp.Pads():
            if pad.GetNetname() in SENS_NETS:
                q = pad.GetPosition()
                near_input |= np.hypot(xs - (pcbnew.ToMM(q.x) - gp.OX), ys - (gp.OY - pcbnew.ToMM(q.y))) < 2.0
    R.via[gmask & near_input] = nid["/VREF"]
    for ref, fp in fps.items():
        for pad in fp.Pads():
            q = pad.GetPosition()
            cx, cy = pcbnew.ToMM(q.x) - gp.OX, gp.OY - pcbnew.ToMM(q.y)
            net = nid.get(pad.GetNetname(), gp.BLOCK)
            sz = pad.GetSize(); hx, hy = pcbnew.ToMM(sz.x) / 2, pcbnew.ToMM(sz.y) / 2
            rot_pad = -pad.GetOrientationDegrees()
            if pad.GetShape() == pcbnew.PAD_SHAPE_CUSTOM:     # JP1: the anchor size is not the copper
                bb = pad.GetBoundingBox()
                hx, hy = pcbnew.ToMM(bb.GetWidth()) / 2, pcbnew.ToMM(bb.GetHeight()) / 2
                c = bb.GetCenter(); cx, cy = pcbnew.ToMM(c.x) - gp.OX, gp.OY - pcbnew.ToMM(c.y); rot_pad = 0
            attr = pad.GetAttribute()
            tht = attr in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH)
            layers = (0, 1) if tht else (0,)
            if pad.GetShape() == pcbnew.PAD_SHAPE_CIRCLE or attr == pcbnew.PAD_ATTRIB_NPTH:
                R.add_disc(layers, cx, cy, max(hx, pcbnew.ToMM(pad.GetDrillSize().x) / 2), net)
            else:
                R.add_rect(layers, cx, cy, hx, hy, net, rot=rot_pad)
            if tht:
                R.via[np.hypot(xs - cx, ys - cy) < max(hx, hy) + gp.VIA_D / 2 + gp.CLEAR + 0.05] = gp.BLOCK

    def pad_cells(pad, net):
        """grid cells a track of this net may start/end in: inside the pad, and for SMD pads far
        enough from the pad edge that a TRACK-wide track stays (within one grid step) on the pad"""
        q = pad.GetPosition()
        cx, cy = pcbnew.ToMM(q.x) - gp.OX, gp.OY - pcbnew.ToMM(q.y)
        i0, j0 = R.cell(cx, cy)
        smd = pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD
        ls = (0, 1) if pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH else (0,)
        sz = pad.GetSize()
        hx, hy = pcbnew.ToMM(sz.x) / 2, pcbnew.ToMM(sz.y) / 2
        rot = math.radians(pad.GetOrientationDegrees())
        mx, my = max(hx - gp.TRACK / 2, 0) + gp.G / 2 + 1e-3, max(hy - gp.TRACK / 2, 0) + gp.G / 2 + 1e-3
        out = []
        for di in range(-15, 16):
            for dj in range(-15, 16):
                i, j = i0 + di, j0 + dj
                if not (0 <= i < gp.NX and 0 <= j < gp.NY):
                    continue
                x, y = R.xy(i, j)
                if not pad.HitTest(P(x, y), 0):
                    continue
                if smd:   # pad frame: KiCad's y is down, and its rotation is counter-clockwise on screen
                    dx, dy = x - cx, -(y - cy)
                    u = dx * math.cos(rot) - dy * math.sin(rot)
                    v = dx * math.sin(rot) + dy * math.cos(rot)
                    if abs(u) > mx or abs(v) > my:
                        continue
                out += [(l, i, j) for l in ls if R.trk[l][i, j] in (gp.FREE, net) or R.hard[l][i, j] == net]
        return out

    netpads = {}
    for fp in fps.values():
        for pad in fp.Pads():
            if pad.GetNetname() in nid:
                netpads.setdefault(pad.GetNetname(), []).append(pad)
    failures = []
    via_at = []
    def add_via(xy, name, net):
        if any(n == name and math.hypot(xy[0] - x, xy[1] - y) < gp.VIA_D / 2 for x, y, n in via_at):
            return
        via_at.append((xy[0], xy[1], name))
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(P(*xy)); v.SetWidth(MM(gp.VIA_D)); v.SetDrill(MM(gp.VIA_DRILL))
        v.SetNet(nets[name]); board.Add(v); R.add_via_copper(xy[0], xy[1], net)
    def commit(path, name, net):
        for l, pts in gp.simplify(path):
            xyl = [R.xy(i, j) for (_, i, j) in pts]
            for a, b in zip(xyl, xyl[1:]):
                tr = pcbnew.PCB_TRACK(board)
                tr.SetStart(P(*a)); tr.SetEnd(P(*b)); tr.SetWidth(MM(gp.TRACK))
                tr.SetLayer(pcbnew.F_Cu if l == 0 else pcbnew.B_Cu); tr.SetNet(nets[name]); board.Add(tr)
                R.add_segment_copper(l, a, b, net)
        for (l1, i1, j1), (l2, _, _) in zip(path, path[1:]):
            if l1 != l2:
                add_via(R.xy(i1, j1), name, net)
    gnet = nid["GND"]
    def gnd_stub(pad):
        """short top-layer stub from an SMD ground pad to a via into the bottom ground pour"""
        src = pad_cells(pad, gnet)
        q = pad.GetPosition()
        i0, j0 = R.cell(pcbnew.ToMM(q.x) - gp.OX, gp.OY - pcbnew.ToMM(q.y))
        tg = []
        for di in range(-60, 61):
            for dj in range(-60, 61):
                i, j = i0 + di, j0 + dj
                if not (0 <= i < gp.NX and 0 <= j < gp.NY):
                    continue
                if R.via[i, j] in (gp.FREE, gnet) and R.trk[0][i, j] in (gp.FREE, gnet) \
                        and R.trk[1][i, j] in (gp.FREE, gnet) and R.hard[0][i, j] != gnet:
                    tg.append((0, i, j))
        path = R.route(gnet, src, tg, bottom_cost=99, via_cost=999)
        if path is None:
            failures.append("GND via for %s.%s" % (pad.GetParentFootprint().GetReference(), pad.GetNumber()))
            return
        if len(path) > 1:
            commit(path, "GND", gnet)
        add_via(R.xy(path[-1][1], path[-1][2]), "GND", gnet)
    # LMP7721 guard pins: pin 6 (V+) sits between the N/C pins 5 and 7, so a routed link from pin 5
    # would wall it in.  Tie 5 -> 7 under the chip body instead, close to the right pad row, which
    # leaves the left half under the body for TIA_OUT.  Pins 2 and 7 sit in the guard pour.
    vref = nid["/VREF"]
    u3 = {n: fps["U3"].FindPadByNumber(n).GetPosition() for n in ("2", "5", "7")}
    u3 = {n: (round(pcbnew.ToMM(q.x) - gp.OX, 4), round(gp.OY - pcbnew.ToMM(q.y), 4)) for n, q in u3.items()}
    xl = round(u3["7"][0] - 1.775, 4)
    for a, b in [(u3["5"], (xl, u3["5"][1])), ((xl, u3["5"][1]), (xl, u3["7"][1])), ((xl, u3["7"][1]), u3["7"])]:
        tr = pcbnew.PCB_TRACK(board)
        tr.SetStart(P(*a)); tr.SetEnd(P(*b)); tr.SetWidth(MM(gp.TRACK)); tr.SetLayer(pcbnew.F_Cu)
        tr.SetNet(nets["/VREF"]); board.Add(tr); R.add_segment_copper(0, a, b, vref)
    # rev E: close the guard under the chip.  A VREF bar from pin 2 to pin 7 separates the input
    # pins (1, 8) from V-, OUT and V+ (3, 4, 6); the guard pour fills everything above it.
    u3["2"] = (round(pcbnew.ToMM(fps["U3"].FindPadByNumber("2").GetPosition().x) - gp.OX, 4), u3["7"][1])
    a, b = u3["2"], (xl, u3["7"][1])
    tr = pcbnew.PCB_TRACK(board)
    tr.SetStart(P(*a)); tr.SetEnd(P(*b)); tr.SetWidth(MM(gp.TRACK)); tr.SetLayer(pcbnew.F_Cu)
    tr.SetNet(nets["/VREF"]); board.Add(tr); R.add_segment_copper(0, a, b, vref)
    netpads["/VREF"] = [p for p in netpads["/VREF"]
                        if not (p.GetParentFootprint().GetReference() == "U3" and p.GetNumber() in ("2", "5", "7"))]
    def xy(ref, n):
        q = fps[ref].FindPadByNumber(n).GetPosition()
        return (round(pcbnew.ToMM(q.x) - gp.OX, 4), round(gp.OY - pcbnew.ToMM(q.y), 4))
    def hand(name, layer, pts):
        for a, b in zip(pts, pts[1:]):
            tr = pcbnew.PCB_TRACK(board)
            tr.SetStart(P(*a)); tr.SetEnd(P(*b)); tr.SetWidth(MM(gp.TRACK)); tr.SetLayer(layer)
            tr.SetNet(nets[name]); board.Add(tr); R.add_segment_copper(0 if layer == pcbnew.F_Cu else 1, a, b, nid[name])
    # TIA_OUT (rev E): the feedback pads' side drops to the bottom layer at V1 inside the guard, runs
    # under U3 and comes up at V2 below the bar, then to pin 4 and R11.  On the top layer the TIA_OUT
    # copper inside the guard is an island, so no bare-board gap leads from the input out of the guard.
    V1, V2 = (xy("R6", "2")[0], 41.90), (13.70, 37.00)
    hand("/TIA_OUT", pcbnew.F_Cu, [xy("R6", "2"), V1])
    hand("/TIA_OUT", pcbnew.F_Cu, [xy("C2", "2"), V1])
    hand("/TIA_OUT", pcbnew.B_Cu, [V1, (V1[0], 37.76), V2])
    hand("/TIA_OUT", pcbnew.F_Cu, [V2, (13.00, xy("U3", "4")[1]), xy("U3", "4"), xy("R11", "1")])
    add_via(V1, "/TIA_OUT", nid["/TIA_OUT"]); add_via(V2, "/TIA_OUT", nid["/TIA_OUT"])
    # DET_IN (rev E): two straight runs, so the guard pour hugs them (rev D left a pocket at R4)
    d0, r4 = xy("CR3", "3"), xy("R4", "2")
    hand("/DET_IN", pcbnew.F_Cu, [d0, (r4[0], d0[1] - (r4[0] - d0[0])), r4])
    r5 = xy("R5", "1")
    hand("/DET_IN", pcbnew.F_Cu, [r4, (r4[0] - (r5[1] - r4[1]), r5[1]), r5])
    # COAX_IN: one straight track from R4 to the SMA centre, midway between the SMA's ground pins
    cin = nid["/COAX_IN"]
    ends = [fps[r].FindPadByNumber("1").GetPosition() for r in ("R4", "J5")]
    a, b = [(round(pcbnew.ToMM(q.x) - gp.OX, 4), round(gp.OY - pcbnew.ToMM(q.y), 4)) for q in ends]
    tr = pcbnew.PCB_TRACK(board)
    tr.SetStart(P(*a)); tr.SetEnd(P(*b)); tr.SetWidth(MM(gp.TRACK)); tr.SetLayer(pcbnew.F_Cu)
    tr.SetNet(nets["/COAX_IN"]); board.Add(tr); R.add_segment_copper(0, a, b, cin)
    smd_gnd = [p for p in netpads["GND"] if p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD]
    for pad in smd_gnd:        # every SMD ground via before the signals (rev E: R9's got boxed in)
        gnd_stub(pad)
    for name in ROUTE_ORDER:
        if name == "GND":
            continue            # through-hole GND pins: the two ground pours; SMD ones: stubs below
        net = nid[name]
        pads = list(netpads[name])
        tree = pad_cells(pads[0], net)
        for pad in sorted(pads[1:], key=lambda p: p.GetPosition().x):
            path = R.route(net, tree, pad_cells(pad, net), bottom_cost=3.0)
            if path is None:
                failures.append("%s -> %s.%s" % (name, pad.GetParentFootprint().GetReference(), pad.GetNumber()))
                continue
            commit(path, name, net)
            tree += path
        print("routed", name, flush=True)

    ring = [(-27.54, -2.14), (37.70, -2.14), (37.70, 0.16), (40.24, 2.70), (40.24, 35.14),
            (37.70, 37.68), (37.70, 49.12), (36.42, 50.40), (-27.54, 50.40)]
    gp.polygon_zone(board, GUARD, pcbnew.F_Cu, nets["/VREF"], priority=2, name="guard top")
    gp.polygon_zone(board, GUARD, pcbnew.B_Cu, nets["/VREF"], priority=2, name="guard bottom")
    gp.polygon_zone(board, ring, pcbnew.F_Cu, nets["GND"], name="GND top", hole=GUARD)
    gp.polygon_zone(board, ring, pcbnew.B_Cu, nets["GND"], name="GND bottom", hole=GUARD)
    vnet = nid["/VREF"]
    stitched = 0
    for x, y in [(9.2, 45.0), (26.0, 45.0), (25.9, 37.4), (9.4, 38.9), (20.2, 44.8)]:
        i0, j0 = R.cell(x, y)
        spots = sorted(((di * di + dj * dj, i0 + di, j0 + dj) for di in range(-10, 11) for dj in range(-10, 11)))
        for _, i, j in spots:
            if gmask[i, j] and R.via[i, j] in (gp.FREE, vnet) and R.trk[0][i, j] in (gp.FREE, vnet) \
                    and R.trk[1][i, j] in (gp.FREE, vnet):
                add_via(R.xy(i, j), "/VREF", vnet); stitched += 1
                break
    print("guard stitching vias:", stitched)
    for name, pts in gp.KEEPOUT.items():
        gp.polygon_zone(board, pts, pcbnew.B_Cu, rule_area=True, name=name)
    board.BuildConnectivity()      # island removal needs this, or it deletes every pour
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    # rev E: no solder mask on the guard (LMP7721 datasheet 10.1).  Opening = guard fill shrunk by
    # 0.10 mm, and at least 0.50 mm away from any pad and 0.40 mm from any track/via of another net,
    # so the mask still covers every other track, every gap next to the guard and the edge of the
    # GND pour: exposed guard copper never faces exposed copper of another net across < 0.4 mm of mask.
    err = MM(0.005)
    mask_area = 0.0
    for z in board.Zones():
        if z.GetZoneName() not in ("guard top", "guard bottom"):
            continue
        L = z.GetLayer(); ML = pcbnew.F_Mask if L == pcbnew.F_Cu else pcbnew.B_Mask
        SL = pcbnew.F_SilkS if L == pcbnew.F_Cu else pcbnew.B_SilkS
        opening = z.GetFilledPolysList(L).CloneDropTriangulation()
        opening.Deflate(MM(0.10), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, err)
        keep = pcbnew.SHAPE_POLY_SET()
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                if pad.IsOnLayer(L) and pad.GetNetname() != "/VREF":
                    pad.TransformShapeToPolygon(keep, L, MM(0.50), err, pcbnew.ERROR_OUTSIDE)
            for g in fp.GraphicalItems():
                if g.GetLayer() == L:
                    g.TransformShapeToPolygon(keep, L, MM(0.50), err, pcbnew.ERROR_OUTSIDE)
                if g.GetLayer() == SL:
                    g.TransformShapeToPolygon(keep, SL, MM(0.20), err, pcbnew.ERROR_OUTSIDE)
            for fld in fp.GetFields():
                if fld.GetLayer() == SL and fld.IsVisible():
                    fld.TransformShapeToPolygon(keep, SL, MM(0.20), err, pcbnew.ERROR_OUTSIDE)
        for d in board.GetDrawings():         # silkscreen stays on mask: never print it on bare copper
            if d.GetLayer() == SL:
                d.TransformShapeToPolygon(keep, SL, MM(0.20), err, pcbnew.ERROR_OUTSIDE)
        for t in board.GetTracks():
            if t.IsOnLayer(L) and t.GetNetname() != "/VREF":
                t.TransformShapeToPolygon(keep, L, MM(0.40), err, pcbnew.ERROR_OUTSIDE)
        opening.BooleanSubtract(keep)
        opening.Deflate(MM(0.10), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, err)    # drop slivers
        opening.Inflate(MM(0.10), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, err)
        opening.Fracture()
        for k in range(opening.OutlineCount()):
            one = pcbnew.SHAPE_POLY_SET(); one.AddOutline(opening.Outline(k))
            sh = pcbnew.PCB_SHAPE(board); sh.SetShape(pcbnew.SHAPE_T_POLY)
            sh.SetPolyShape(one); sh.SetFilled(True); sh.SetWidth(0); sh.SetLayer(ML); board.Add(sh)
        mask_area += opening.Area() / 1e12
    print("guard mask openings: %.1f mm2" % mask_area)
    board.Save(OUT)
    print("wrote", OUT, "tracks+vias", len(board.GetTracks()))
    if failures:
        print("UNROUTED:"); [print("  ", f) for f in failures]


if __name__ == "__main__":
    main()
