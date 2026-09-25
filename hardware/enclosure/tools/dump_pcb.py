#!/usr/bin/env python3
"""Dump footprint/pad/zone positions of the shield PCB to JSON (run inside KiCad python):
    flatpak run --command=python3 org.kicad.KiCad tools/dump_pcb.py <board.kicad_pcb> build/pcb_dump.json
Read-only: never saves the board."""
import pcbnew, json, sys
b = pcbnew.LoadBoard(sys.argv[1])
mm = pcbnew.ToMM
out = {}
bb = b.GetBoardEdgesBoundingBox()
out['edge'] = [mm(bb.GetX()), mm(bb.GetY()), mm(bb.GetRight()), mm(bb.GetBottom())]
fps = {}
for f in b.GetFootprints():
    r = f.GetReference()
    try:
        cy = f.GetCourtyard(pcbnew.F_CrtYd if f.GetLayer()==pcbnew.F_Cu else pcbnew.B_CrtYd).BBox()
        cyb = [mm(cy.GetX()), mm(cy.GetY()), mm(cy.GetRight()), mm(cy.GetBottom())]
    except Exception as e:
        cyb = str(e)
    pads = [(p.GetNumber(), round(mm(p.GetPosition().x),3), round(mm(p.GetPosition().y),3), round(mm(p.GetDrillSize().x),2), round(mm(p.GetSize().x),2), round(mm(p.GetSize().y),2)) for p in f.Pads()]
    fps[r] = dict(fp=f.GetFPIDAsString(), pos=[mm(f.GetPosition().x), mm(f.GetPosition().y)], rot=f.GetOrientationDegrees(), side='B' if f.IsFlipped() else 'F', value=f.GetValue(), crtyd=cyb, pads=pads)
out['fps'] = fps
json.dump(out, open(sys.argv[2], 'w'), indent=1)
zones = []
for z in b.Zones():
    bb = z.GetBoundingBox()
    zones.append(dict(name=z.GetZoneName(), layer=z.GetLayerName(),
                      bbox=[mm(bb.GetX()), mm(bb.GetY()), mm(bb.GetRight()), mm(bb.GetBottom())]))
out['zones'] = zones
json.dump(out, open(sys.argv[2], 'w'), indent=1)
