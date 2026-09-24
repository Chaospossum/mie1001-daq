#!/usr/bin/env python3
"""JLCPCB assembly files + gerber zip from BOM.csv and KiCad's position file.

fab/jlcpcb_bom.csv   Comment, Designator, Footprint, LCSC Part #   (SMD parts only)
fab/jlcpcb_cpl.csv   Designator, Mid X, Mid Y, Layer, Rotation
fab/mie1001_daq_shield_gerbers.zip
Through-hole parts (A1 headers, J1-J4, JP1) are not in the JLC files: hand-solder them.
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
HAND_SMD = {"R14"}          # anti-surge 1206 from Digi-Key, soldered by hand

bom = list(csv.DictReader(open("BOM.csv")))
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
with zipfile.ZipFile("fab/mie1001_daq_shield_gerbers.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for fn in sorted(os.listdir("fab/gerbers")):
        z.write(os.path.join("fab/gerbers", fn), fn)
print(f"JLC BOM: {len(rows)} lines, {len(placed)} placed parts; gerber zip written")
