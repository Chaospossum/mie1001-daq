import numpy as np
from plotter_look import plotter
rng = np.random.default_rng(3)
# --- MCP4725_sine_scope, simulated: sketch logic 1:1, hardware modelled -------------------
N = 64
sine = (2048 + (2047.0 * np.sin(2 * np.pi * np.arange(N) / N))).astype(int)   # (int) truncation as in C
k = np.arange(160)                                   # 2.5 cycles on screen
code = sine[k % N]
sent = code // 4                                     # Serial.print(sine[i] / 4)  (integer division)
# DAC and Uno ADC share the 5 V rail, so read ~= code/4. Measured on the real board: code 3584 -> 896 (+1).
# Model: +0.5 count offset, ~0.5 count rms noise, MCP4725 zero-scale ~ +5 mV near code 0.
read = np.clip(np.round(code / 4 + 0.5 + 1.0 * (code < 20) + rng.normal(0, 0.5, k.size)), 0, 1023).astype(int)
np.savetxt('sim_sine_scope.csv', np.c_[sent, read], delimiter=',', fmt='%d', header='sent,read  (SIMULATED)', comments='')
plotter([('sent', sent, '#0072B2'), ('read', read, '#D55E00')], 'sim_plotter_sine_scope.png',
        banner='SIMULATION of MCP4725_sine_scope (model of the sketch + breadboard, not measured data)')
# --- ADS1115_selftest, REAL numbers from 20 Sept, drawn in plotter style ---------------------------
d = np.loadtxt('../2026-09-20_selftest/ads_selftest_2026-09-20.txt'); L = 0.1875e-3
plotter([('A0_3V3pin', d[:, 1] * L, '#0072B2'), ('A1_GND', d[:, 2] * L, '#D55E00'),
         ('A2_5Vpin', d[:, 3] * L, '#009E73'), ('A3_free', d[:, 4] * L, '#E69F00')],
        '../2026-09-20_selftest/fig_ads_selftest_plotter_style.png', baud='9600',
        banner='REAL DATA (20 Sept, 17 readings from the Serial Monitor) re-drawn in Serial Plotter style, not a screenshot', title='Serial Plotter - re-drawn from logged data', port='the Uno')
print('ok')
