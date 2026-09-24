#!/usr/bin/env python3
"""
Generate the MIE1001 Team 5 DAQ shield schematic (KiCad 8 file format, opens in KiCad 8/9/10).

The board is a shield for an Arduino UNO R3:
    detector -> BNC -> clamp -> LMP7721 TIA (range-selectable) -> RC -> ADS1115 -> I2C
    I2C -> MCP4725 -> MCP6002 buffer -> Riso -> screw terminal -> Extrel QPS mass command
    Team 4 sequencer -> screw terminal -> series R + pulldown -> UNO D8

Everything is drawn from computed pin coordinates, so wire ends always land exactly on pins.
Run:  python3 generate_schematic.py
"""
import math, uuid, os, re, csv

# ----------------------------------------------------------------------------- helpers
def U():
    return str(uuid.uuid4())

def esc(s):
    return (s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n'))

GRID = 1.27
def ongrid(v):
    return abs(round(v / GRID) * GRID - v) < 1e-6

# ----------------------------------------------------------------------------- library
# pin: (number, name, dx, dy, rot, etype)   dx/dy = connection point in symbol space (y up)
PIN_LEN = 5.08

def pin(num, name, x, y, rot, etype="passive", length=PIN_LEN, hide=False):
    return dict(num=num, name=name, x=x, y=y, rot=rot, etype=etype, length=length, hide=hide)

def pin_sexp(p):
    h = " (hide yes)" if p["hide"] else ""
    return (f'      (pin {p["etype"]} line (at {p["x"]} {p["y"]} {p["rot"]}) (length {p["length"]}){h}\n'
            f'        (name "{esc(p["name"])}" (effects (font (size 1.27 1.27))))\n'
            f'        (number "{p["num"]}" (effects (font (size 1.27 1.27)))))')

def rect(x1, y1, x2, y2, fill="background", width=0.254):
    return (f'      (rectangle (start {x1} {y1}) (end {x2} {y2})\n'
            f'        (stroke (width {width}) (type default)) (fill (type {fill})))')

def poly(pts, width=0.254, fill="none"):
    s = " ".join(f"(xy {x} {y})" for x, y in pts)
    return (f'      (polyline (pts {s})\n'
            f'        (stroke (width {width}) (type default)) (fill (type {fill})))')

LIB = {}   # name -> dict(pins=[...], graphics_by_unit={unit: [str]}, props={}, power=bool, hide_pin_numbers=bool, units=int)

def defsym(name, pins, graphics, props, power=False, hide_numbers=False, hide_names=False, name_offset=1.016):
    LIB[name] = dict(pins=pins, graphics=graphics, props=props, power=power,
                     hide_numbers=hide_numbers, hide_names=hide_names, offset=name_offset)

# ---- Arduino UNO R3 (pin numbers match Module:Arduino_UNO_R3 pads / KiCad MCU_Module symbol)
_uno_left = [
    ("15", "D0/RX", 27.94, "bidirectional"), ("16", "D1/TX", 25.4, "bidirectional"),
    ("17", "D2", 22.86, "bidirectional"), ("18", "D3", 20.32, "bidirectional"),
    ("19", "D4", 17.78, "bidirectional"), ("20", "D5", 15.24, "bidirectional"),
    ("21", "D6", 12.7, "bidirectional"), ("22", "D7", 10.16, "bidirectional"),
    ("23", "D8", 7.62, "bidirectional"), ("24", "D9", 5.08, "bidirectional"),
    ("25", "D10", 2.54, "bidirectional"), ("26", "D11", 0.0, "bidirectional"),
    ("27", "D12", -2.54, "bidirectional"), ("28", "D13", -5.08, "bidirectional"),
    ("30", "AREF", -10.16, "input"), ("2", "IOREF", -12.7, "output"),
    ("3", "~{RESET}", -15.24, "input"),
]
_uno_right = [
    ("9", "A0", 27.94, "bidirectional"), ("10", "A1", 25.4, "bidirectional"),
    ("11", "A2", 22.86, "bidirectional"), ("12", "A3", 20.32, "bidirectional"),
    ("13", "SDA/A4", 15.24, "bidirectional"), ("31", "SDA", 12.7, "bidirectional"),
    ("14", "SCL/A5", 7.62, "bidirectional"), ("32", "SCL", 5.08, "bidirectional"),
    ("5", "+5V", 0.0, "power_out"), ("4", "3V3", -2.54, "power_out"),
    ("8", "VIN", -5.08, "power_in"),
    ("6", "GND", -10.16, "power_in"), ("7", "GND", -12.7, "power_in"),
    ("29", "GND", -15.24, "power_in"),
]
uno_pins = [pin(n, nm, -22.86, y, 0, et) for n, nm, y, et in _uno_left]
uno_pins += [pin(n, nm, 22.86, y, 180, et) for n, nm, y, et in _uno_right]
uno_pins += [pin("1", "NC", -22.86, -20.32, 0, "no_connect", hide=True)]
defsym("DAQ:Arduino_UNO_R3", uno_pins,
       {1: [rect(-17.78, 31.75, 17.78, -22.86)]},
       dict(Reference="A", Value="Arduino UNO R3",
            Footprint="Module:Arduino_UNO_R3",
            Datasheet="https://docs.arduino.cc/hardware/uno-rev3",
            Description="Arduino UNO R3 host board - the shield mates with these headers"))

# ---- MCP4725 12-bit I2C DAC
defsym("DAQ:MCP4725", [
    pin("3", "VDD", -15.24, 5.08, 0, "power_in"),
    pin("4", "SDA", -15.24, 2.54, 0, "bidirectional"),
    pin("5", "SCL", -15.24, 0.0, 0, "input"),
    pin("6", "A0", -15.24, -2.54, 0, "input"),
    pin("2", "VSS", -15.24, -5.08, 0, "power_in"),
    pin("1", "VOUT", 15.24, 0.0, 180, "output"),
], {1: [rect(-10.16, 7.62, 10.16, -7.62)]},
    dict(Reference="U", Value="MCP4725A0T-E/CH",
         Footprint="Package_TO_SOT_SMD:SOT-23-6",
         Datasheet="https://ww1.microchip.com/downloads/en/DeviceDoc/22039d.pdf",
         Description="12-bit I2C DAC with EEPROM, SOT-23-6"))

# ---- ADS1115 16-bit I2C ADC   (pin ORDER chosen so ADDR and GND are adjacent -> clean tie-down)
defsym("DAQ:ADS1115", [
    pin("8", "VDD", -17.78, 6.35, 0, "power_in"),
    pin("9", "SDA", -17.78, 3.81, 0, "bidirectional"),
    pin("10", "SCL", -17.78, 1.27, 0, "input"),
    pin("2", "ALERT/RDY", -17.78, -1.27, 0, "open_collector"),
    pin("1", "ADDR", -17.78, -3.81, 0, "input"),
    pin("3", "GND", -17.78, -6.35, 0, "power_in"),
    pin("4", "AIN0", 17.78, 3.81, 180, "passive"),
    pin("5", "AIN1", 17.78, 1.27, 180, "passive"),
    pin("6", "AIN2", 17.78, -1.27, 180, "passive"),
    pin("7", "AIN3", 17.78, -3.81, 180, "passive"),
], {1: [rect(-12.7, 8.89, 12.7, -8.89)]},
    dict(Reference="U", Value="ADS1115IDGSR",
         Footprint="Package_SO:MSOP-10_3x3mm_P0.5mm",
         Datasheet="https://www.ti.com/lit/ds/symlink/ads1115.pdf",
         Description="16-bit delta-sigma ADC, 4ch, PGA, I2C, VSSOP-10"))

# ---- MCP6002 dual op-amp, 2 amplifier units + 1 power unit
#      unit geometry: IN- top, IN+ bottom (TIA convention), OUT right
_tri = [(-5.08, 5.08), (5.08, 0.0), (-5.08, -5.08), (-5.08, 5.08)]
_plus  = [poly([(-3.81, -3.175), (-2.286, -3.175)], 0.2), poly([(-3.048, -3.937), (-3.048, -2.413)], 0.2)]
_minus = [poly([(-3.81, 3.175), (-2.286, 3.175)], 0.2)]
_amp_gfx = [poly(_tri, 0.254, "background")] + _plus + _minus
_opamp_units = {  # MCP6002 SOIC-8 (DS20001733L Table 3-1): unit -> (out, in_minus, in_plus)
    1: ("1", "2", "3"), 2: ("7", "6", "5"),
}
mcp_pins, mcp_gfx = [], {}
for u, (o, im, ip) in _opamp_units.items():
    mcp_pins += [
        dict(unit=u, **pin(im, "-", -10.16, 2.54, 0, "passive")),
        dict(unit=u, **pin(ip, "+", -10.16, -2.54, 0, "passive")),
        dict(unit=u, **pin(o, "~", 10.16, 0.0, 180, "output")),
    ]
    mcp_gfx[u] = list(_amp_gfx)
mcp_pins += [
    dict(unit=3, **pin("8", "VDD", 0.0, 7.62, 270, "power_in")),
    dict(unit=3, **pin("4", "VSS", 0.0, -7.62, 90, "power_in")),
]
mcp_gfx[3] = [rect(-3.81, 2.54, 3.81, -2.54)]
defsym("DAQ:MCP6002", mcp_pins, mcp_gfx,
       dict(Reference="U", Value="MCP6002-I/SN",
            Footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
            Datasheet="https://ww1.microchip.com/downloads/en/DeviceDoc/21733j.pdf",
            Description="Dual rail-to-rail op-amp, 1 MHz, 1.8-6 V, SOIC-8"),
       name_offset=0.508)

# ---- LMP7721 electrometer op-amp (non-standard SOIC-8 pinout, TI SNOSAW6E section 5)
#      1 IN+, 2 N/C (guard), 3 V-, 4 VOUT, 5 N/C, 6 V+, 7 N/C (guard), 8 IN-
defsym("DAQ:LMP7721", [
    dict(unit=1, **pin("8", "-", -10.16, 2.54, 0, "passive")),
    dict(unit=1, **pin("1", "+", -10.16, -2.54, 0, "passive")),
    dict(unit=1, **pin("4", "~", 10.16, 0.0, 180, "output")),
    dict(unit=2, **pin("6", "V+", 0.0, 7.62, 270, "power_in", 2.54)),
    dict(unit=2, **pin("3", "V-", 0.0, -7.62, 90, "power_in", 2.54)),
    dict(unit=2, **pin("2", "GUARD", -7.62, 2.54, 0, "passive", 3.81)),
    dict(unit=2, **pin("5", "GUARD", -7.62, 0.0, 0, "passive", 3.81)),
    dict(unit=2, **pin("7", "GUARD", -7.62, -2.54, 0, "passive", 3.81)),
], {1: list(_amp_gfx), 2: [rect(-3.81, 5.08, 3.81, -5.08)]},
    dict(Reference="U", Value="LMP7721MA/NOPB",
         Footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
         Datasheet="https://www.ti.com/lit/ds/symlink/lmp7721.pdf",
         Description="3 fA input-bias electrometer op-amp, 1.8-5.5 V, SOIC-8"),
    name_offset=0.508)

# ---- BAV199 dual low-leakage clamp diode
defsym("DAQ:BAV199", [
    pin("1", "A1", -11.43, 1.27, 0), pin("2", "K2", -11.43, -1.27, 0),
    pin("3", "K1/A2", 11.43, 0.0, 180),
], {1: [rect(-6.35, 3.81, 6.35, -3.81)]},
    dict(Reference="D", Value="BAV199",
         Footprint="Package_TO_SOT_SMD:SOT-23",
         Datasheet="https://assets.nexperia.com/documents/data-sheet/BAV199.pdf",
         Description="Dual low-leakage (<5 nA) clamp diode, SOT-23"))

# ---- passives
for nm, val, fp, desc in [
    ("DAQ:R", "R", "Resistor_SMD:R_0603_1608Metric", "Resistor, 0603"),
    ("DAQ:R_1206", "R", "Resistor_SMD:R_1206_3216Metric", "Resistor, 1206"),
]:
    defsym(nm, [pin("1", "~", 0, 5.08, 270, "passive", 2.54),
                pin("2", "~", 0, -5.08, 90, "passive", 2.54)],
           {1: [rect(-1.016, 2.54, 1.016, -2.54, "none")]},
           dict(Reference="R", Value=val, Footprint=fp, Datasheet="", Description=desc),
           hide_numbers=True, name_offset=0)
for nm, fp, desc in [
    ("DAQ:C", "Capacitor_SMD:C_0603_1608Metric", "Capacitor, 0603"),
    ("DAQ:C_0805", "Capacitor_SMD:C_0805_2012Metric", "Capacitor, 0805"),
]:
    defsym(nm, [pin("1", "~", 0, 3.81, 270, "passive", 2.54),
                pin("2", "~", 0, -3.81, 90, "passive", 2.54)],
           {1: [poly([(-2.032, 0.762), (2.032, 0.762)], 0.508),
                poly([(-2.032, -0.762), (2.032, -0.762)], 0.508)]},
           dict(Reference="C", Value="C", Footprint=fp, Datasheet="", Description=desc),
           hide_numbers=True, name_offset=0)

# ---- connectors (pins on the LEFT: signal arrives from the left, body to the right)
defsym("DAQ:BNC", [pin("1", "SIG", -11.43, 1.27, 0), pin("2", "SHIELD", -11.43, -1.27, 0),
                   # pads 3 and 4 are the other two outer-contact legs: stacked on pin 2 so all three reach GND
                   pin("3", "SHIELD", -11.43, -1.27, 0, hide=True), pin("4", "SHIELD", -11.43, -1.27, 0, hide=True)],
       {1: [rect(-6.35, 3.81, 6.35, -3.81)]},
       dict(Reference="J", Value="BNC", Footprint="Connector_Coaxial:BNC_Amphenol_031-6575_Horizontal",
            Datasheet="", Description="BNC coaxial jack, horizontal PCB mount"))
defsym("DAQ:Screw_Terminal_1x02", [pin("1", "1", -11.43, 1.27, 0), pin("2", "2", -11.43, -1.27, 0)],
       {1: [rect(-6.35, 3.81, 6.35, -3.81)]},
       dict(Reference="J", Value="Screw terminal 1x02 3.5mm",
            Footprint="TerminalBlock_Phoenix:TerminalBlock_Phoenix_PT-1,5-2-3.5-H_1x02_P3.50mm_Horizontal",
            Datasheet="", Description="2-pole 3.5 mm screw terminal block (Phoenix PT 1,5/2-3,5-H)"))
defsym("DAQ:Conn_1x03", [pin("1", "1", -11.43, 2.54, 0), pin("2", "2", -11.43, 0.0, 0),
                         pin("3", "3", -11.43, -2.54, 0)],
       {1: [rect(-6.35, 5.08, 6.35, -5.08)]},
       dict(Reference="JP", Value="Header 1x03 2.54mm",
            Footprint="Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
            Datasheet="", Description="1x3 pin header, jumper-selectable"))
defsym("DAQ:Conn_1x04", [pin("1", "1", -11.43, 3.81, 0), pin("2", "2", -11.43, 1.27, 0),
                         pin("3", "3", -11.43, -1.27, 0), pin("4", "4", -11.43, -3.81, 0)],
       {1: [rect(-6.35, 6.35, 6.35, -6.35)]},
       dict(Reference="J", Value="Header 1x04 2.54mm",
            Footprint="Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
            Datasheet="", Description="1x4 pin header"))

# ---- power symbols
defsym("DAQ:+5V", [pin("1", "+5V", 0, 0, 90, "power_in", 0)],
       {1: [poly([(-0.762, 1.27), (0, 2.54)], 0.2), poly([(0, 0), (0, 2.54)], 0.2),
            poly([(0, 2.54), (0.762, 1.27)], 0.2)]},
       dict(Reference="#PWR", Value="+5V", Footprint="", Datasheet="", Description="Power symbol +5V"),
       power=True, hide_numbers=True, hide_names=True, name_offset=0)
defsym("DAQ:PWR_FLAG", [pin("1", "pwr", 0, 0, 90, "power_out", 0)],
       {1: [poly([(0, 0), (0, 1.27), (-1.016, 1.905), (0, 2.54), (1.016, 1.905), (0, 1.27)], 0.2)]},
       dict(Reference="#FLG", Value="PWR_FLAG", Footprint="", Datasheet="",
            Description="Tells ERC this net is driven"),
       power=True, hide_numbers=True, hide_names=True, name_offset=0)
defsym("DAQ:GND", [pin("1", "GND", 0, 0, 270, "power_in", 0)],
       {1: [poly([(0, 0), (0, -1.27), (1.27, -1.27), (0, -2.54), (-1.27, -1.27), (0, -1.27)], 0.2)]},
       dict(Reference="#PWR", Value="GND", Footprint="", Datasheet="", Description="Power symbol GND"),
       power=True, hide_numbers=True, hide_names=True, name_offset=0)

# ----------------------------------------------------------------------------- placement engine
SHEET_UUID = "9d1b0f1e-6a2c-4a8f-9e11-daq5000b0ard"
PROJECT = "mie1001_daq_board"

items = []          # rendered s-expressions, in file order
placed = {}         # ref -> Part

class Part:
    def __init__(self, ref, lib, x, y, rot=0, unit=1, fields=None, mirror=None,
                 ref_at=None, val_at=None, show_value=True, just=None):
        self.ref, self.lib, self.x, self.y, self.rot, self.unit = ref, lib, x, y, rot, unit
        self.mirror, self.fields = mirror, fields or {}
        self.ref_at, self.val_at, self.show_value = ref_at, val_at, show_value
        self.just = just
        d = LIB[lib]
        self.pins = {}
        for p in d["pins"]:
            if p.get("unit", 1) not in (unit, 0):
                continue
            self.pins[p["num"]] = self._abs(p["x"], p["y"])
        placed.setdefault(ref, self)

    def _abs(self, px, py):
        if self.mirror == "y":
            px = -px
        elif self.mirror == "x":
            py = -py
        r = math.radians(self.rot)
        c, s = round(math.cos(r)), round(math.sin(r))
        rx, ry = px * c - py * s, px * s + py * c
        return (round(self.x + rx, 4), round(self.y - ry, 4))

    def p(self, num):
        return self.pins[str(num)]

def place(ref, lib, x, y, rot=0, unit=1, **kw):
    part = Part(ref, lib, x, y, rot, unit, **kw)
    d = LIB[lib]
    props = dict(d["props"])
    props["Reference"] = ref
    for k, v in part.fields.items():
        props[k] = v
    rx, ry = part.ref_at or (x + 8.89, y - 2.54)
    vx, vy = part.val_at or (x + 8.89, y + 0.0)
    out = [f'  (symbol (lib_id "{lib}") (at {x} {y} {rot}){" (mirror %s)" % part.mirror if part.mirror else ""}'
           f' (unit {unit}) (exclude_from_sim no) (in_bom {"no" if d["power"] else "yes"})'
           f' (on_board yes) (dnp no)',
           f'    (uuid "{U()}")']
    order = ["Reference", "Value", "Footprint", "Datasheet", "Description",
             "Rating", "Manufacturer", "MPN", "Digi-Key P/N", "LCSC", "Note"]
    for k in order + [k for k in props if k not in order]:
        if k not in props:
            continue
        v = props[k]
        if k == "Reference":
            at, hide = (rx, ry), d["power"]
        elif k == "Value":
            at, hide = (vx, vy), (not part.show_value)
        else:
            at, hide = (x, y), True
        h = " (hide yes)" if hide else ""
        j = (f' (justify {part.just})'
             if part.just and k in ("Reference", "Value") and not hide else "")
        # cancel the symbol rotation so field text always reads left-to-right
        ang = 0 if hide else {90: 270, 270: 90}.get(rot, 0)
        out.append(f'    (property "{esc(k)}" "{esc(str(v))}" (at {at[0]} {at[1]} {ang})'
                   f' (effects (font (size 1.27 1.27)){j}{h}))')
    for num in part.pins:
        out.append(f'    (pin "{num}" (uuid "{U()}"))')
    out.append(f'    (instances (project "{PROJECT}" (path "/{SHEET_UUID}"'
               f' (reference "{ref}") (unit {unit}))))')
    out.append("  )")
    items.append("\n".join(out))
    return part

# ---- wires / labels / annotation
wire_pts = []
def wire(*pts):
    pts = [(round(a, 4), round(b, 4)) for a, b in pts]
    for a, b in zip(pts, pts[1:]):
        wire_pts.append((a, b))
        items.append(f'  (wire (pts (xy {a[0]} {a[1]}) (xy {b[0]} {b[1]}))'
                     f' (stroke (width 0) (type default)) (uuid "{U()}"))')
    return pts[-1]

def junction(*pts):
    for x, y in pts:
        items.append(f'  (junction (at {x} {y}) (diameter 0) (color 0 0 0 0) (uuid "{U()}"))')

def nc(*pts):
    for x, y in pts:
        items.append(f'  (no_connect (at {x} {y}) (uuid "{U()}"))')

def label(name, pt, rot=0, justify="left bottom"):
    items.append(f'  (label "{esc(name)}" (at {pt[0]} {pt[1]} {rot}) (fields_autoplaced yes)'
                 f' (effects (font (size 1.27 1.27)) (justify {justify})) (uuid "{U()}"))')

def text(s, x, y, size=1.27, bold=False, justify="left top"):
    b = " (bold yes)" if bold else ""
    items.append(f'  (text "{esc(s)}" (at {x} {y} 0)'
                 f' (effects (font (size {size} {size}){b}) (justify {justify})) (uuid "{U()}"))')

def block(x1, y1, x2, y2, title):
    items.append(f'  (rectangle (start {x1} {y1}) (end {x2} {y2})'
                 f' (stroke (width 0.15) (type dash)) (fill (type none)) (uuid "{U()}"))')
    text(title, x1 + 2.54, y1 + 1.27, size=1.6, bold=True)

def pwr(kind, pt, rot=0):
    """+5V / GND flag attached directly at pt."""
    place(f"#PWR{pwr.n:02d}", f"DAQ:{kind}", pt[0], pt[1], rot,
          ref_at=(pt[0], pt[1] + 3.81), val_at=(pt[0], pt[1] - 3.81 if kind == "+5V" else pt[1] + 4.6))
    pwr.n += 1
pwr.n = 1

# ----------------------------------------------------------------------------- BOM data
# Manufacturer / MPN / Digi-Key P/N for every fitted part.  Edit here, re-run, BOM follows.
BOM = {
  "A1":  ("Arduino UNO R3",   "Arduino",           "A000066",             "1050-1024-ND"),
  "U1":  ("MCP4725A0T-E/CH",  "Microchip",         "MCP4725A0T-E/CH",     "MCP4725A0T-E/CHCT-ND"),
  "U2":  ("ADS1115IDGSR",     "Texas Instruments", "ADS1115IDGSR",        "296-38849-1-ND"),
  "U3":  ("MCP6002-I/SN",     "Microchip",         "MCP6002-I/SN",        "MCP6002-I/SN-ND"),
  "U4":  ("LMP7721MA/NOPB",   "Texas Instruments", "LMP7721MA/NOPB",      "LMP7721MA/NOPB-ND"),
  "D1":  ("BAV199LT1G",       "onsemi",            "BAV199LT1G",          "BAV199LT1GOSCT-ND"),
  "J1":  ("Detector in, BNC", "Amphenol RF",       "031-6575",            "ARF2111-ND"),
  "J2":  ("QPS mass cmd out", "Phoenix Contact",   "1984617",             "277-1721-ND"),
  "J3":  ("VREF / AIN3 / GND","Sullins",           "PRPC040SAAN-RC",      "S1011EC-40-ND"),
  "J4":  ("Trigger in",       "Phoenix Contact",   "1984617",             "277-1721-ND"),
  "JP1": ("TIA range select", "Sullins",           "PRPC040SAAN-RC",      "S1011EC-40-ND"),
  "R1":  ("2M2 1% 0603",      "Yageo",             "RC0603FR-072M2L",     "YAG3329CT-ND"),
  "R2":  ("100M 1% 1206",     "Stackpole",         "HVCB1206FKC100M",     "HVCB1206FKC100MCT-ND"),
  "R3":  ("1k 1% 0603",       "Yageo",             "RC0603FR-071KL",      "311-1.00KHRCT-ND"),
  "R4":  ("1k 1% 0603",       "Yageo",             "RC0603FR-071KL",      "311-1.00KHRCT-ND"),
  "R5":  ("4k7 1% 0603",      "Yageo",             "RC0603FR-074K7L",     "311-4.70KHRCT-ND"),
  "R6":  ("4k7 1% 0603",      "Yageo",             "RC0603FR-074K7L",     "311-4.70KHRCT-ND"),
  "R7":  ("10k 1% 0603",      "Yageo",             "RC0603FR-0710KL",     "311-10.0KHRCT-ND"),
  "R8":  ("10k 1% 0603",      "Yageo",             "RC0603FR-0710KL",     "311-10.0KHRCT-ND"),
  "R9":  ("1k 1% 0603",       "Yageo",             "RC0603FR-071KL",      "311-1.00KHRCT-ND"),
  "R10": ("10k 1% 0603",      "Yageo",             "RC0603FR-0710KL",     "311-10.0KHRCT-ND"),
  "R11": ("10k 1% 0603",      "Yageo",             "RC0603FR-0710KL",     "311-10.0KHRCT-ND"),
  "R12": ("100R 1% 0603",     "Yageo",             "RC0603FR-07100RL",    "311-100HRCT-ND"),
  "R13": ("1k 1% 0603",       "Yageo",             "RC0603FR-071KL",      "311-1.00KHRCT-ND"),
  "R14": ("10k 1% 0603 anti-surge", "Panasonic",    "ERJ-PA3F1002V",       "P10KBYCT-ND"),
  "R15": ("100R 1% 0603",     "Yageo",             "RC0603FR-07100RL",    "311-100HRCT-ND"),
  "R16": ("1k 1% 0603",       "Yageo",             "RC0603FR-071KL",      "311-1.00KHRCT-ND"),
  "R17": ("1k 1% 0603",       "Yageo",             "RC0603FR-071KL",      "311-1.00KHRCT-ND"),
  "C1":  ("10pF C0G 50V 0603","Murata",            "GRM1885C1H100JA01D",  "490-1403-1-ND"),
  "C2":  ("1uF X5R 50V 0603", "Samsung",           "CL10A105KB8NNNC",     "1276-1860-1-ND"),
  "C3":  ("10uF X5R 25V 0805","Samsung",           "CL21A106KAYNNNE",     "1276-2891-1-ND"),
  "C4":  ("100nF X7R 50V 0603","Samsung",          "CL10B104KB8NNNC",     "1276-1000-1-ND"),
  "C5":  ("100nF X7R 50V 0603","Samsung",          "CL10B104KB8NNNC",     "1276-1000-1-ND"),
  "C6":  ("100nF X7R 50V 0603","Samsung",          "CL10B104KB8NNNC",     "1276-1000-1-ND"),
  "C7":  ("10uF X5R 25V 0805","Samsung",           "CL21A106KAYNNNE",     "1276-2891-1-ND"),
  "C8":  ("100nF X7R 50V 0603","Samsung",          "CL10B104KB8NNNC",     "1276-1000-1-ND"),
  "C9":  ("1uF X5R 50V 0603", "Samsung",           "CL10A105KB8NNNC",     "1276-1860-1-ND"),
  "C10": ("1uF X5R 50V 0603", "Samsung",           "CL10A105KB8NNNC",     "1276-1860-1-ND"),
}
# LCSC part numbers for JLCPCB assembly of the SMD parts (checked 2026-09-22).
# Through-hole parts (A1, J1-J4, JP1) are hand-soldered from the Digi-Key order.
LCSC = {
  "U1": "C144198", "U2": "C37593", "U3": "C116706", "U4": "C124427", "D1": "C145516",
  "R1": "C22938", "R2": "C59781", "R3": "C21190", "R4": "C21190", "R5": "C23162", "R6": "C23162",
  "R7": "C25804", "R8": "C25804", "R9": "C21190", "R10": "C25804", "R11": "C25804",
  "R12": "C22775", "R13": "C21190", "R15": "C22775", "R16": "C21190", "R17": "C21190",
  "C1": "C1634", "C2": "C15849", "C3": "C15850", "C4": "C14663", "C5": "C14663",
  "C6": "C14663", "C7": "C15850", "C8": "C14663", "C9": "C15849", "C10": "C15849",
}
NOTES = {
  "R2":  "High-value TIA feedback: guard the pads, keep them clean, no flux residue. Handling oils leak more than the resistor does.",
  "C1":  "MUST be fitted. TIA stability needs Cf >= sqrt(Cin/(2*pi*Rf*GBW)); with ~100 pF of cable, Rf = 2M2 and the LMP7721's 17 MHz GBW that is ~0.65 pF, so 10 pF has wide margin (sets a 7.2 kHz / 159 Hz pole).",
  "C2":  "Any 1 uF >=16 V X5R/X7R 0603 works; confirm JLCPCB stock of C15849 when ordering.",
  "R14": "Series protection at the BNC: anti-surge (pulse-rated, AEC-Q200) 0603, limits the current into D1. 10 uV drop per nA. HAND-SOLDER from the Digi-Key order (not in the JLC assembly files).",
  "R15": "Isolation resistor so the MCP6002 VREF buffer can drive C9.",
  "R17": "Protects the LMP7721 IN+ from transients on VREF; carries only fA.",
  "R11": "ALERT/RDY is open-drain - this pull-up is required",
  "U4": "Electrometer TIA. Guard ring (VREF) on both layers around pins 1/8 and the feedback parts, no solder mask there. Clean flux off after soldering.",
  "R12": "Isolation resistor: MCP6002 driving >100 pF of cable needs Riso (DS20001733L section 4.3).",
  "D1": "Tied to VREF, not the rails: 0 V bias means near-zero leakage into the pA node (20-50 pA per diode at 2.5 V reverse).",
}
NOTES["R2"] = ("High-value TIA feedback: guard the pads, keep them clean, no flux residue. "
               "JLC/LCSC has no HVCB stock: use Uniroyal 1206W4F1006T5E (C59781), 1% +-100 ppm/C.")

SHORT = {
  "R1": "2M2", "R2": "100M", "R3": "1k", "R4": "1k", "R5": "4k7", "R6": "4k7",
  "R7": "10k", "R8": "10k", "R9": "1k", "R10": "10k", "R11": "10k", "R12": "100R", "R13": "1k",
  "C1": "10pF", "C2": "1uF", "C3": "10uF", "C4": "100nF", "C5": "100nF",
  "C6": "100nF", "C7": "10uF", "C8": "100nF", "C9": "1uF", "C10": "1uF",
  "R14": "10k", "R15": "100R", "R16": "1k", "R17": "1k",
  "J1": "Detector in", "J2": "QPS cmd out", "J3": "VREF/AIN3",
  "J4": "Trigger in", "JP1": "Range select",
}

def F(ref, **extra):
    v, mfr, mpn, dk = BOM[ref]
    d = {"Value": SHORT.get(ref, v), "Rating": v,
         "Manufacturer": mfr, "MPN": mpn, "Digi-Key P/N": dk}
    if ref in LCSC:
        d["LCSC"] = LCSC[ref]
    if ref in NOTES:
        d["Note"] = NOTES[ref]
    d.update(extra)
    return d

# ----------------------------------------------------------------------------- sheet content
# ============================ BLOCK 1 - front end =============================
block(15.24, 19.05, 193.04, 106.68,
      "1    DETECTOR INPUT  -  PROTECTION  -  TRANSIMPEDANCE AMPLIFIER")

J1 = place("J1", "DAQ:BNC", 33.02, 69.85, fields=F("J1"),
           ref_at=(33.02, 62.23), val_at=(33.02, 64.77))
R4 = place("R4", "DAQ:R", 58.42, 68.58, 90, fields=F("R4"),
           ref_at=(58.42, 64.77), val_at=(58.42, 73.66))
D1 = place("D1", "DAQ:BAV199", 64.77, 88.9, 180, fields=F("D1"),
           ref_at=(64.77, 81.28), val_at=(64.77, 83.82))

R14 = place("R14", "DAQ:R", 46.99, 68.58, 90, fields=F("R14"),
            ref_at=(46.99, 64.77), val_at=(46.99, 73.66))
wire(J1.p(1), R14.p(1)); label("BNC_IN", (40.64, 68.58))   # series R before the clamp
wire(R14.p(2), (53.34, 68.58))
wire((53.34, 68.58), (53.34, 88.9))                 # down to the clamp
junction((53.34, 68.58))
label("DET_IN", (53.34, 78.74))
wire(J1.p(2), (44.45, 71.12), (44.45, 82.55)); pwr("GND", (44.45, 82.55))
# both outer ends of the BAV199 go to VREF: back-to-back clamp at 0 V bias (near-zero leakage)
wire(D1.p(1), (76.2, 90.17), (81.28, 90.17))
wire(D1.p(2), (76.2, 87.63), (81.28, 87.63), (81.28, 90.17))
wire((81.28, 90.17), (96.52, 90.17)); junction((81.28, 90.17), (96.52, 90.17))

U4 = place("U4", "DAQ:LMP7721", 114.3, 71.12, unit=1, fields=F("U4"),
           ref_at=(113.03, 62.23), val_at=(113.03, 64.77))
wire(R4.p(2), U4.p("8"))                            # TIA_IN into the inverting input
# LMP7721 supply + guard unit: N/C pins 2 and 7 are tied to the VREF guard (datasheet 10.1)
U4P = place("U4", "DAQ:LMP7721", 127.0, 93.98, unit=2, fields=F("U4"),
            ref_at=(132.08, 87.63), val_at=(132.08, 90.17), show_value=False)
pwr("+5V", U4P.p("6")); pwr("GND", U4P.p("3"))
wire(U4P.p("2"), (116.84, 91.44), (116.84, 96.52), U4P.p("7"))
wire(U4P.p("5"), (116.84, 93.98)); junction((116.84, 93.98))
wire((116.84, 95.25), (96.52, 95.25)); junction((116.84, 95.25), (96.52, 95.25))
text("guard = VREF", 99.06, 96.52, 1.0)
C8 = place("C8", "DAQ:C", 142.24, 93.98, fields=F("C8"), ref_at=(144.78, 92.71), val_at=(144.78, 95.25), just="left")
pwr("+5V", C8.p(1)); pwr("GND", C8.p(2))
# TIA_IN rail runs up from the inverting input and feeds JP1 pin 2 directly
wire((83.82, 68.58), (83.82, 45.72), (110.49, 45.72))
junction((83.82, 68.58))
label("TIA_IN", (83.82, 52.07))

C1 = place("C1", "DAQ:C", 93.98, 63.5, 90, fields=F("C1"),
           ref_at=(93.98, 59.69), val_at=(93.98, 67.31))
wire((83.82, 63.5), C1.p(1)); junction((83.82, 63.5))
wire(C1.p(2), (139.7, 63.5))

JP1 = place("JP1", "DAQ:Conn_1x03", 121.92, 45.72, fields=F("JP1"),
            ref_at=(121.92, 36.83), val_at=(121.92, 39.37))
R1 = place("R1", "DAQ:R", 116.84, 33.02, 90, fields=F("R1"),
           ref_at=(127.0, 30.48), val_at=(127.0, 35.56), just="left")
R2 = place("R2", "DAQ:R_1206", 116.84, 58.42, 90, fields=F("R2"),
           ref_at=(127.0, 55.88), val_at=(127.0, 60.96), just="left")
wire(JP1.p(1), (106.68, 43.18), (106.68, 33.02), R1.p(1)); label("RF_2M2", (106.68, 38.1))
wire(R1.p(2), (139.7, 33.02))
wire(JP1.p(3), (104.14, 48.26), (104.14, 58.42), R2.p(1)); label("RF_100M", (104.14, 53.34), justify="right bottom")
wire(R2.p(2), (139.7, 58.42))
wire((139.7, 33.02), (139.7, 71.12))                # TIA_OUT rail
junction((139.7, 58.42), (139.7, 63.5), (139.7, 71.12))
text("JP1  1-2 = CEM range (R1 2M2)\n       2-3 = Faraday range (R2 100M)", 143.51, 36.83, 1.0)

R3 = place("R3", "DAQ:R", 157.48, 71.12, 90, fields=F("R3"), ref_at=(157.48, 67.31), val_at=(157.48, 63.5))
C2 = place("C2", "DAQ:C", 167.64, 78.74, fields=F("C2"), ref_at=(171.45, 77.47), val_at=(171.45, 80.01), just="left")
wire(U4.p("4"), R3.p(1)); label("TIA_OUT", (146.05, 71.12))
wire(R3.p(2), (177.8, 71.12))
label("ADC_IN", (177.8, 90.17))
wire(C2.p(1), (167.64, 71.12)); junction((167.64, 71.12))
wire(C2.p(2), (167.64, 83.82)); pwr("GND", (167.64, 83.82))
text("TIA (U4 LMP7721):  Vout = VREF +/- I_det x Rf\n"
     "Rf = 2M2  ->  1.14 uA full scale (CEM),  57 pA / LSB\n"
     "Rf = 100M ->  25 nA full scale (Faraday), 1.25 pA / LSB\n"
     "C1 sets the TIA pole: 7.2 kHz on 2M2, 159 Hz on 100M\n"
     "R3/C2 = 1k/1uF anti-alias: fc = 159 Hz  (Nyquist at 860 SPS is 430 Hz)\n"
     "D1 clamps DET_IN to VREF +/- 0.6 V at zero bias", 17.78, 30.48, 1.0)

# ============================ BLOCK 5 - controller ============================
block(200.66, 19.05, 381.0, 106.68,
      "5    ARDUINO UNO R3 HOST  -  I2C BUS  -  EXTERNAL TRIGGER INPUT")

A1 = place("A1", "DAQ:Arduino_UNO_R3", 289.56, 62.23, fields=F("A1"), mirror="y",
           ref_at=(289.56, 27.94), val_at=(289.56, 96.52))

# ---- I2C escapes left, towards the ADC and the DAC -------------------------
wire(A1.p("31"), (251.46, 49.53))                    # dedicated SDA
wire((251.46, 49.53), (251.46, 101.6))               # SDA trunk down to the channel
wire(A1.p("32"), (256.54, 57.15))                    # dedicated SCL
wire((256.54, 57.15), (256.54, 99.06))               # SCL trunk
label("SDA", (251.46, 87.63)); label("SCL", (256.54, 85.09))
text("I2C uses the dedicated SDA/SCL pins only: that works on\nUNO R3/R4, Leonardo and Mega. A4/A5 stay free.",
     201.93, 41.91, 1.0)

R5 = place("R5", "DAQ:R", 245.11, 88.9, fields=F("R5"), ref_at=(238.76, 87.63),
           val_at=(238.76, 90.17), just="left")
R6 = place("R6", "DAQ:R", 262.89, 88.9, fields=F("R6"), ref_at=(265.43, 87.63),
           val_at=(265.43, 90.17), just="left")
pwr("+5V", R5.p(1)); pwr("+5V", R6.p(1))
wire(R5.p(2), (251.46, 93.98)); junction((251.46, 93.98))
wire(R6.p(2), (256.54, 93.98)); junction((256.54, 93.98))
text("I2C pull-ups for the bus (the UNO has none on SDA/SCL).",
     201.93, 103.51, 1.0)

# ---- power out of the UNO --------------------------------------------------
wire(A1.p("5"), (261.62, 62.23)); pwr("+5V", (261.62, 62.23))
for pn in ("6", "7", "29"):
    wire(A1.p(pn), (259.08, {"6": 72.39, "7": 74.93, "29": 77.47}[pn]))
wire((259.08, 72.39), (259.08, 85.09)); junction((259.08, 74.93), (259.08, 77.47))
pwr("GND", (259.08, 85.09))
place("#FLG01", "DAQ:PWR_FLAG", 264.16, 81.28, ref_at=(264.16, 77.47), val_at=(266.7, 82.55))
wire((259.08, 81.28), (264.16, 81.28)); junction((259.08, 81.28))

# ---- external trigger from Team 4 -> D8 ------------------------------------
J4 = place("J4", "DAQ:Screw_Terminal_1x02", 365.76, 55.88, fields=F("J4"),
           ref_at=(365.76, 48.26), val_at=(365.76, 50.8))
R9 = place("R9", "DAQ:R", 337.82, 54.61, 90, fields=F("R9"),
           ref_at=(337.82, 50.8), val_at=(337.82, 59.69))
R10 = place("R10", "DAQ:R", 322.58, 62.23, fields=F("R10"), ref_at=(325.12, 60.96),
            val_at=(325.12, 63.5), just="left")
wire(J4.p(1), R9.p(2)); label("TRIG_EXT", (344.17, 54.61))
wire(R9.p(1), A1.p("23")); label("TRIG", (327.66, 54.61))
wire(J4.p(2), (349.25, 57.15), (349.25, 66.04)); pwr("GND", (349.25, 66.04))
wire(R10.p(1), (322.58, 54.61)); junction((322.58, 54.61))
wire(R10.p(2), (322.58, 72.39)); pwr("GND", (322.58, 72.39))
text("J4: 1 = TRIG in (Team 4 sequencer, 3.3-5 V logic), 2 = GND.\n"
     "R9 limits fault current, R10 holds D8 low when nothing is plugged in.",
     317.5, 79.38, 1.0)

# ---- ADS1115 conversion-ready -> D2 ----------------------------------------
R11 = place("R11", "DAQ:R", 316.23, 31.75, fields=F("R11"), ref_at=(318.77, 30.48),
            val_at=(318.77, 33.02), just="left")
pwr("+5V", R11.p(1))
wire(A1.p("17"), (316.23, 39.37))
wire(R11.p(2), (316.23, 39.37))
wire((316.23, 39.37), (316.23, 110.49))              # RDY trunk down to the channel
junction((316.23, 39.37))

for pn in ("15", "16", "18", "19", "20", "21", "22", "24", "25", "26", "27", "28",
           "30", "2", "3", "9", "10", "11", "12", "13", "14", "4", "8"):
    nc(A1.p(pn))

# ============================ BLOCK 2 - VREF ==================================
block(15.24, 111.76, 107.95, 163.83, "2    MID-SUPPLY REFERENCE  (2.50 V)")

R7 = place("R7", "DAQ:R", 33.02, 127.0, fields=F("R7"), ref_at=(35.56, 125.73), val_at=(35.56, 128.27), just="left")
R8 = place("R8", "DAQ:R", 33.02, 142.24, fields=F("R8"), ref_at=(35.56, 140.97), val_at=(35.56, 143.51), just="left")
C3 = place("C3", "DAQ:C_0805", 45.72, 140.97, fields=F("C3"), ref_at=(48.26, 139.7), val_at=(48.26, 142.24), just="left")
pwr("+5V", (33.02, 116.84)); wire((33.02, 116.84), R7.p(1))
wire(R7.p(2), R8.p(1))
wire(R8.p(2), (33.02, 152.4)); pwr("GND", (33.02, 152.4))
wire((33.02, 134.62), (45.72, 134.62), C3.p(1)); junction((33.02, 134.62))
wire(C3.p(2), (45.72, 149.86)); pwr("GND", (45.72, 149.86))

U3C = place("U3", "DAQ:MCP6002", 73.66, 132.08, unit=2, fields=F("U3"),
            ref_at=(72.39, 123.19), val_at=(72.39, 125.73), show_value=False)
wire((45.72, 134.62), U3C.p("5")); junction((45.72, 134.62))
wire(U3C.p("7"), (88.9, 132.08))
wire((88.9, 132.08), (88.9, 123.19), (63.5, 123.19), U3C.p("6"))
R15 = place("R15", "DAQ:R", 96.52, 132.08, 90, fields=F("R15"),
            ref_at=(96.52, 128.27), val_at=(96.52, 136.53))
wire((88.9, 132.08), R15.p(1)); junction((88.9, 132.08)); label("VREF_BUF", (88.9, 127.0))
C9 = place("C9", "DAQ:C", 104.14, 137.16, fields=F("C9"), ref_at=(106.68, 135.89), val_at=(106.68, 138.43), just="left")
wire(C9.p(1), (104.14, 132.08)); junction((104.14, 132.08)); pwr("GND", C9.p(2))
label("VREF_DIV", (33.02, 137.16))
text("VREF = 5V x R8/(R7+R8) = 2.50 V, C3 filters USB ripple.\nU3B buffers it; R15 lets it drive C9.\nFeeds R17 -> TIA IN+, the guard, D1 and AIN1.",
     59.69, 143.51, 1.0)

# ============================ BLOCK 3 - ADC ===================================
block(110.49, 111.76, 219.71, 163.83, "3    16-BIT ADC  (ADS1115, I2C 0x48)")

U2 = place("U2", "DAQ:ADS1115", 152.4, 135.89, fields=F("U2"),
           ref_at=(152.4, 124.46), val_at=(152.4, 147.32))
C5 = place("C5", "DAQ:C", 172.72, 154.94, fields=F("C5"), ref_at=(175.26, 153.67), val_at=(175.26, 156.21), just="left")
pwr("+5V", (127.0, 121.92))
wire((127.0, 121.92), (127.0, 129.54), U2.p("8"))
pwr("+5V", C5.p(1)); pwr("GND", C5.p(2))
wire(U2.p("9"), (121.92, 132.08), (121.92, 101.6), (251.46, 101.6))
wire(U2.p("10"), (119.38, 134.62), (119.38, 99.06), (256.54, 99.06))
wire(U2.p("2"), (113.03, 137.16), (113.03, 110.49), (316.23, 110.49))
label("SDA", (200.66, 101.6)); label("SCL", (200.66, 99.06)); label("RDY", (200.66, 110.49))
wire(U2.p("1"), (130.81, 139.7), (130.81, 142.24), U2.p("3"))
wire((130.81, 142.24), (130.81, 149.86)); junction((130.81, 142.24))
pwr("GND", (130.81, 149.86))
text("ADDR -> GND sets the I2C address to 0x48.   C5 decouples U2.", 112.4, 160.02, 1.0)

J3 = place("J3", "DAQ:Conn_1x03", 207.01, 148.59, fields=F("J3"),
           ref_at=(207.01, 138.43), val_at=(207.01, 140.97))
R13 = place("R13", "DAQ:R", 180.34, 137.16, 90, fields=F("R13"),
            ref_at=(180.34, 140.97), val_at=(180.34, 143.51))
wire(U2.p("6"), R13.p(1)); label("AIN2", (171.45, 137.16))   # AIN2 reads back the QPS command
wire(R13.p(2), (186.69, 137.16)); label("QPS_OUT", (186.69, 137.16))
wire(U2.p("7"), (187.96, 139.7), (187.96, 148.59), J3.p(2)); label("AIN3", (187.96, 144.78), justify="right bottom")
wire(U2.p("4"), (177.8, 132.08), (177.8, 71.12))
wire(J3.p(3), (186.69, 151.13), (186.69, 158.75)); pwr("GND", (186.69, 158.75))

# VREF trunk: U3C in block 2 feeds the TIA in block 1 and the ADC / spare header here
wire(R15.p(2), (109.22, 132.08), (109.22, 107.95))
R17 = place("R17", "DAQ:R", 96.52, 81.28, 0, fields=F("R17"),
            ref_at=(99.06, 80.01), val_at=(99.06, 82.55), just="left")
wire((109.22, 107.95), (96.52, 107.95), R17.p(2))    # VREF up to R17; clamp and guard tap below it
wire(R17.p(1), (96.52, 73.66), U4.p("1")); label("TIA_REF", (99.06, 73.66))
wire((109.22, 107.95), (193.04, 107.95), (193.04, 146.05), J3.p(1))
junction((109.22, 107.95))
R16 = place("R16", "DAQ:R", 187.96, 134.62, 90, fields=F("R16"),
            ref_at=(187.96, 130.81), val_at=(187.96, 138.43))
C10 = place("C10", "DAQ:C", 180.34, 130.81, 180, fields=F("C10"), ref_at=(182.88, 129.54), val_at=(182.88, 132.08), just="left")
wire(U2.p("5"), R16.p(1)); label("AIN1", (172.72, 134.62))
junction(C10.p(1)); pwr("GND", C10.p(2), 180)
junction((193.04, 134.62))
label("VREF", (140.97, 107.95))

# ============================ BLOCK 4 - DAC ===================================
block(226.06, 111.76, 381.0, 163.83, "4    MASS-COMMAND DAC  (MCP4725, I2C 0x60)  AND OUTPUT BUFFER")

U1 = place("U1", "DAQ:MCP4725", 266.7, 132.08, fields=F("U1"),
           ref_at=(266.7, 121.92), val_at=(266.7, 143.51))
C4 = place("C4", "DAQ:C", 233.68, 152.4, fields=F("C4"), ref_at=(236.22, 151.13), val_at=(236.22, 153.67), just="left")
pwr("+5V", (243.84, 119.38))
wire((243.84, 119.38), (243.84, 127.0), U1.p("3"))
pwr("+5V", C4.p(1)); pwr("GND", C4.p(2))
wire(U1.p("4"), (241.3, 129.54), (241.3, 101.6)); junction((241.3, 101.6))
wire(U1.p("5"), (238.76, 132.08), (238.76, 99.06)); junction((238.76, 99.06))
wire(U1.p("6"), (247.65, 134.62), (247.65, 137.16), U1.p("2"))
wire((247.65, 137.16), (247.65, 144.78)); junction((247.65, 137.16))
pwr("GND", (247.65, 144.78))
text("A0 -> GND sets the I2C address to 0x60.", 252.73, 148.59, 1.0)

U3A = place("U3", "DAQ:MCP6002", 312.42, 132.08, unit=1, fields=F("U3"),
            ref_at=(311.15, 123.19), val_at=(311.15, 125.73), show_value=False)
wire(U1.p("1"), (292.1, 132.08), (292.1, 134.62), U3A.p("3"))
label("DAC_OUT", (285.75, 132.08))
wire(U3A.p("1"), (330.2, 132.08))
wire((330.2, 132.08), (330.2, 123.19), (302.26, 123.19), U3A.p("2")); label("BUF_OUT", (309.88, 123.19))
J2 = place("J2", "DAQ:Screw_Terminal_1x02", 361.95, 132.08, fields=F("J2"),
           ref_at=(361.95, 124.46), val_at=(361.95, 127.0))
R12 = place("R12", "DAQ:R", 337.82, 132.08, 90, fields=F("R12"),
            ref_at=(337.82, 128.27), val_at=(337.82, 137.16))
wire((330.2, 132.08), R12.p(1)); junction((330.2, 132.08))
wire(R12.p(2), (347.98, 132.08), (347.98, 130.81), J2.p(1))
label("QPS_OUT", (342.9, 132.08))
wire(J2.p(2), (345.44, 133.35), (345.44, 142.24)); pwr("GND", (345.44, 142.24))
text("U3A buffers the DAC (gain = 1) -> 0-5 V mass command. R12 isolates the cable.\n"
     "A 0-10 V Extrel command needs a separate >=12 V rail\n"
     "for U3 and gain 2 - NOT possible on the 5 V shield rail.",
     285.75, 151.13, 1.0)

# ============================ BLOCK 6 - power =================================
block(15.24, 166.37, 127.0, 217.17, "6    OP-AMP SUPPLY  -  DECOUPLING")

U3P = place("U3", "DAQ:MCP6002", 34.29, 190.5, unit=3, fields=F("U3"),
            ref_at=(41.91, 187.96), val_at=(41.91, 193.04), show_value=False)
pwr("+5V", U3P.p("8")); pwr("GND", U3P.p("4"))
C6 = place("C6", "DAQ:C", 53.34, 190.5, fields=F("C6"), ref_at=(55.88, 189.23), val_at=(55.88, 191.77), just="left")
C7 = place("C7", "DAQ:C_0805", 71.12, 190.5, fields=F("C7"), ref_at=(73.66, 189.23), val_at=(73.66, 191.77), just="left")
for c in (C6, C7):
    wire(c.p(1), (c.x, 181.61)); pwr("+5V", (c.x, 181.61))
    wire(c.p(2), (c.x, 199.39)); pwr("GND", (c.x, 199.39))

text("U3 is a dual MCP6002: A buffers the DAC, B buffers VREF.\n"
     "C4/C5/C6/C8 sit at the VDD pins of U1/U2/U3/U4,\n"
     "C7 at the 5 V entry.",
     17.78, 203.2, 1.0)

# ============================ notes ===========================================
block(132.08, 166.37, 381.0, 217.17, "DESIGN NOTES")
text(
 "1.  Board is a shield for an Arduino UNO R3.  All power comes from the UNO 5 V rail; no separate supply is fitted.\n"
 "2.  Signal chain:  detector -> J1 -> R4 + D1 clamp -> U3B TIA -> R3/C2 anti-alias -> U2 AIN0 -> I2C -> UNO -> USB.\n"
 "3.  The ADS1115 is read single-ended on AIN0 with AIN1 tied to VREF, so AIN0-AIN1 can also be read differentially.\n"
 "4.  R14 then D1 (BAV199): 10k limits discharge current, D1 clamps to VREF back-to-back.  At 0 V bias its leakage is ~0; tied to\n"
 "     GND/5V each diode would leak 20-50 pA straight into the measured current.  Do not substitute a switching diode.\n"
 "5.  ALERT/RDY is open-drain.  R11 pulls it up; firmware can use D2 as a conversion-ready interrupt instead of polling.\n"
 "6.  Trigger: Team 4's sequencer drives J4-1.  R10 keeps D8 defined when the cable is absent.\n"
 "7.  Detector dynode bias (-5 to -6 kV) comes from its own HV supply and is never wired to this board.\n"
 "8.  ADS1115 inputs must stay inside GND..VDD.  VREF at mid-supply gives 2.5 V of headroom either way, so the\n"
 "     board reads a detector that sources current (Faraday cup) or one that sinks it (CD-SEM anode) unchanged.\n"
 "9.  C1 is NOT optional.  A TIA needs Cf >= sqrt(Cin / (2*pi*Rf*GBW)): with ~100 pF of cable, LMP7721 GBW = 17 MHz\n"
 "     and Rf = 2M2 that is 0.65 pF.  C1 = 10 pF gives a 7.2 kHz (2M2) / 159 Hz (100M) pole with a wide margin.\n"
 "10. R3/C2 = 1k/1uF: 159 Hz anti-alias corner, below the 430 Hz Nyquist at 860 SPS.  1k rather than 10k keeps the\n"
 "     ADS1115 input current (~0.4 uA) from making a 4 mV offset.  Step settling ~11 ms, ~30 s per 2600-point scan.\n"
 "11. U4 is an LMP7721 (20 fA max bias): an MCP600x's ~1 pA typical bias has no max and equals one ADC count.\n"
 "12. MCP4725 powers up at mid-scale (2.5 V on the QPS).  Program its EEPROM to 0x000 once from firmware.\n"
 "13. The input sits at VREF = 2.5 V while the chamber and cable shield are at GND: insulation leakage is 2.5 pA per TOhm.\n"
 "     With PTFE cable it is ~0.03 pA and constant; the per-scan beam-off baseline removes it.  Measure it at bring-up.\n"
 "     AIN2 reads the delivered QPS voltage back, so firmware can correct for the 5 V USB rail (the DAC's reference).",
 134.62, 173.99, 1.05)

# ===================== BLOCK 7 - connector / interface summary ================
block(15.24, 222.25, 287.02, 250.19, "7    CONNECTOR AND INTERFACE SUMMARY  (hand this to Teams 3 and 4)")
text(
 "J1   BNC        centre = detector / preamp output,  shell = board GND.  HV dynode bias never touches this board.\n"
 "J2   1 = QPS_OUT  0-5 V mass command (via R12 100R), read back on AIN2   2 = GND\n"
 "J4   1 = TRIG IN, Team 4 sequencer, 0-5 V logic -> UNO D8      2 = GND\n"
 "J3   1 = VREF (2.50 V)     2 = AIN3 (spare ADC input)     3 = GND",
 17.78, 229.87, 1.05)
text(
 "JP1  1-2 = CEM range     Rf = R1 2M2    full scale 1.14 uA,  57 pA/LSB\n"
 "     2-3 = Faraday range Rf = R2 100M   full scale 25 nA,  1.25 pA/LSB\n"
 "I2C  ADS1115 = 0x48 (ADDR->GND)   MCP4725 = 0x60 (A0->GND)\n"
 "UNO  D2 = ALERT/RDY    D8 = trigger    SDA/SCL pins = I2C.  Every other UNO pin is free.",
 172.72, 229.87, 1.05)

# ----------------------------------------------------------------------------- emit
def lib_sexp():
    out = ["  (lib_symbols"]
    for name, d in LIB.items():
        short = name.split(":", 1)[1]
        pw = " (power)" if d["power"] else ""
        hn = " (pin_numbers hide)" if d["hide_numbers"] else ""
        hnm = " hide" if d["hide_names"] else ""
        out.append(f'  (symbol "{name}"{pw}{hn} (pin_names (offset {d["offset"]}){hnm})'
                   f' (exclude_from_sim no) (in_bom {"no" if d["power"] else "yes"}) (on_board yes)')
        props = d["props"]
        for i, (k, v) in enumerate(props.items()):
            hide = "" if k in ("Reference", "Value") else " (hide yes)"
            y = 0 if k not in ("Reference", "Value") else (2.54 if k == "Reference" else -2.54)
            out.append(f'    (property "{esc(k)}" "{esc(str(v))}" (at 0 {y} 0)'
                       f' (effects (font (size 1.27 1.27)){hide}))')
        for unit, gfx in d["graphics"].items():
            out.append(f'    (symbol "{short}_{unit}_1"')
            out.extend(gfx)
            upins = [p for p in d["pins"] if p.get("unit", 1) == unit]
            for p in upins:
                out.append(pin_sexp(p))
            out.append("    )")
        # pins that belong to a unit with no graphics of its own
        for p in d["pins"]:
            if p.get("unit", 1) not in d["graphics"]:
                out.append(f'    (symbol "{short}_{p["unit"]}_1"')
                out.append(pin_sexp(p))
                out.append("    )")
        out.append("  )")
    out.append("  )")
    return "\n".join(out)

header = f'''(kicad_sch (version 20231120) (generator "eeschema") (generator_version "8.0")
  (uuid "{SHEET_UUID}")
  (paper "A3")
  (title_block
    (title "DAQ shield for Arduino UNO R3 - Team 5 acquisition board")
    (date "2026-09-22")
    (rev "E")
    (company "MIE1001 Team 5 - Foundation of Imaging Engineering, University College Maastricht")
    (comment 1 "Portable quadrupole mass spectrometer - data acquisition and control block")
    (comment 2 "Team 5 scope: ADC side. MCP4725 mass command is fitted for Team 4's sequencer.")
    (comment 3 "Digi-Key and LCSC (JLCPCB assembly) part numbers in BOM.csv")
    (comment 4 "Firmware base: Grinias et al., J. Chem. Educ. 2016, 93, 1316")
  )
'''

body = "\n".join(items)
sch = header + lib_sexp() + "\n" + body + f'\n  (sheet_instances (path "/" (page "1")))\n)\n'

here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "mie1001_daq_board.kicad_sch"), "w") as f:
    f.write(sch)

