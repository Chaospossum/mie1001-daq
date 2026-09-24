# MIE1001 — simple DAQ shield (rev D)

The beginner version of the DAQ board: an Arduino UNO R3 shield that the two breakout
boards from class plug into (modular: both unplug). Fat tracks, the breakouts, connectors and
through-hole parts are hand-soldered. **Rev D adds a Faraday-cup preamp**: its 16 small SMD parts are
assembled by JLCPCB; everything else you solder yourselves.

![board](fab/board_top.png)

```
SIGNAL IN (J1) -> R2 4k7 -> [CR1/CR2 clamp, C1 filter] -> ADS1115 breakout A0 -> I2C -> UNO -> USB -> laptop
UNO -> I2C -> SparkFun MCP4725 breakout OUT -> QPS OUT (J2), 0-5 V
TRIG IN (J3) -> R1 1k -> UNO D8 (R3 100k to GND)    ADS1115 ALRT -> UNO D2
Faraday cup -> J5 SMA -> R4 10k -> CR3 clamp to VREF -> R5 1k -> U3 LMP7721 preamp (R6 100M || C2 10p)
            -> R11/C6 1k/1u -> ADS1115 A1 (PRE_OUT)      VREF 2.5 V (R8/R9 + C4 -> U4A MCP6002 -> R10 -> C5) -> A3
J4 = test header: 1 PRE_OUT, 2 A2 (spare), 3 VREF, 4 GND
```

| Check | Result |
|---|---|
| ERC | 0 errors, 0 warnings |
| Guard check (`check_guard.py`, rev D) | 0 items of any other net within 1.0 mm of the preamp input (COAX_IN, DET_IN, TIA_IN, TIA_REF) |
| Independent critical review | Two reviews against the Adafruit, SparkFun, Arduino, Phoenix and TI source files and datasheets. Rev A: pinouts and UNO geometry correct, four fixes → rev B. Rev C: copper clean, no respin needed; one wrong BOM part number and several wrong claims in this file, all corrected below |
| Host board | Arduino UNO R3 **SMD** (ATmega328P in a flat TQFP-32 package). Its headers are identical to the standard R3 (same positions, same pins, SDA/SCL next to AREF), so the shield fits unchanged |
| Still unverified | The height of the parts on the UNO under the shield (crystal, USB chip, capacitors). The SMD chip itself is only about 1.2 mm tall, so this is much less of a risk than with the socketed DIP chip, but look at your board before soldering |
| DRC incl. schematic parity | 0 errors, 0 unconnected, 0 parity issues (4 `lib_footprint_mismatch` warnings: ARD1 and J1–J3 are deliberately modified copies) |
| Orientation | Same real-UNO geometry as the full board (rev E): flipped library footprint, keep-outs over the USB, DC jack and both ICSP headers |
| Rules | 0.5 mm tracks, 0.3 mm gaps, 0.8/0.4 mm vias: far above JLCPCB's minimums |

## What changed in rev D (2026-09-24): the preamp

The Faraday cup gives a current of pA to nA. The ADS1115 measures voltage, so rev D adds a
**transimpedance amplifier** (U3, LMP7721) that turns 1 nA into 0.1 V. Everything that was on rev C
stays where it was; the preamp sits in the band under the digital header, where the text used to be
(the text moved to the left edge and the back).

| Part | Job |
|---|---|
| **J5** SMA jack (vertical, PTFE) | Detector input. Use a **BNC-female to SMA-male adapter** for a BNC cable. A BNC did not fit anywhere on this board |
| **U3** LMP7721 + **R6** 100 MΩ | The preamp: Vout = VREF − I × 100 MΩ. Full scale ~25 nA; 1 ADC count = 1.25 pA at GAIN_ONE |
| **C2** 10 pF | Stops the preamp oscillating with the cable capacitance. Sets a 159 Hz bandwidth |
| **R4** 10k + **CR3** BAV199 + **R5** 1k | Protect U3 from a discharge on the cable. CR3 is tied to VREF, so it leaks ~0 into the input |
| **VREF** 2.5 V: R8/R9 10k/10k, C4 10 µF, U4A MCP6002, R10 100 Ω, C5 1 µF | The input sits at 2.5 V so the output can swing both ways on a single 5 V supply |
| **R7** 1k | Protects U3's + input |
| **R11** 1k + **C6** 1 µF | 159 Hz anti-alias filter before ADS1115 **A1** |
| **Guard ring** (copper at VREF, both layers) | Surrounds the whole input so no other copper can leak pA into it |

