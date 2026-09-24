#!/bin/sh
# Rebuild everything from the two generators: schematic -> netlist -> PCB -> checks -> fab files.
#   ./build.sh
# Needs KiCad 10 (flatpak org.kicad.KiCad) and poppler (pdftoppm not required).
set -e
cd "$(dirname "$0")"
K="flatpak run --command=kicad-cli org.kicad.KiCad"
mkdir -p build fab/gerbers

python3 generate_schematic.py
$K sch erc --severity-error --severity-warning -o erc.rpt mie1001_daq_board.kicad_sch
$K sch export pdf -o mie1001_daq_board.pdf mie1001_daq_board.kicad_sch
$K sch export netlist --format kicadsexpr -o build/net.net mie1001_daq_board.kicad_sch

flatpak run --command=python3 org.kicad.KiCad generate_pcb.py
# DRC incl. schematic parity. Expected: 0 errors, 0 unconnected, 0 parity issues and
# 4 lib_footprint_mismatch warnings (J1, J2, J4, A1 are deliberately modified copies).
$K pcb drc --schematic-parity --severity-error --severity-warning -o drc.rpt mie1001_daq_board.kicad_pcb
flatpak run --command=python3 org.kicad.KiCad check_guard.py

rm -f fab/gerbers/*
$K pcb export gerbers -l "F.Cu,B.Cu,F.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts" \
    -o fab/gerbers/ mie1001_daq_board.kicad_pcb
$K pcb export drill --format excellon --excellon-separate-th --drill-origin absolute \
    --excellon-units mm -o fab/gerbers/ mie1001_daq_board.kicad_pcb
$K pcb export pos --side front --format csv --units mm --smd-only -o build/pos.csv mie1001_daq_board.kicad_pcb
$K pcb export pdf --mode-single -l "F.Cu,F.Silkscreen,F.Fab,Edge.Cuts" -o fab/assembly_top.pdf mie1001_daq_board.kicad_pcb
$K pcb render --side top --width 1600 --height 1200 --quality basic -o fab/board_top.png mie1001_daq_board.kicad_pcb
python3 make_fab.py