# standalone symbol library, so the "DAQ" lib_id actually resolves in KiCad
lib_body = lib_sexp()
lib_body = lib_body.split("\n")[1:-1]          # drop the (lib_symbols ...) wrapper
lib_body = [ln[2:] if ln.startswith("  ") else ln for ln in lib_body]
lib_body = [ln.replace('(symbol "DAQ:', '(symbol "') for ln in lib_body]
with open(os.path.join(here, "DAQ.kicad_sym"), "w") as f:
    f.write('(kicad_symbol_lib (version 20231120) (generator "kicad_symbol_editor")'
            ' (generator_version "8.0")\n' + "\n".join(lib_body) + "\n)\n")
with open(os.path.join(here, "sym-lib-table"), "w") as f:
    f.write('(sym_lib_table\n  (version 7)\n'
            '  (lib (name "DAQ")(type "KiCad")(uri "${KIPRJMOD}/DAQ.kicad_sym")(options "")'
            '(descr "MIE1001 Team 5 DAQ shield symbols"))\n)\n')

# ----------------------------------------------------------------------------- self-check
bad = [(a, b) for a, b in wire_pts if not all(ongrid(v) for v in (*a, *b))]
allpins = [(r, n, pt) for r, pr in placed.items() for n, pt in pr.pins.items()]
offgrid_pins = [(r, n, pt) for r, n, pt in allpins if not all(ongrid(v) for v in pt)]
print(f"wires: {len(wire_pts)}   off-grid wire segments: {len(bad)}")
print(f"pins:  {len(allpins)}   off-grid pins: {len(offgrid_pins)}")
for x in bad[:5]: print("   off-grid wire", x)
for x in offgrid_pins[:5]: print("   off-grid pin", x)

