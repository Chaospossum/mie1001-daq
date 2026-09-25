# Simulations (NOT measured data)

`basic.py` simulates `firmware/MCP4725_sine_scope`: the sketch's own logic (64-point sine, `sine[i] / 4`,
`analogRead(A0)`) with the DAC and the Uno ADC modelled on the same 5 V rail, the +1 count offset measured at
code 3584 on 24 Sept, and ~0.5 count noise. `plotter_look.py` draws it in the style of the Arduino IDE 2
Serial Plotter, with a banner saying it is a simulation. The sketch was run on the breadboard, but no
screenshot was kept.

`basic.py` also re-draws the real 20 Sept ADS1115 self-test numbers in the same style
(`../2026-09-20_selftest/fig_ads_selftest_plotter_style.png`, labelled as real data).

Run: `pip install numpy matplotlib && python basic.py`
