# MIE1001 — Team 5 acquisition simulation (Wokwi)

Full acquisition loop simulated in Wokwi:

    Arduino Uno --I2C--> MCP4725 (0x60) --analog--> quad --analog--> ADS1115 (0x48) --I2C--> Arduino Uno

The Uno sets a mass command on the DAC, the quad chip returns the ion
signal at that mass, the ADC reads it back. Sweeping the DAC produces a
mass spectrum.

## Files

| File | What it is |
|---|---|
| `sketch.ino` | Scan program: sweeps the DAC, reads the ADC, prints CSV |
| `diagram.json` | Wiring |
| `libraries.txt` | Adafruit ADS1X15 |
| `mcp4725.chip.c/.json` | 12-bit DAC, I2C 0x60 (Team 4's block) |
| `quad.chip.c/.json` | Quadrupole + detector model |
| `ads1115.chip.c/.json` | 16-bit ADC, I2C 0x48 (Team 5's block) |
| `signal.chip.c/.json` | Standalone free-running signal source (ADC test only) |

## Wiring

I2C bus (shared): Uno A4 = SDA, A5 = SCL. MCP4725 at 0x60, ADS1115 at 0x48.
Power: 5V and GND to both breakouts.
Analog path: MCP4725 OUT -> quad IN, quad OUT -> ADS1115 A0.

## Simulated sample

PEG1000. Peaks every 44 Da (ethylene oxide repeat) under a Gaussian
envelope centred near m/z 1010. Peak n sits at:

    m/z = 44n + 41        n = 10 .. 35

Mass command mapping in `quad.chip.c`: 0-5 V spans 0-2000 m/z, so

    DAC value = (m/z) / 2000 * 4095

## Calibration exercise

1. Run the scan, capture the CSV from the serial monitor.
2. Find peak positions in DAC counts.
3. Assign each to its known m/z using the 44 Da spacing.
4. Least-squares fit m/z = a * DAC + b.
5. Check residuals -- they should be flat, not curved.

## Parameters worth changing

`sketch.ino`
- `DWELL_MS` -- settling time per step. Set to 0 and watch peaks distort.
- `SCAN_STEP` -- 1 for full resolution, 2+ for a faster sweep.
- `AVERAGES` -- reads averaged per step; trades speed for noise.
- `ads.setGain()` -- GAIN_ONE is +/-4.096 V. Higher gain resolves more but clips sooner.

`quad.chip.c`
- `PEAK_SIGMA` -- peak width, i.e. resolution.
- `NOISE` -- baseline noise amplitude.
- `MZ_MAX` -- mass range spanned by the 0-5 V command.

## Limitations

The quad chip is a lookup, not physics. Real quadrupoles have
mass-dependent transmission, resolution set by the DC/RF ratio, and
non-Gaussian peak shapes. This is enough to develop and validate
acquisition software, not to predict instrument performance.

## Notes

- The custom chips (`*.chip.c`) were generated with AI (Claude) and checked by us; see the AI declaration in the report.
- `ADS1115_INPUT/` is a smaller first test: the ADS1115 alone with a signal source.
- To run: create a new Arduino Uno project on wokwi.com and upload these files (the chips need the "custom chip" feature).
- Files recovered from a local backup on 25 September 2026 (originally made 3 September).