# BOM
rows = {}
for ref, pr in placed.items():
    if ref.startswith("#"):
        continue
    v, mfr, mpn, dk = BOM[ref]
    key = (v, mfr, mpn, dk, LIB[pr.lib]["props"]["Footprint"])
    rows.setdefault(key, []).append(ref)
def sortkey(r):
    m = re.match(r"([A-Za-z]+)(\d+)", r)
    return (m.group(1), int(m.group(2)))
with open(os.path.join(here, "BOM.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Qty", "References", "Value", "Footprint", "Manufacturer", "MPN",
                "Digi-Key P/N", "LCSC", "Note"])
    for key, refs in sorted(rows.items(), key=lambda kv: sortkey(sorted(kv[1], key=sortkey)[0])):
        v, mfr, mpn, dk, fp = key
        note = " ".join(NOTES[r] for r in sorted(refs, key=sortkey) if r in NOTES)
        lcsc = LCSC.get(sorted(refs, key=sortkey)[0], "")
        w.writerow([len(refs), ", ".join(sorted(refs, key=sortkey)), v, fp, mfr, mpn, dk, lcsc, note])
print(f"BOM lines: {len(rows)}  parts: {sum(len(v) for v in rows.values())}")
print("written:", os.path.join(here, "mie1001_daq_board.kicad_sch"))
