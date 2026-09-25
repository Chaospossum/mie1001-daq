#!/bin/sh
# Rebuild the simple shield: schematic -> netlist -> PCB -> checks -> fab files.
set -e
cd "$(dirname "$0")"
K="flatpak run --command=kicad-cli org.kicad.KiCad"
mkdir -p build fab/gerbers
python3 generate_schematic.py
$K sch erc --severity-error --severity-warning -o erc.rpt mie1001_daq_simple.kicad_sch
$K sch export pdf -o mie1001_daq_simple.pdf mie1001_daq_simple.kicad_sch
$K sch export netlist --format kicadsexpr -o build/net.net mie1001_daq_simple.kicad_sch
flatpak run --command=python3 org.kicad.KiCad generate_pcb.py
# expected: 0 errors, 0 unconnected, 0 parity; 4 lib_footprint_mismatch (A1, J1-J3 modified copies)
$K pcb drc --schematic-parity --severity-error --severity-warning -o drc.rpt mie1001_daq_simple.kicad_pcb
# leakage check around the preamp input: proximity + bare-board flood fill (rev E); fails the build on any finding
flatpak run --command=python3 org.kicad.KiCad check_guard.py
rm -f fab/gerbers/*
$K pcb export gerbers -l "F.Cu,B.Cu,F.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts" -o fab/gerbers/ mie1001_daq_simple.kicad_pcb
$K pcb export drill --format excellon --excellon-separate-th --drill-origin absolute --excellon-units mm -o fab/gerbers/ mie1001_daq_simple.kicad_pcb
$K pcb export pos --side front --format csv --units mm --smd-only -o build/pos.csv mie1001_daq_simple.kicad_pcb
$K pcb export pdf --mode-single --black-and-white -l "F.Cu,F.Silkscreen,Edge.Cuts" -o fab/print_1to1_top.pdf mie1001_daq_simple.kicad_pcb
$K pcb render --side top --width 1600 --height 1200 --quality basic -o fab/board_top.png mie1001_daq_simple.kicad_pcb
$K pcb render --side bottom --width 1600 --height 1200 --quality basic -o fab/board_bottom.png mie1001_daq_simple.kicad_pcb
# Digi-Key order list (fab/digikey_bom.csv), optional JLCPCB assembly files, and the gerber zip
python3 make_fab.py
