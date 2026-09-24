#!/usr/bin/env python3
"""
Generate the SIMPLE MIE1001 Team 5 DAQ shield schematic (KiCad 8 format, opens in KiCad 8/9/10).

A plain Arduino UNO R3 shield for the breakout boards used in class:
    Adafruit ADS1115 breakout (original, one row of 10 pins) and SparkFun MCP4725 breakout (6 pins)
plug into female headers.  Screw terminals for the signal in, the QPS mass command out and the
trigger in; the breakouts bring their own I2C pull-ups.
Rev D adds an electrometer preamp (LMP7721 transimpedance amplifier, 100 MOhm) for a Faraday cup on a
vertical SMA jack, with a guarded input and a buffered 2.5 V reference.  Its SMD parts are assembled by
JLCPCB; everything else stays through-hole and hand-soldered.
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

# ---- Arduino UNO R3, drawn as the real board seen from the top (USB and DC jack on the left):
#      top header    SCL SDA AREF GND D13..D8 | D7..D0
#      bottom header NC IOREF RESET 3V3 5V GND GND VIN | A0..A5
#      pin numbers = Module:Arduino_UNO_R3 pad numbers (hidden on the sheet)
_uno_top = [("32", "SCL", "bidirectional"), ("31", "SDA", "bidirectional"), ("30", "AREF", "input"),
            ("29", "GND", "power_in"), ("28", "D13", "bidirectional"), ("27", "D12", "bidirectional"),
            ("26", "D11", "bidirectional"), ("25", "D10", "bidirectional"), ("24", "D9", "bidirectional"),
            ("23", "D8", "bidirectional"), None,
            ("22", "D7", "bidirectional"), ("21", "D6", "bidirectional"), ("20", "D5", "bidirectional"),
            ("19", "D4", "bidirectional"), ("18", "D3", "bidirectional"), ("17", "D2", "bidirectional"),
            ("16", "D1/TX", "bidirectional"), ("15", "D0/RX", "bidirectional")]
_uno_bot = [None, None, None, None,
            ("1", "NC", "no_connect"), ("2", "IOREF", "output"), ("3", "~{RESET}", "input"),
            ("4", "3V3", "power_out"), ("5", "+5V", "power_out"), ("6", "GND", "power_in"),
            ("7", "GND", "power_in"), ("8", "VIN", "power_in"), None,
            ("9", "A0", "bidirectional"), ("10", "A1", "bidirectional"), ("11", "A2", "bidirectional"),
            ("12", "A3", "bidirectional"), ("13", "SDA/A4", "bidirectional"), ("14", "SCL/A5", "bidirectional")]
uno_pins = [pin(q[0], q[1], round(-22.86 + 2.54 * i, 2), 20.32, 270, q[2]) for i, q in enumerate(_uno_top) if q]
uno_pins += [pin(q[0], q[1], round(-22.86 + 2.54 * i, 2), -20.32, 90, q[2]) for i, q in enumerate(_uno_bot) if q]
defsym("DAQ:Arduino_UNO_R3", uno_pins,
       {1: [rect(-27.94, 15.24, 27.94, -15.24)]},
       dict(Reference="A", Value="Arduino UNO R3",
            Footprint="Module:Arduino_UNO_R3",
            Datasheet="https://docs.arduino.cc/hardware/uno-rev3",
            Description="Arduino UNO R3 host board - the shield mates with these headers"),
       hide_numbers=True)

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
defsym("DAQ:SMA", [pin("1", "SIG", -11.43, 1.27, 0), pin("2", "SHIELD", -11.43, -1.27, 0)],
       {1: [rect(-6.35, 3.81, 6.35, -3.81)]},
       dict(Reference="J", Value="SMA", Footprint="Connector_Coaxial:SMA_Amphenol_132134_Vertical",
            Datasheet="https://www.amphenolrf.com/132134.html",
            Description="SMA jack, vertical through-hole, PTFE insulator"))
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
PROJECT = "mie1001_daq_simple"

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


# ---- simple-board symbols: female sockets for the breakouts, through-hole resistor
def conn_sym(name, n, names, fp, desc, ref="J"):
    top = (n - 1) * 1.27
    pins = [pin(str(i + 1), names[i], -11.43, round(top - i * 2.54, 2), 0) for i in range(n)]
    h = top + 2.54
    defsym(name, pins, {1: [rect(-6.35, h, 6.35, -h)]},
           dict(Reference=ref, Value=name.split(":")[1], Footprint=fp, Datasheet="", Description=desc))
conn_sym("DAQ:ADS1115_Breakout", 10, ["VDD", "GND", "SCL", "SDA", "ADDR", "ALRT", "A0", "A1", "A2", "A3"],
         "Connector_PinSocket_2.54mm:PinSocket_1x10_P2.54mm_Vertical",
         "Socket for the Adafruit ADS1115 breakout (original version, one row of 10 pins)", ref="U")
conn_sym("DAQ:MCP4725_Breakout", 6, ["OUT", "GND", "SCL", "SDA", "VCC", "GND"],
         "Connector_PinSocket_2.54mm:PinSocket_1x06_P2.54mm_Vertical",
         "Socket for the SparkFun MCP4725 breakout (BOB-12918)", ref="U")
conn_sym("DAQ:Spare_1x04", 4, ["1", "2", "3", "4"],
         "Connector_PinSocket_2.54mm:PinSocket_1x04_P2.54mm_Vertical", "1x4 female header")
defsym("DAQ:D_THT", [pin("1", "K", 5.08, 0, 180, "passive", 2.54), pin("2", "A", -5.08, 0, 0, "passive", 2.54)],
       {1: [poly([(-2.54, 2.54), (-2.54, -2.54), (2.54, 0.0), (-2.54, 2.54)], 0.254, "background"),
            poly([(2.54, 2.54), (2.54, -2.54)], 0.254)]},
       dict(Reference="D", Value="1N4148",
            Footprint="Diode_THT:D_DO-35_SOD27_P7.62mm_Horizontal",
            Datasheet="https://www.vishay.com/docs/81857/1n4148.pdf",
            Description="Small-signal diode, DO-35 through-hole"), hide_numbers=True, name_offset=0)
defsym("DAQ:C_THT", [pin("1", "~", 0, 3.81, 270, "passive", 2.54), pin("2", "~", 0, -3.81, 90, "passive", 2.54)],
       {1: [poly([(-2.032, 0.762), (2.032, 0.762)], 0.508), poly([(-2.032, -0.762), (2.032, -0.762)], 0.508)]},
       dict(Reference="C", Value="C", Footprint="Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P2.50mm",
            Datasheet="", Description="Ceramic disc capacitor, through-hole"),
       hide_numbers=True, name_offset=0)
defsym("DAQ:R_THT", [pin("1", "~", 0, 5.08, 270, "passive", 2.54), pin("2", "~", 0, -5.08, 90, "passive", 2.54)],
       {1: [rect(-1.016, 2.54, 1.016, -2.54, "none")]},
       dict(Reference="R", Value="R", Footprint="Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal",
            Datasheet="", Description="Resistor, through-hole 1/4 W"), hide_numbers=True, name_offset=0)

# ----------------------------------------------------------------------------- BOM data
BOM = {
  "ARD1": ("Arduino UNO R3 SMD (ATmega328P TQFP-32)", "Arduino or compatible", "UNO R3 SMD CH340 clone (marked V1888); A000073 is the official SMD edition", "do not order: use your own board"),
  "U1": ("Adafruit ADS1115 breakout (original, 1x10)", "Adafruit", "1085 (ORIGINAL 1x10 version, from the class kit)", "do not order"),
  "U2": ("SparkFun MCP4725 breakout", "SparkFun",       "BOB-12918",         "1568-12918-ND"),
  "J1": ("Signal in",                "Phoenix Contact", "1984617",           "277-1721-ND"),
  "J2": ("QPS out",                  "Phoenix Contact", "1984617",           "277-1721-ND"),
  "J3": ("Trigger in",               "Phoenix Contact", "1984617",           "277-1721-ND"),
  "J4": ("Spare ADC in",             "Sullins",         "PPTC041LFBN-RC",    "S7002-ND"),
  # sockets the breakouts plug into (listed so they get ordered)
  "X1": ("Female header 1x10 for U1", "Sullins",        "PPTC101LFBN-RC",    "S7008-ND"),
  "X2": ("Female header 1x6 for U2",  "Sullins",        "PPTC061LFBN-RC",    "S7004-ND"),
  "R1": ("1 kOhm 0.25 W",                  "Yageo",           "CFR-25JB-52-1K",    "1.0KQBK-ND"),
  "R2": ("4.7 kOhm 0.25 W",                 "Yageo",           "CFR-25JB-52-4K7",   "13-CFR-25JB-52-4K7-ND"),
  "R3": ("100 kOhm 0.25 W",                "Yageo",           "CFR-25JB-52-100K",  "13-CFR-25JB-52-100K-ND"),
  "C1": ("100 nF 50 V X7R ceramic",    "Vishay",          "K104K15X7RF5TL2",   "BC1084CT-ND"),
  "CR1": ("1N4148",                   "onsemi",          "1N4148",            "1N4148FS-ND"),
  "CR2": ("1N4148",                   "onsemi",          "1N4148",            "1N4148FS-ND"),
  # ---- rev D preamp (SMD parts assembled by JLCPCB; J5 and R4 hand-soldered)
  "J5":  ("Detector in, SMA jack vertical", "Amphenol RF", "132134",          "ACX1230-ND"),
  "R4":  ("10 kOhm 0.25 W",            "Yageo",           "CFR-25JB-52-10K",   "10KQBK-ND"),
  "R5":  ("1k 1% 0603",                "Yageo",           "RC0603FR-071KL",    "311-1.00KHRCT-ND"),
  "R6":  ("100M 1% 1206",              "Stackpole",       "HVCB1206FKC100M",   "HVCB1206FKC100MCT-ND"),
  "R7":  ("1k 1% 0603",                "Yageo",           "RC0603FR-071KL",    "311-1.00KHRCT-ND"),
  "R8":  ("10k 1% 0603",               "Yageo",           "RC0603FR-0710KL",   "311-10.0KHRCT-ND"),
  "R9":  ("10k 1% 0603",               "Yageo",           "RC0603FR-0710KL",   "311-10.0KHRCT-ND"),
  "R10": ("100R 1% 0603",              "Yageo",           "RC0603FR-07100RL",  "311-100HRCT-ND"),
  "R11": ("1k 1% 0603",                "Yageo",           "RC0603FR-071KL",    "311-1.00KHRCT-ND"),
  "C2":  ("10pF C0G 50V 0603",         "Murata",          "GRM1885C1H100JA01D", "490-1403-1-ND"),
  "C3":  ("100nF X7R 50V 0603",        "Samsung",         "CL10B104KB8NNNC",   "1276-1000-1-ND"),
  "C4":  ("10uF X5R 25V 0805",         "Samsung",         "CL21A106KAYNNNE",   "1276-2891-1-ND"),
  "C5":  ("1uF X5R 50V 0603",          "Samsung",         "CL10A105KB8NNNC",   "1276-1860-1-ND"),
  "C6":  ("1uF X5R 50V 0603",          "Samsung",         "CL10A105KB8NNNC",   "1276-1860-1-ND"),
  "C7":  ("100nF X7R 50V 0603",        "Samsung",         "CL10B104KB8NNNC",   "1276-1000-1-ND"),
  "CR3": ("BAV199LT1G",                "onsemi",          "BAV199LT1G",        "BAV199LT1GOSCT-ND"),
  "U3":  ("LMP7721MA/NOPB",            "Texas Instruments", "LMP7721MA/NOPB",  "LMP7721MA/NOPB-ND"),
  "U4":  ("MCP6002-I/SN",              "Microchip",       "MCP6002-I/SN",      "MCP6002-I/SN-ND"),
}
NOTES = {
  "U1": "Use the board from the class kit. The footprint is a 1x10 female header (PPTC101LFBN-RC) and fits only the ORIGINAL Adafruit board (one row: VDD GND SCL SDA ADDR ALRT A0-A3). What Digi-Key/Adafruit sell today as 1085 (1528-1085-ND) is the STEMMA QT version with two rows of 6: it does NOT fit.",
  "U2": "The footprint is a 1x6 female header (PPTC061LFBN-RC). Pull-ups ON (default), A0 jumper to GND (default) -> address 0x60. Retired at SparkFun, still at Digi-Key.",
  "R1": "Series resistor on the trigger input: limits the current if the trigger is driven a little above 5 V.",
  "R2": "Series resistor on SIGNAL IN: this is the part that actually protects the ADC, limiting the input current to 1.3-2.4 mA at +/-12 V against its 10 mA absolute maximum. Gain error from the ADS1115 input impedance: under 0.1 % at +/-6.144 V, 0.66 % at +/-0.256 V.",
  "R3": "Pull-down on D8: an unconnected TRIG IN reads LOW instead of floating.",
  "C1": "Filter cap at the ADS1115 input, 2.5 mm lead pitch. With R2 (4.7 kOhm) it is a single-pole low-pass at 339 Hz, and it supplies the charge the ADC's switched-capacitor input needs each sample. It does NOT remove 50 Hz hum (only 1.1 % at 50 Hz): use a low data rate or averaging for that. Must be X7R or C0G, NOT Y5V (Digi-Key BC1160-ND is the Y5V version: wrong part).",
  "CR1": "Diverts most of the current to +5 V if the input goes high. R2 is what keeps the ADC inside its 10 mA limit. Mind the stripe: cathode (striped end) to +5V. Leakage 25 nA max adds up to 117 uV of offset through R2.",
  "CR2": "Same, to GND, if the input goes below 0 V. Mind the stripe: cathode (striped end) to the signal.",
  "J5": "Faraday cup input. SMA with a PTFE insulator; use a BNC-female to SMA-male adapter for a BNC cable. Hand-solder. The centre pin sits in the VREF guard: keep it clean.",
  "R4": "Surge resistor at the input: limits the current into CR3 if the cup cable carries a discharge. Through-hole, mounted standing up; hand-solder. 10 uV drop per nA.",
  "R6": "100 MOhm feedback: 1 nA -> 0.1 V. Guard the pads, keep them clean, no flux residue. JLC/LCSC has no Stackpole HVCB stock: use Uniroyal 1206W4F1006T5E (C59781), 1% +-100 ppm/C.",
  "C2": "MUST be fitted: without it the preamp oscillates with the cable capacitance. With R6 it sets a 159 Hz bandwidth.",
  "R7": "Protects the LMP7721 IN+ from spikes on VREF; carries only fA.",
  "R10": "Isolation resistor so the MCP6002 VREF buffer can drive C5.",
  "C6": "With R11: 159 Hz anti-alias filter before ADS1115 A1.",
  "CR3": "Clamp tied to VREF on both ends: 0 V bias means near-zero leakage into the pA node. Do not substitute a switching diode.",
  "U3": "Electrometer preamp (3 fA typical input bias). Guard ring (VREF) on both layers around pins 1/8 and the feedback parts, no solder mask there. Clean flux off after soldering.",
  "U4": "Unit A buffers the 2.5 V reference (VREF); unit B is unused, wired as a follower.",
}
LCSC = {"R5": "C21190", "R6": "C59781", "R7": "C21190", "R8": "C25804", "R9": "C25804", "R10": "C22775",
        "R11": "C21190", "C2": "C1634", "C3": "C14663", "C4": "C15850", "C5": "C15849", "C6": "C15849",
        "C7": "C14663", "CR3": "C145516", "U3": "C124427", "U4": "C116706"}
SHORT = {"R1": "1 kΩ", "R2": "4.7 kΩ", "R3": "100 kΩ", "C1": "100 nF", "CR1": "1N4148", "CR2": "1N4148", "J1": "SIGNAL IN", "J2": "QPS OUT", "J3": "TRIG IN", "J4": "SPARE ADC A1-A3",
         "U1": "ADS1115 breakout", "U2": "MCP4725 breakout",
         "J5": "DET IN (SMA)", "R4": "10 kΩ", "R5": "1k", "R6": "100M", "R7": "1k", "R8": "10k", "R9": "10k",
         "R10": "100R", "R11": "1k", "C2": "10pF", "C3": "100nF", "C4": "10uF", "C5": "1uF", "C6": "1uF",
         "C7": "100nF", "CR3": "BAV199", "U3": "LMP7721", "U4": "MCP6002"}

def F(ref, **extra):
    v, mfr, mpn, dk = BOM[ref]
    d = {"Value": SHORT.get(ref, v), "Rating": v, "Manufacturer": mfr, "MPN": mpn, "Digi-Key P/N": dk}
    if ref in LCSC:
        d["LCSC"] = LCSC[ref]
    if ref in NOTES:
        d["Note"] = NOTES[ref]
    d.update(extra)
    return d

# ----------------------------------------------------------------------------- sheet content
# Every connection is a drawn wire: no net labels stand in for a wire. The labels that remain sit ON
# a wire and only name the net (the PCB generator routes by these names). Vertical rails between the
# breakouts and the UNO carry +5V, SDA, SCL and GND; a wire crossing a rail without a dot is NOT connected.
block(20.32, 22.86, 320.04, 203.2, "SIMPLE DAQ SHIELD  -  every connection drawn as a wire")

X5, XSDA, XSCL, XGND, XRDY = 127.0, 134.62, 142.24, 149.86, 111.76
YGT, YSDA, YSCL, Y5B, YGB = 137.16, 139.7, 142.24, 190.5, 193.04   # UNO runs to the rails, GND return

A1 = place("ARD1", "DAQ:Arduino_UNO_R3", 236.22, 167.64, fields=F("ARD1"),
           ref_at=(236.22, 163.83), val_at=(236.22, 167.64))
U1 = place("U1", "DAQ:ADS1115_Breakout", 88.9, 76.2, fields=F("U1"), mirror="y",
           ref_at=(88.9, 57.15), val_at=(88.9, 59.69))
U2 = place("U2", "DAQ:MCP4725_Breakout", 88.9, 127.0, fields=F("U2"), mirror="y",
           ref_at=(88.9, 113.03), val_at=(88.9, 115.57))
y = lambda part, pn: part.p(pn)[1]

# ---- the four rails: each is split at every tap so every T is a real wire joint with a dot
taps = {
    X5:   [43.18, y(U1, 1), y(U2, 5), Y5B],
    XSDA: [y(U1, 4), y(U2, 4), YSDA],
    XSCL: [y(U1, 3), y(U2, 3), YSCL],
    XGND: [y(U1, 2), y(U1, 5), 76.2, 90.17, y(U2, 2), y(U2, 6), YGT, YGB],
}
for x, ys in taps.items():
    ys = sorted(set(ys))
    wire(*[(x, v) for v in ys])
    junction(*[(x, v) for v in ys[1:-1]])
pwr("+5V", (X5, 43.18))
pwr("GND", (XGND, YGB))

# ---- breakouts and UNO onto the rails
for part, pn, x in [(U1, 1, X5), (U1, 2, XGND), (U1, 3, XSCL), (U1, 4, XSDA), (U1, 5, XGND),
                    (U2, 2, XGND), (U2, 3, XSCL), (U2, 4, XSDA), (U2, 5, X5), (U2, 6, XGND)]:
    wire(part.p(pn), (x, y(part, pn)))
# UNO top header: SCL, SDA and GND leave upwards, then run left to their rails
wire(A1.p("29"), (A1.p("29")[0], YGT), (XGND, YGT))
wire(A1.p("31"), (A1.p("31")[0], YSDA), (193.04, YSDA), (XSDA, YSDA)); label("SDA", (193.04, YSDA))
wire(A1.p("32"), (A1.p("32")[0], YSCL), (193.04, YSCL), (XSCL, YSCL)); label("SCL", (193.04, YSCL))
# UNO power header: 5V and both GNDs leave downwards
wire(A1.p("5"), (A1.p("5")[0], Y5B), (X5, Y5B))
wire(A1.p("6"), (A1.p("6")[0], YGB))
wire(A1.p("7"), (A1.p("7")[0], YGB))
text("USB-B\nsocket", 198.12, 156.21, 1.0)
text("DC\njack", 200.66, 175.26, 1.0)
text("top view, pins where they are on the real board", 236.22, 170.18, 1.0, justify="top")
text("POWER", 232.41, 172.72, 1.0, justify="top")
text("ANALOG IN", 252.73, 172.72, 1.0, justify="top")
text("DIGITAL", 236.22, 159.39, 1.0, justify="top")
text("U1  ADS1115 = ADC (analog-to-digital converter)", 25.4, 93.98, 1.27, bold=True)
text("Measures the detector voltage on A0 and turns it into a 16-bit number.\n"
     "Class kit board, original 1x10 version.\n"
     "ADDR to GND: I2C address 0x48.\n"
     "ALRT/RDY to UNO D2: says 'a new reading is ready'.\n"
     "Has its own 10 kΩ I2C pull-ups.", 25.4, 97.79, 1.0)
text("U2  MCP4725 = DAC (digital-to-analog converter)", 25.4, 139.7, 1.27, bold=True)
text("Turns a number from the UNO into a voltage, 0-5 V.\n"
     "That voltage is the mass command for the quadrupole (Team 4).\n"
     "SparkFun BOB-12918, A0 jumper to GND: address 0x60.\n"
     "Output sits at mid-scale at power-up.", 25.4, 143.51, 1.0)
text("HOW TO READ THIS DRAWING", 25.4, 163.83, 1.27, bold=True)
text("Green line = wire.  Dot = wires joined.\n"
     "Wires crossing WITHOUT a dot are NOT connected.\n"
     "X on a UNO pin = pin not used by this shield.\n"
     "Four vertical rails: +5V (power), SDA (I2C data),\n"
     "SCL (I2C clock), GND (0 V return).\n"
     "I2C = the 2-wire bus the UNO uses to talk to U1 and U2.", 25.4, 167.64, 1.0)
for rx, nm in ((127.64, "+5V"), (135.26, "SDA"), (142.88, "SCL"), (150.5, "GND")):
    text(nm, rx, 104.14, 1.27, bold=True)
text("ARD1  Arduino UNO R3 = the controller", 271.78, 99.06, 1.27, bold=True)
text("Reads U1 and sets U2 over I2C,\nsends the data to the laptop over USB.\nThis board plugs on top of it.\nPin NAMES shown (D2, D8, SDA...), as printed on the UNO.\nSDA/A4 and SCL/A5 are the SAME wires as SDA and SCL\ninside the UNO: keep A4 and A5 free.\nYour board: Uno R3 CH340G clone, IOREF is labelled 5V.",
     271.78, 102.87, 1.0)
text("SIGNAL IN: preamp output from the detector (Team 3)", 190.5, 35.56, 1.27, bold=True)
text("RDY: ADC tells the UNO a reading is ready", 180.34, 26.67, 1.0)
text("UNITS USED ON THIS DRAWING", 274.32, 40.64, 1.27, bold=True)
text("Ω   ohm: resistance, how hard a part resists current\n"
     "kΩ  kilo-ohm = 1000 Ω   (4.7 kΩ = 4700 Ω)\n"
     "F   farad: capacitance, how much charge a\n"
     "     capacitor stores\n"
     "nF  nanofarad = 0.000 000 001 F   (100 nF = 0.1 µF)\n"
     "V   volt: voltage, the electrical 'pressure'\n"
     "A   ampere: current, the flow of charge\n"
     "mA  milliampere = 0.001 A\n"
     "W   watt: power; the resistors are rated 0.25 W\n"
     "Hz  hertz: frequency, cycles per second\n"
     "bit binary digit; 16-bit = 65 536 steps\n"
     "0x48, 0x60: I2C addresses, written in hexadecimal\n"
     "+/-  plus or minus (+/-12 V = from -12 V to +12 V)", 274.32, 44.45, 1.0)

# ---- ALRT/RDY: over the top of the sheet to UNO D2 on the far side
wire(U1.p(6), (XRDY, y(U1, 6)), (XRDY, 30.48), (114.3, 30.48), (A1.p("17")[0], 30.48), A1.p("17"))
label("RDY", (114.3, 30.48))

# ---- signal input: J1 -> R2 -> SIG node (D1 to +5V, D2 and C1 to GND) -> ADS1115 A0
wire(U1.p(7), (154.94, y(U1, 7)), (154.94, 60.96), (156.21, 60.96), (162.56, 60.96),
     (180.34, 60.96), (185.42, 60.96))
label("SIG", (156.21, 60.96))
D1 = place("CR1", "DAQ:D_THT", 162.56, 53.34, 90, fields=F("CR1"), ref_at=(166.37, 52.07), val_at=(166.37, 54.61), just="left")
D2 = place("CR2", "DAQ:D_THT", 162.56, 68.58, 90, fields=F("CR2"), ref_at=(166.37, 67.31), val_at=(166.37, 69.85), just="left")
C1 = place("C1", "DAQ:C_THT", 180.34, 67.31, fields=F("C1"), ref_at=(184.15, 66.04), val_at=(184.15, 68.58), just="left")
R2 = place("R2", "DAQ:R_THT", 190.5, 60.96, 90, fields=F("R2"), ref_at=(190.5, 57.15), val_at=(190.5, 64.77))
J1 = place("J1", "DAQ:Screw_Terminal_1x02", 219.71, 62.23, fields=F("J1"), ref_at=(219.71, 53.34), val_at=(219.71, 55.88))
wire(D1.p(2), (162.56, 60.96))
wire(D1.p(1), (162.56, 43.18), (X5, 43.18))
wire(D2.p(1), (162.56, 60.96))
wire(D2.p(2), (162.56, 76.2))
wire(C1.p(1), (180.34, 60.96))
wire(C1.p(2), (180.34, 76.2))
wire((XGND, 76.2), (162.56, 76.2), (180.34, 76.2), (204.47, 76.2))
wire(R2.p(2), (196.85, 60.96), J1.p(1)); label("SIG_EXT", (196.85, 60.96))
wire(J1.p(2), (204.47, y(J1, 2)), (204.47, 76.2))
junction((162.56, 60.96), (180.34, 60.96), (162.56, 76.2), (180.34, 76.2))
text("INPUT PROTECTION AND FILTER", 154.94, 96.52, 1.27, bold=True)
text("R2 4.7 kΩ: limits the current into the ADC\n     if the input hits +/-12 V (2.4 mA max)\n"
     "CR1, CR2: clamp diodes, send an over-voltage to +5V or GND\n"
     "C1 100 nF: with R2 a 339 Hz low-pass filter against fast noise", 154.94, 100.33, 1.0)
text("J4 (ADS1115 inputs, not the UNO's): 1 = A1 preamp out, 2 = A2 spare,\n3 = A3 VREF 2.5 V, 4 = GND.  Pins 1 and 3 are for a meter or scope only.", 184.15, 90.17, 1.0)

# ---- spare inputs A1-A3 on J4
J4 = place("J4", "DAQ:Spare_1x04", 175.26, 86.36, fields=F("J4"), ref_at=(184.15, 85.09), val_at=(184.15, 87.63), just="left")
for pn, jp, name in [(8, 1, "PRE_OUT"), (9, 2, "AIN2"), (10, 3, "VREF")]:
    wire(U1.p(pn), (152.4, y(U1, pn)), J4.p(jp)); label(name, (152.4, y(U1, pn)))
wire(J4.p(4), (XGND, y(J4, 4)))

# ---- QPS mass command out on J2
J2 = place("J2", "DAQ:Screw_Terminal_1x02", 175.26, 121.92, fields=F("J2"), ref_at=(175.26, 113.03), val_at=(175.26, 115.57))
wire(U2.p(1), (152.4, y(U2, 1)), J2.p(1)); label("QPS", (152.4, y(U2, 1)))
wire(J2.p(2), (XGND, y(J2, 2)))
text("QPS OUT: mass command 0-5 V\nto the Extrel controller (Team 4)", 154.94, 128.27, 1.0)

# ---- trigger in: J3 -> R1 -> UNO D8, R3 pull-down
R1 = place("R1", "DAQ:R_THT", 279.4, 142.24, 90, fields=F("R1"), ref_at=(279.4, 138.43), val_at=(279.4, 146.05))
R3 = place("R3", "DAQ:R_THT", 269.24, 149.86, fields=F("R3", Footprint="Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P2.54mm_Vertical"),
           ref_at=(271.78, 148.59), val_at=(271.78, 151.13), just="left")
J3 = place("J3", "DAQ:Screw_Terminal_1x02", 308.61, 143.51, fields=F("J3"), ref_at=(308.61, 134.62), val_at=(308.61, 137.16))
d8 = A1.p("23")
wire(d8, (d8[0], 142.24), (241.3, 142.24), (269.24, 142.24), R1.p(1)); label("TRIG", (241.3, 142.24))
wire(R3.p(1), (269.24, 142.24))
wire(R1.p(2), (285.75, 142.24), J3.p(1)); label("TRIG_EXT", (285.75, 142.24))
wire(J3.p(2), (292.1, y(J3, 2)), (292.1, YGB))
wire(R3.p(2), (269.24, YGB))
junction((269.24, 142.24))

# ---- GND return along the bottom, under the UNO
wire((XGND, YGB), (203.2, YGB), (A1.p("6")[0], YGB), (A1.p("7")[0], YGB), (269.24, YGB), (292.1, YGB))
junction((203.2, YGB), (A1.p("6")[0], YGB), (A1.p("7")[0], YGB), (269.24, YGB))
place("#FLG02", "DAQ:PWR_FLAG", 203.2, YGB, 180, ref_at=(203.2, 199.39), val_at=(205.74, 197.51))
text("TRIG IN: start pulse from Team 4's sequencer -> UNO D8\n"
     "R1 1 kΩ limits the current; R3 100 kΩ pulls an open input LOW", 254.0, 196.85, 1.0)

# ============================ rev D: PREAMP ===================================
# Faraday cup current -> voltage.  The input node sits at VREF = 2.5 V, so the output swings both
# ways around it: Vout = VREF - I x 100 MOhm.  PRE_OUT and VREF reach the ADS1115 (A1, A3) and J4
# by net label; everything inside this block is a drawn wire.
block(20.32, 208.28, 297.18, 283.21, "PREAMP  (rev D):  Faraday cup current  ->  voltage for the ADS1115")
J5 = place("J5", "DAQ:SMA", 40.64, 233.68, fields=F("J5"), mirror="y",
           ref_at=(40.64, 226.06), val_at=(40.64, 228.6))
R4 = place("R4", "DAQ:R_THT", 66.04, 232.41, 90,
           fields=F("R4", Footprint="Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P2.54mm_Vertical"),
           ref_at=(66.04, 228.6), val_at=(66.04, 236.22))
CR3 = place("CR3", "DAQ:BAV199", 76.2, 243.84, 90, fields=F("CR3"),
            ref_at=(80.01, 242.57), val_at=(80.01, 245.11), just="left")
R5 = place("R5", "DAQ:R", 86.36, 232.41, 90, fields=F("R5"), ref_at=(86.36, 228.6), val_at=(86.36, 236.22))
U3 = place("U3", "DAQ:LMP7721", 111.76, 234.95, unit=1, fields=F("U3"),
           ref_at=(113.03, 242.57), val_at=(113.03, 245.11))
R6 = place("R6", "DAQ:R_1206", 111.76, 218.44, 90, fields=F("R6"), ref_at=(111.76, 214.63), val_at=(119.38, 214.63))
C2 = place("C2", "DAQ:C", 111.76, 223.52, 90, fields=F("C2"), ref_at=(104.14, 226.06), val_at=(119.38, 226.06))
R7 = place("R7", "DAQ:R", 91.44, 237.49, 90, fields=F("R7"), ref_at=(91.44, 241.3), val_at=(91.44, 243.84))
wire(J5.p(1), R4.p(1)); label("COAX_IN", (55.88, 232.41))
pwr("GND", J5.p(2))
wire(R4.p(2), (76.2, 232.41), R5.p(1)); junction((76.2, 232.41)); label("DET_IN", (78.74, 232.41))
wire(CR3.p(3), (76.2, 232.41))
wire(R5.p(2), (96.52, 232.41), U3.p(8)); junction((96.52, 232.41)); label("TIA_IN", (99.06, 232.41))
wire((96.52, 232.41), (96.52, 223.52), (96.52, 218.44), R6.p(1)); junction((96.52, 223.52))
wire((96.52, 223.52), C2.p(1))
wire(R6.p(2), (127.0, 218.44), (127.0, 223.52), (127.0, 234.95)); junction((127.0, 223.52), (127.0, 234.95))
wire(C2.p(2), (127.0, 223.52))
wire(R7.p(2), U3.p(1)); label("TIA_REF", (99.06, 237.49))
# output: anti-alias filter, then to ADS1115 A1 / J4-1 by the PRE_OUT label
R11 = place("R11", "DAQ:R", 137.16, 234.95, 90, fields=F("R11"), ref_at=(137.16, 231.14), val_at=(137.16, 238.76))
C6 = place("C6", "DAQ:C", 147.32, 238.76, fields=F("C6"), ref_at=(149.86, 237.49), val_at=(149.86, 240.03), just="left")
wire(U3.p(4), (127.0, 234.95), R11.p(1)); label("TIA_OUT", (129.54, 234.95))
wire(R11.p(2), (147.32, 234.95), (152.4, 234.95)); junction((147.32, 234.95)); label("PRE_OUT", (152.4, 234.95))
wire(C6.p(1), (147.32, 234.95)); pwr("GND", C6.p(2))
# LMP7721 supply, decoupling, and the N/C pins 2/5/7 on the guard (datasheet 10.1)
U3P = place("U3", "DAQ:LMP7721", 177.8, 226.06, unit=2, fields=F("U3"),
            ref_at=(182.88, 219.71), val_at=(182.88, 222.25), show_value=False)
pwr("+5V", U3P.p(6)); pwr("GND", U3P.p(3))
wire(U3P.p(2), (167.64, 223.52), (167.64, 226.06), (167.64, 228.6), (167.64, 257.81))
wire(U3P.p(5), (167.64, 226.06)); wire(U3P.p(7), (167.64, 228.6)); junction((167.64, 226.06), (167.64, 228.6))
C3 = place("C3", "DAQ:C", 187.96, 226.06, fields=F("C3"), ref_at=(190.5, 224.79), val_at=(190.5, 227.33), just="left")
pwr("+5V", C3.p(1)); pwr("GND", C3.p(2))
# VREF = 2.5 V: divider, filter, MCP6002 buffer, isolation resistor, reservoir cap
R8 = place("R8", "DAQ:R", 213.36, 223.52, fields=F("R8"), ref_at=(215.9, 222.25), val_at=(215.9, 224.79), just="left")
R9 = place("R9", "DAQ:R", 213.36, 238.76, fields=F("R9"), ref_at=(215.9, 237.49), val_at=(215.9, 240.03), just="left")
C4 = place("C4", "DAQ:C_0805", 203.2, 234.95, fields=F("C4"), ref_at=(198.12, 233.68), val_at=(198.12, 236.22), just="right")
pwr("+5V", R8.p(1)); pwr("GND", R9.p(2)); pwr("GND", C4.p(2))
wire(R8.p(2), (213.36, 231.14), R9.p(1))
wire(C4.p(1), (213.36, 231.14)); junction((213.36, 231.14))
U4A = place("U4", "DAQ:MCP6002", 236.22, 228.6, unit=1, fields=F("U4"), ref_at=(237.49, 219.71), val_at=(237.49, 222.25))
U4B = place("U4", "DAQ:MCP6002", 236.22, 246.38, unit=2, fields=F("U4"), ref_at=(237.49, 253.99), val_at=(237.49, 256.54),
            show_value=False)
U4P = place("U4", "DAQ:MCP6002", 281.94, 238.76, unit=3, fields=F("U4"), ref_at=(276.86, 236.22), val_at=(276.86, 241.3),
            show_value=False, just="right")
wire((213.36, 231.14), (220.98, 231.14), U4A.p(3)); junction((220.98, 231.14)); label("VREF_DIV", (215.9, 231.14))
wire(U4A.p(1), (248.92, 228.6), (248.92, 220.98), (223.52, 220.98), (223.52, 226.06), U4A.p(2))
junction((248.92, 228.6))
R10 = place("R10", "DAQ:R", 256.54, 228.6, 90, fields=F("R10"), ref_at=(256.54, 224.79), val_at=(256.54, 232.41))
wire((248.92, 228.6), R10.p(1)); label("VREF_BUF", (250.19, 228.6))
C5 = place("C5", "DAQ:C", 266.7, 232.41, fields=F("C5"), ref_at=(269.24, 233.68), val_at=(269.24, 236.22), just="left")
wire(R10.p(2), (266.7, 228.6), (271.78, 228.6), (271.78, 257.81)); junction((266.7, 228.6))
wire(C5.p(1), (266.7, 228.6)); pwr("GND", C5.p(2))
wire((220.98, 231.14), (220.98, 248.92), U4B.p(5))
wire(U4B.p(7), (248.92, 246.38), (248.92, 241.3), (223.52, 241.3), (223.52, 243.84), U4B.p(6))
label("BUF_B", (248.92, 243.84))
pwr("+5V", U4P.p(8)); pwr("GND", U4P.p(4))
C7 = place("C7", "DAQ:C", 289.56, 238.76, fields=F("C7"), ref_at=(292.1, 237.49), val_at=(292.1, 240.03), just="left")
pwr("+5V", C7.p(1)); pwr("GND", C7.p(2))
# VREF bus along the bottom: clamp, IN+ resistor, guard pins, buffer output
wire(CR3.p(1), (74.93, 257.81), (77.47, 257.81), (86.36, 257.81), (167.64, 257.81), (271.78, 257.81))
wire(CR3.p(2), (77.47, 257.81)); wire(R7.p(1), (86.36, 257.81))
junction((77.47, 257.81), (86.36, 257.81), (167.64, 257.81))
label("VREF", (190.5, 257.81))
text("HOW THE PREAMP WORKS", 22.86, 262.89, 1.27, bold=True)
text("The Faraday cup gives a tiny current (pA to nA).  U3 turns it into a voltage: every 1 nA moves the output 0.1 V\n"
     "(R6 = 100 MΩ).  The input is held at VREF = 2.5 V, so the output moves DOWN from 2.5 V for positive ions.\n"
     "Full scale is about 25 nA.  Read it on the ADS1115 as A1 - A3 (PRE_OUT - VREF): one count at GAIN_ONE = 1.25 pA.\n"
     "R4 + CR3 protect U3 from a discharge on the cable.  C2 keeps it from oscillating.  R11/C6 filter before the ADC.\n"
     "U4A makes VREF from 5 V (R8/R9 divider, C4 filter).  The copper guard ring (VREF) around the input stops leakage.",
     22.86, 266.7, 1.0)

# ---- every UNO pin not used by the shield
for pn in ("1", "2", "3", "4", "8", "9", "10", "11", "12", "13", "14", "15", "16", "18", "19", "20",
           "21", "22", "24", "25", "26", "27", "28", "30"):
    nc(A1.p(pn))


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
    (title "SIMPLE DAQ shield for Arduino UNO R3 - class breakout boards")
    (date "2026-09-24")
    (rev "D")
    (company "MIE1001 Team 5 - Foundation of Imaging Engineering, Maastricht University (FSE, M4I)")
    (comment 1 "Portable quadrupole mass spectrometer - data acquisition and control block")
    (comment 2 "Team 5 scope: ADC side. MCP4725 mass command is fitted for Team 4's sequencer.")
    (comment 3 "Digi-Key and LCSC part numbers in BOM.csv. JLCPCB assembles the preamp SMD parts only.")
    (comment 4 "Firmware base: Grinias et al., J. Chem. Educ. 2016, 93, 1316")
  )
'''

body = "\n".join(items)
sch = header + lib_sexp() + "\n" + body + f'\n  (sheet_instances (path "/" (page "1")))\n)\n'

here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "mie1001_daq_simple.kicad_sch"), "w") as f:
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
    key = (v, mfr, mpn, dk, pr.fields.get("Footprint", LIB[pr.lib]["props"]["Footprint"]))
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
    # parts with no symbol: the sockets the breakouts plug into, and the UNO stacking headers
    for ref in [r for r in BOM if r not in placed]:
        v, mfr, mpn, dk = BOM[ref]
        w.writerow([1, ref, v, "(on U1/U2 footprint)", mfr, mpn, dk, "", ""])
    w.writerow([1, "-", "Stacking header set for UNO R3 (1x10, 2x 1x8, 1x6)", "", "Adafruit", "85", "", "",
                "Adafruit product 85 (Adafruit, Jameco, Amazon); 10.5 mm legs clear the UNO's USB-B jack."])
print(f"BOM lines: {len(rows)}  parts: {sum(len(v) for v in rows.values())}")
print("written:", os.path.join(here, "mie1001_daq_simple.kicad_sch"))
