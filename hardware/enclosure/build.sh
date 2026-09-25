#!/usr/bin/env bash
# Rebuild everything: PCB positions -> STLs -> renders -> fit table -> (optional) PrusaSlicer estimate.
#   ./build.sh            full build (re-reads the shield .kicad_pcb, read-only)
#   ./build.sh --no-pcb   keep scad/pcb_positions.scad as it is (no KiCad needed)
#   ./build.sh --no-slice skip PrusaSlicer
set -euo pipefail
cd "$(dirname "$0")"
OPENSCAD=${OPENSCAD:-$HOME/Applications/OpenSCAD-2026.09.23-x86_64.AppImage}
PCB=${PCB:-$HOME/projects/mie1001_daq_simple/mie1001_daq_simple.kicad_pcb}
mkdir -p build stl renders
if [[ " $* " != *" --no-pcb "* ]]; then
  cp "$PCB" build/pcb_snapshot.kicad_pcb            # snapshot: never touch the KiCad project
  flatpak run --command=python3 org.kicad.KiCad tools/dump_pcb.py build/pcb_snapshot.kicad_pcb build/pcb_dump.json
  python3 tools/make_positions.py
fi
S=scad/daq_enclosure.scad
$OPENSCAD --backend=manifold -D 'part="base"'      -o stl/daq_base.stl $S
$OPENSCAD --backend=manifold -D 'part="lid_print"' -o stl/daq_lid.stl  $S   # lid already flipped for printing
$OPENSCAD --backend=manifold -D 'part="spacer"'    -o stl/daq_spacer_x2.stl $S  # 2 spacers UNO<->shield
png() { # part name rot_x rot_z [extra]
  $OPENSCAD --backend=manifold ${5:-} -D "part=\"$1\"" -o renders/$2.png --imgsize=1400,1050 \
    --colorscheme=Tomorrow --projection=p --autocenter --viewall --camera=0,0,0,$3,0,$4,300 $S; }
png assembly assembly 60 -30
png assembly assembly_back 60 150
png exploded exploded 70 -30
png boards   boards_only 55 -30
png base      base       50 -30 --render=force
png base      base_left  60 230 --render=force
png lid       lid_top    25 20  --render=force
png lid_print lid_print  50 -30 --render=force
python3 tools/fit_check.py > /dev/null && echo "fit table -> build/fit_table.md"
if [[ " $* " != *" --no-slice "* ]]; then
  for p in base lid; do
    flatpak run com.prusa3d.PrusaSlicer --export-gcode --load print/petg_clear_0.2mm.ini --center 125,105 \
      -o build/daq_$p.gcode stl/daq_$p.stl > build/slice_$p.log 2>&1
    echo "$p: $(grep -h -E '^; (estimated printing time \(normal mode\)|total filament used \[g\])' build/daq_$p.gcode | tr '\n' ' ')"
  done
fi