**Firmware:** read the preamp as `ads.readADC_Differential_1_3()` (A1 − A3 = PRE_OUT − VREF), then
`I = −V / 100e6`. The ADS1115 only offers the pairs 0-1, 0-3, 1-3 and 2-3, which is why VREF is on A3.
SIGNAL IN (J1) → A0 still works as before for a voltage input.

**J4 changed:** pin 1 is now PRE_OUT and pin 3 is VREF (monitor only: connect a meter or scope, never a
source). Pin 2 (A2) is still a free input.

**Still 0-5 V on QPS OUT.** The Extrel 150-QC wants a 0-10 V mass command; that needs a gain-2 amplifier on
a supply above 10 V (e.g. a 12 V adapter on the UNO's DC jack). Not on this revision.

**Handling:** the input works at picoamps. After soldering, wash off **all** flux around U3, R6, C2, R4 and
J5 (isopropyl alcohol, then dry), handle the board by its edges, and measure the zero offset with the
cable connected and the beam off before every scan.

## Names on the drawing and the board (2026-09-24, copper unchanged)

- The UNO is **ARD1** and the clamp diodes are **CR1, CR2** (were A1, D1, D2), so the names no longer clash
  with the UNO's pins A1 and D2.
- The UNO symbol shows only the pin names printed on the UNO (D2, D8, SDA ...), not KiCad pad numbers.
- SDA/A4 and SCL/A5 are the same wires inside the UNO: the ✕ on A4/A5 means the shield adds nothing
  there, not that they are separate. Keep A4 and A5 free.

## What changed in rev C

Three parts on the signal input, in the free band under the ADS1115 socket:

- **C1 (100 nF) to ground.** With R2 it is a single-pole low-pass at **339 Hz**, and it supplies the
  charge the ADC's switched-capacitor input takes at each sample. It takes the edge off fast noise
  and limits the bandwidth, so leave it out if you need to measure something faster than ~300 Hz.
  **It does not remove mains hum**: at 50 Hz it attenuates by only 1.1 %. See the firmware notes for
  what actually works. **C1 must be X7R or C0G, not Y5V** (a Y5V part loses most of its value when
  warm, which moves the corner frequency anywhere up to ~2 kHz).
- **CR1 and CR2 (1N4148) clamps.** They divert most of an over-voltage to the rails. Be clear about
  what does the work: **R2 is what keeps the chip legal** (1.3–2.4 mA at ±12 V against its 10 mA
  limit), because the 1N4148 only starts conducting around 0.5–0.7 V, by which point the input is
  already past the ADC's absolute maximum of VDD + 0.3 V and the chip's own internal protection
  diode is conducting alongside CR1. The diodes are there for the energy of a static zap or a badly
  wrong connection, not to hold the pin inside spec. TI also warns that overdriving one input can
  upset conversions on the others: **while A0 is overdriven, readings on A1–A3 are not valid either.**
- **What the diodes cost:** up to 25 nA of leakage each, which through R2 is up to 117 µV of offset
  (15 counts at GAIN_SIXTEEN, and several times worse when hot). Fine at low gain; calibrate the
  offset if you use the high gain ranges.
- **One side effect:** with the Uno unpowered, a signal above 5 V feeds up to 2.4 mA (at +12 V) back into its
  5 V rail through CR1. Don't leave a live preamp connected to an unpowered board.
- **No amplifier.** The ADS1115 has a programmable gain amplifier built in, so a small signal is
  handled in software with `ads.setGain(...)` instead of another chip. Note that at the highest
  gains the chip's differential input resistance falls to about 710 k, where R2 costs ~0.66 % of
  gain (under 0.1 % at the ±6.144 V range, 0.2–0.4 % at ±2.048 and ±1.024 V): calibrate if you use GAIN_SIXTEEN. Note TI suggests keeping
  a filter resistor under 1 k; 4.7 k is deliberate here, chosen for protection, and C1 at the pin
  supplies the sampling charge that the series resistance otherwise would.

**Watch the stripe when soldering the diodes.** The silkscreen prints **K** at the cathode end of
each one, and that is the end with the black band on the part. CR1's K points right, towards +5 V.
CR2's K points left, towards the signal. Backwards, they short the signal to a rail.

## What changed in rev B

- **R2 (4k7) in series with SIGNAL IN.** The ADS1115 input may not go above VDD + 0.3 V (TI
  datasheet, absolute maximum ratings). If the preamp swings to its ±12 V rails, R2 keeps the current
  into the chip's input clamp to 1.3–2.4 mA (its limit is 10 mA). Gain error: under 0.1 % on the ±6.144 V
  range, 0.66 % on the ±0.256 V range.
- **R3 (100k) pull-down on D8.** A TRIG IN with nothing connected now reads LOW instead of
  picking up noise and giving false triggers.
- **Pin-1 triangles and "which way round" text on both sockets.** Both breakouts fit in their
  sockets rotated 180°. For the MCP4725 that puts 5 V on its GND pin. Now the MCP4725 outline is
  the real 15.2 × 15.2 mm board.
- **Firmware and BOM fixes.** `dac.begin(0x60)` (the library default is 0x62), and the BOM no
  longer orders the new two-row ADS1115 board that doesn't fit.

## Before you order: three things to check by hand

1. **Which ADS1115 board do you have?** Use the one from the class kit; do not order a new one. This shield fits the **original** Adafruit board with
   **one row of 10 pins** (VDD GND SCL SDA ADDR ALRT A0 A1 A2 A3). Adafruit now sells a newer
   STEMMA QT version (two rows of 6, "VIN" instead of "VDD") under the same product number
   1085, and **it does not fit**. Your team's self-test sketch says "VDD", so you probably have
   the original, but count the pins.
2. **Print `fab/print_1to1_top.pdf` at 100 %** and lay the UNO and both breakouts on it. The
   header holes must line up with the UNO's pins and with each breakout's pins.
3. **Height over the UNO's chip area.** CR1, CR2, C1, the ADS1115 socket and J4 all sit above it.
   On the UNO R3 SMD the ATmega328P is a flat TQFP (about 1.2 mm), so the chip itself is no problem;
   check that nothing else on your board (crystal, USB chip, capacitors) is taller than the gap, and
   trim the leads flush.

## Parts (full list in `BOM.csv`)

| Ref | Part | Where |
|---|---|---|
| U1 | Adafruit ADS1115 breakout (original, 1×10), **from the class kit** | plugs into a 1×10 female header (Sullins PPTC101LFBN-RC, Digi-Key S7008-ND). Don't order 1528-1085-ND: that is the new two-row board |
| U2 | SparkFun MCP4725 breakout BOB-12918 | plugs into a 1×6 female header (PPTC061LFBN-RC, S7004-ND). Retired at SparkFun, still at Digi-Key 1568-12918-ND |
| J1, J2, J3 | Phoenix 1984617 screw terminals, 3.5 mm | Digi-Key 277-1721-ND |
| J4 | 1×4 female header for the spare inputs | S7002-ND |
| R1 | 1k ¼ W resistor on the trigger | 1.0KQBK-ND |
| R2 | 4k7 ¼ W resistor in series with SIGNAL IN | 13-CFR-25JB-52-4K7-ND |
| R3 | 100k ¼ W pull-down on D8, mounted standing up | 13-CFR-25JB-52-100K-ND |
| C1 | 100 nF 50 V **X7R** disc, **2.5 mm lead pitch** (not Y5V: BC1160-ND is the wrong one) | BC1084CT-ND |
| CR1, CR2 | 1N4148 signal diodes (DO-35) | 1N4148FS-ND |
| — | UNO stacking headers | Adafruit 85 (legs just clear the USB jack) |

No other parts. Both breakouts already carry the I²C pull-ups: the ADS1115 board has 10k on
SDA and on SCL (hard-wired), the MCP4725 board has 4.7k on each through jumper SJ1 (closed by a
trace from the factory). In parallel that is 3.2k per line, about 2.9k once the Arduino's own
internal pull-ups are counted, which draws 1.6 mA at the low level against the 3 mA an I²C
device must sink. The minimum sensible value here is about 1.5k, so this is fine and the shield
adds no pull-ups of its own. If you ever chain more I²C boards onto this one, each brings its own
pull-ups and the total drops: cut SJ1 on the MCP4725 board to take its 4.7k pair off the bus.
The ADS1115 breakout also pulls ALRT (UNO pin D2) up with 10k.

## Ordering and building

1. JLCPCB: upload `fab/mie1001_daq_simple_gerbers.zip`, 2 layers, 1.6 mm, HASL is fine.
   **Rev D: turn on PCB Assembly (top side)** and upload `fab/jlcpcb_bom.csv` and `fab/jlcpcb_cpl.csv`
   (16 SMD preamp parts, 11 BOM lines). Check the parts' rotation in JLC's preview, especially U3, U4
   and CR3, and that C59781 (100 MΩ), C124427 (LMP7721) and C15849 (1 µF) are in stock.
2. Solder, lowest parts first (rev D adds R4, standing up with its body on the circle, and the J5 SMA): CR1, CR2 (lying flat, **stripe towards the K on the board**), R1 and
   R2 (lying flat), C1, R3 (standing up, body on the circle), then the female headers (keep them straight: plug the
   breakout in while soldering), the terminal blocks, and finally the stacking headers.
3. **Trim every lead under the board flush. This is required, not optional.** The ADS1115 socket
   and J4 sit right above the UNO's ATmega chip, and CR1, CR2 and C1 are in the same band. An untrimmed
   socket lead sticks out about 1.6 mm and a terminal pin about 2.9 mm. The ATmega on the SMD UNO is flat, but check the clearance
   over the rest of that area with the real boards before you solder everything down.
4. Plug the breakouts in **component side up**, matching the pin names on the breakout to the names on
   the shield: VDD on the left for the ADS1115, and OUT at the top (at the ▼) for the MCP4725. Rotated
   180° the MCP4725 gets 5 V on its GND pin.

## Firmware notes

- ADS1115 at **0x48**, MCP4725 at **0x60**. Libraries: Adafruit ADS1X15 and Adafruit MCP4725.
- **`dac.begin(0x60)`**: the Adafruit_MCP4725 library defaults to 0x62, so a plain `dac.begin()`
  finds nothing. `ads.begin()` (0x48) is correct as is.
- Read the signal on A0. `ads.setGain(GAIN_TWOTHIRDS)` gives ±6.144 V full scale. For a small
  signal turn the gain up instead of adding an amplifier: `GAIN_SIXTEEN` gives ±0.256 V full scale
  and ~7.8 µV steps.
- **The input is filtered at 339 Hz** (R2 with C1), so the board cannot follow anything faster.
  Leave C1 out if you need the bandwidth.
- **For 50 Hz mains hum, use the ADC, not the filter.** Set a low data rate (`ads.setDataRate(RATE_ADS1115_8SPS)`),
  which averages over whole mains cycles, or average a batch of readings in the sketch. C1 barely
  touches 50 Hz. (TI's 50/60 Hz rejection figure at 8 SPS is for common-mode noise; there is no
  datasheet number for hum on a single-ended input, so measure it.)
- **J4's spare inputs (the ADS1115's A1–A3, not the UNO's) have no resistor, clamp or filter.** They go straight to the chip. Keep
  them under 0–VDD, and tie them to GND if you don't use them.
- **The useful input range is 0 V to VDD** (the USB 5 V, often only 4.8 V). This board expects a
  voltage from Team 3's preamp, not the raw detector current. R2 protects the chip from a preamp
  that overshoots, but readings above VDD are not valid.
- The MCP4725 powers up at mid-scale (2.5 V on QPS OUT). Write 0 to its EEPROM once.
- Trigger in: `pinMode(8, INPUT)`, active HIGH. R3 holds D8 low when nothing is connected. Use 5 V
  logic if you can: the ATmega needs 3.0 V for a HIGH, so 3.3 V logic (3.27 V at D8 after the R1/R3 divider) has under 0.3 V to spare.
  R1 limits the current if the trigger goes a little above 5 V. **Never feed it 12 V**: that pushes
  6.5 mA into the ATmega's input clamp, past its absolute maximum.
- ALRT goes to **UNO pin 2**: `pinMode(2, INPUT)` is enough, the breakout has the pull-up. (The diodes are named CR1 and CR2 and the UNO is ARD1, so "D2" and "A1" on this board
  always mean the UNO's pins.)

## Compared with the full board (`../mie1001_daq_board`, rev E)

This one has no electrometer amplifier and no guard ring: it digitises a voltage that someone
else has already made. Since rev C it does have basic input protection (R2 with CR1/CR2) and a
339 Hz filter (R2 with C1), but nothing that can measure a current. That is exactly what the class
breakouts are for, and it is much easier to build and debug. For picoamp detector currents,
use the full board.

## Files

`generate_schematic.py` and `generate_pcb.py` generate everything (the PCB script reuses the
UNO geometry and the router of the full board); `./build.sh` rebuilds and re-runs all checks.
The possum and the prayer to the machine gods are in `generate_pcb.py`, `possum()`.
