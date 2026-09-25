# Self-tests on the real Uno, 20 September 2026

Serial output of `firmware/ADS1115_selftest` and `firmware/MCP4725_standalone_test` from the first
breadboard session, copied from what was pasted in the team chat that day. The measurements are real;
the two figures are re-plotted / re-typeset from those numbers (not screenshots of the IDE).

- `ads_selftest_2026-09-20.txt` - the 17 repeated ADS1115 readings (raw counts, GAIN_TWOTHIRDS, 0.1875 mV/count):
  A0 = 3.3 V pin, A1 = GND, A2 = 5 V pin, A3 = floating.
- `fig_ads_selftest.png` - the readings, and each channel's scatter around its mean.
  Grounded input: 1.1 counts rms (0.2 mV); 3.3 V pin: 0.8 counts (0.15 mV).
- `fig_serial_monitor_debug.png` - the debugging sequence, shortened: ADS1115 not found until the wiring was
  fixed, then all channels PASS; MCP4725 with SDA/SCL stuck low, then no chip, then PASS
  (DAC 3584 -> Uno A0 896, expected 895; DAC 4095 -> 1023).
