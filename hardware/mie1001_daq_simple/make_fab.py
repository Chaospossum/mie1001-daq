#!/usr/bin/env python3
"""Digi-Key order list, (optional) JLCPCB assembly files and the gerber zip, from BOM.csv and KiCad's position file.

fab/digikey_bom.csv  Digi-Key BOM Manager / "Upload a list" format, quantities for ONE board
                     (do-not-order items left out). Spares: see README "Ordering from Digi-Key".
OPTIONAL (only if JLCPCB assembles the SMD parts instead of hand-soldering):
fab/jlcpcb_bom.csv   Comment, Designator, Footprint, LCSC Part #   (SMD parts only)
fab/jlcpcb_cpl.csv   Designator, Mid X, Mid Y, Layer, Rotation
fab/mie1001_daq_simple_gerbers.zip
Through-hole parts (sockets, terminals, J5 SMA, R1-R4, CR1, CR2, C1) are not in the JLC files: hand-solder them.
"""
import csv
import os
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

# KiCad -> JLCPCB zero-orientation offsets for KiCad library footprints
# (JLCKicadTools cpl_rotations_db.csv). MSOP has no entry: check it in JLC's preview.
import re
ROT_FIX = [(r"^SOIC-", 270), (r"^SOT-23", -90)]
HAND_SMD = set()          # every SMD part is machine-placed; J5, R4 and the rest are through-hole

bom = list(csv.DictReader(open("BOM.csv")))

# ---- Digi-Key order list (primary route: university procurement, everything from Digi-Key)
# Unit prices in USD from digikey.com on 2026-09-25 at the quantity for one board (cut tape / single
# piece). Only used for the cost estimate printed below; Digi-Key's cart has the real price.
PRICE_USD = {
    "1568-12918-ND": 6.95, "277-1721-ND": 0.59, "S7002-ND": 0.42, "S7008-ND": 0.64, "S7004-ND": 0.47,
    "1.0KQBK-ND": 0.10, "13-CFR-25JB-52-4K7-ND": 0.10, "13-CFR-25JB-52-100K-ND": 0.11,
    "13-CFR-25JB-52-10K-ND": 0.10, "BC1084CT-ND": 0.29, "1N4148FS-ND": 0.10, "ACX1230-ND": 9.98,
    "311-1.00KHRCT-ND": 0.10, "HVCB1206FKC100MCT-ND": 4.01, "311-100KHRCT-ND": 0.10,
    "311-100HRCT-ND": 0.10, "1276-1027-1-ND": 0.10, "732-8013-1-ND": 0.10, "587-4334-1-ND": 0.29,
    "1276-1102-1-ND": 0.10, "BAV199LT1GOSCT-ND": 0.16, "LMP7721MA/NOPB-ND": 7.34,
    "MCP6002-I/SN-ND": 0.42, "1528-1074-ND": 1.95,
}
dk = {}
for r in bom:
    pn = r["Digi-Key P/N"].strip()
    if not pn or pn.lower().startswith("do not order"):
        continue
    d = dk.setdefault(pn, {"Digi-Key Part Number": pn, "Manufacturer Part Number": r["MPN"],
                           "Manufacturer": r["Manufacturer"], "Quantity": 0, "Customer Reference": []})
    if (d["Manufacturer Part Number"], d["Manufacturer"]) != (r["MPN"], r["Manufacturer"]):
        raise SystemExit(f"{pn}: two different MPNs/manufacturers in BOM.csv")
    d["Quantity"] += int(r["Qty"])
    d["Customer Reference"].append(r["References"].replace(" ", "") if r["References"] != "-" else "UNO stacking hdr")
with open("fab/digikey_bom.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["Digi-Key Part Number", "Manufacturer Part Number", "Manufacturer",
                                      "Quantity", "Customer Reference"])
    w.writeheader()
    for d in dk.values():
        w.writerow(dict(d, **{"Customer Reference": ("MIE1001 " + ",".join(d["Customer Reference"]))[:48]}))
nopr = sorted(set(dk) - set(PRICE_USD))
if nopr:
    raise SystemExit("Digi-Key P/N without a price in make_fab.py: %s" % nopr)
cost = sum(d["Quantity"] * PRICE_USD[pn] for pn, d in dk.items())
print(f"Digi-Key BOM: {len(dk)} lines, {sum(d['Quantity'] for d in dk.values())} parts, "
      f"~${cost:.2f} per board (1 board ${cost:.2f}, 2 boards ${2 * cost:.2f}, qty-1 prices, excl. PCB/shipping/VAT)")

# ---- OPTIONAL: JLCPCB assembly of the SMD parts
pos = {r["Ref"]: r for r in csv.DictReader(open("build/pos.csv"))}


def key(ref):
    stem = ref.rstrip("0123456789")
    return stem, int(ref[len(stem):])


rows, placed = [], set()
for r in bom:
    refs = [x.strip() for x in r["References"].split(",")]
    smd = [x for x in refs if x in pos and x not in HAND_SMD]
    if not smd or not r["LCSC"]:
        continue
    placed.update(smd)
    rows.append({"Comment": r["Value"], "Designator": ",".join(smd),
                 "Footprint": r["Footprint"].split(":")[-1], "LCSC Part #": r["LCSC"]})
with open("fab/jlcpcb_bom.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["Comment", "Designator", "Footprint", "LCSC Part #"])
    w.writeheader(); w.writerows(rows)
with open("fab/jlcpcb_cpl.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
    for ref in sorted(placed, key=key):
        p = pos[ref]
        rot = float(p["Rot"])
        for pat, off in ROT_FIX:
            if re.match(pat, p["Package"]):
                rot = (rot + off) % 360
                break
        w.writerow([ref, f'{float(p["PosX"]):.4f}mm', f'{float(p["PosY"]):.4f}mm', "Top", f'{rot:.1f}'])
missing = sorted(set(pos) - placed - HAND_SMD, key=key)
if missing:
    raise SystemExit("SMD parts without an LCSC number: %s" % missing)
with zipfile.ZipFile("fab/mie1001_daq_simple_gerbers.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for fn in sorted(os.listdir("fab/gerbers")):
        z.write(os.path.join("fab/gerbers", fn), fn)
print(f"(optional) JLC BOM: {len(rows)} lines, {len(placed)} placed parts; gerber zip written")
