#!/usr/bin/env python3
"""Numerical fit check: every opening of the enclosure against the part it serves.

Runs OpenSCAD with part="report" (echoes the derived opening coordinates), reads the shield's
connector positions from build/pcb_dump.json, and prints a markdown table to
build/fit_table.md.  Board frame as in scad/pcb_positions.scad.
"""
import ast
import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OPENSCAD = os.environ.get("OPENSCAD", os.path.expanduser("~/Applications/OpenSCAD-2026.09.23-x86_64.AppImage"))
X0, Y0 = 72.06, 102.54


def report():
    out = os.path.join(ROOT, "build", "report.echo")
    subprocess.run([OPENSCAD, "--backend=manifold", "-D", 'part="report"', "-o", out,
                    os.path.join(ROOT, "scad", "daq_enclosure.scad")], check=True, capture_output=True)
    r = {}
    for line in open(out):
        if 'ECHO: "R;' in line:
            _, k, v = line.split('"')[1].split(";", 2)
            r[k] = ast.literal_eval(v)
    return r


def main():
    r = report()
    d = json.load(open(os.path.join(ROOT, "build", "pcb_dump.json")))
    f = d["fps"]

    def bc(x, y):
        return x - X0, Y0 - y

    rows = []

    def row(what, opening, part, clr, note=""):
        ok = "OK" if clr >= 0.99 or "info" in note else ("tight" if clr >= 0.3 else "CHECK")
        rows.append((what, opening, part, f"{clr:.2f}", ok, note))

    ut, st, zs, zc = r["uno_top"], r["shield_top"], r["z_split"], r["z_ceil"]
    xi0, xi1 = r["xi"]; yi0, yi1 = r["yi"]; xo0, xo1 = r["xo"]
    # --- USB-B
    uy, uw, uo, jh = r["usb"]; n = r["usb_notch"]
    row("USB-B jack, sides", f"notch y {n[0]:.1f}..{n[1]:.1f}", f"jack y {uy-uw/2:.1f}..{uy+uw/2:.1f} (A000066)",
        min(uy - uw / 2 - n[0], n[1] - uy - uw / 2))
    row("USB-B jack, bottom", f"notch floor z {n[2]:.1f}", f"jack bottom = UNO top z {ut:.1f}", ut - n[2])
    row("USB-B jack, top", f"lid wall edge z {zs:.1f}", f"jack top z {ut+jh:.1f}", zs - ut - jh, "jack_h assumed 11.0")
    row("USB-B jack, reach", f"outer wall x {xo0:.1f}", f"jack front x {-uo:.1f}", xo0 + uo, "info: protrudes, plug mates fully")
    # --- DC
    dy, dw, do, _ = r["dc"]; n = r["dc_notch"]
    row("DC jack, sides", f"notch y {n[0]:.1f}..{n[1]:.1f}", f"jack y {dy-dw/2:.1f}..{dy+dw/2:.1f}",
        min(dy - dw / 2 - n[0], n[1] - dy - dw / 2))
    row("DC jack, bottom/top", f"z {n[2]:.1f}..{zs:.1f}", f"jack z {ut:.1f}..{ut+jh:.1f}", min(ut - n[2], zs - ut - jh))
    row("DC jack, plug reach", f"outer wall x {xo0:.1f}", f"jack front x {-do:.1f}", -(xo0 + do),
        "info: jack front recessed; plug sleeve 9.5 mm long, body must be <= 11.6 dia")
    # --- terminals
    for ref, slot, side in (("J1", "sigtrig_slot", "L"), ("J3", "sigtrig_slot", "L"), ("J2", "qps_slot", "R")):
        c = f[ref]["crtyd"]; (ax, ay), (bx, by) = bc(c[0], c[1]), bc(c[2], c[3])
        cx0, cx1, cy0, cy1 = min(ax, bx), max(ax, bx), min(ay, by), max(ay, by)
        pads = [bc(p[1], p[2]) for p in f[ref]["pads"]]
        s = r[slot]
        ey = [p[1] for p in pads]
        row(f"{ref} wire entries (y)", f"slot y {s[0]:.1f}..{s[1]:.1f}", f"entries y {min(ey):.2f}, {max(ey):.2f} (3.5 pitch)",
            min(min(ey) - s[0], s[1] - max(ey)) - 1.5, "clearance to a 3 mm wire/ferrule")
        row(f"{ref} wire entry (z)", f"slot z {zs:.1f}..{s[2]:.1f}", f"entry centre z {r['wire_z']:.1f}", s[2] - r["wire_z"] - 1.5,
            "wire_z assumed shield+3.9")
        wall = xi0 if side == "L" else xi1
        row(f"{ref} body vs lid wall", f"inner wall x {wall:.2f}", f"body x {cx0+0.5:.2f}..{cx1-0.5:.2f} (courtyard - 0.5)",
            (cx0 + 0.5 - wall) if side == "L" else (wall - cx1 + 0.5))
    for name, key, refs in (("J1+J3 screw window", "sigtrig_win", ("J1", "J3")), ("J2 screw window", "qps_win", ("J2",))):
        w = r[key]
        row(name, f"x {w[0]:.1f}..{w[2]:.1f}, y {w[1]:.1f}..{w[3]:.1f}", "screws over clamp, 2.5-3 mm blade",
            min(w[2] - w[0], 3.5) - 2.5, "info: window width vs 3 mm blade; lid ceiling %.1f above terminal top" % (zc - r["term_top"]))
    # --- J4
    w = r["j4_slot"]; p = [bc(q[1], q[2]) for q in f["J4"]["pads"]]
    row("J4 Dupont slot", f"x {w[0]:.2f}..{w[2]:.2f}, y {w[1]:.2f}..{w[3]:.2f}",
        f"socket x {p[0][0]-1.27:.2f}..{p[-1][0]+1.27:.2f}, y {p[0][1]-1.27:.2f}..{p[0][1]+1.27:.2f}",
        min(p[0][0] - 1.27 - w[0], w[2] - p[-1][0] - 1.27, p[0][1] - 1.27 - w[1], w[3] - p[0][1] - 1.27))
    # --- J5
    j5 = bc(*f["J5"]["pos"]); D = r["faraday_pass_d"]
    row("J5 SMA -> BNC adapter", f"hole dia {D} at ({j5[0]:.2f},{j5[1]:.2f})", "SMA nut 8 mm hex (9.2 a/c)", (D - 9.2) / 2, "radial")
    row("J5 adapter BNC studs", f"hole dia {D}", "BNC bayonet studs 11.6 across", (D - 11.6) / 2, "info: radial, only while threading the lid over the adapter")
    # --- heights
    row("Breakouts vs lid ceiling", f"ceiling z {zc:.1f}", f"breakout top z {r['brk_top']:.1f}", zc - r["brk_top"], "brk_h assumed 14.5")
    row("Stacking headers vs ceiling", f"ceiling z {zc:.1f}", f"header top z {r['hdr_top']:.1f}", zc - r["hdr_top"])
    # --- boards vs walls / posts
    row("Boards vs side walls (x)", f"x {xi0:.1f} / {xi1:.2f}", "outline x 0 / 68.58", min(-xi0, xi1 - 68.58))
    row("Boards vs front/back walls", f"y {yi0:.1f} / {yi1:.2f}", "outline y 0 / 53.34", min(-yi0, yi1 - 53.34))
    corners = [(0, 0), (66.04, 0), (68.58, 5.08), (68.58, 37.85), (66.04, 51.82), (64.52, 53.34), (0, 53.34)]
    pc = min(math.dist(p, c) - r["post_r"] for p in r["posts"] for c in corners)
    row("Lid-screw posts vs board corners", "post r %.1f" % r["post_r"], "UNO outline corners", pc)
    # --- mounting
    for (hx, hy), h in zip(r["uno_pegs"][:1] + r["uno_holes"], ("H1", "H2", "H3")):
        px, py = bc(*f[h]["pos"])
        row(f"Boss/peg {h} vs shield hole", f"at ({hx:.2f},{hy:.2f})", f"PCB {h} ({px:.2f},{py:.2f})", -math.dist((hx, hy), (px, py)),
            "info: position error (0 = exact)")
    ic = [bc(x, y) for x, y in ((134.0, 70.4), (139.9, 78.6))]
    icsp_y = max(p[1] for p in ic)
    row("Spacer at H3 vs UNO ICSP header", f"spacer dia {r['spacer'][0]} at y 35.56", f"ICSP keep-out y max {icsp_y:.2f}",
        35.56 - r["spacer"][0] / 2 - icsp_y, "keep-out is already larger than the header")
    g = r["patch"]; gb = [bc(x, y) for x, y in ((108.4, 54.4), (132.525, 63.7))]
    row("Preamp guard vs nearest wall", f"back wall y {yi1:.2f}", f"guard y max {max(p[1] for p in gb):.2f}",
        yi1 - max(p[1] for p in gb), "info: nothing of the enclosure is within %.1f mm above it" % (zc - st))

    lines = ["| Check | Enclosure | Part | Clearance mm | | Note |", "|---|---|---|---|---|---|"]
    lines += ["| " + " | ".join(x) + " |" for x in rows]
    txt = "\n".join(lines)
    open(os.path.join(ROOT, "build", "fit_table.md"), "w").write(txt + "\n")
    print(txt)
    print(f"\nz: UNO top {ut:.1f}, split {zs:.1f}, shield top {st:.1f}, ceiling {zc:.1f}, top {r['z_top']:.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
