"""Draw data in the style of the Arduino IDE 2 Serial Plotter, clearly marked as a simulation."""
import numpy as np, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

def plotter(series, fname, baud='115200', banner='SIMULATION: model output, not measured data', title='Serial Plotter - simulated port', port='the simulated port'):
    W, H = 12.0, 6.4
    fig = plt.figure(figsize=(W, H), dpi=150); fig.patch.set_facecolor('#ffffff')
    bg = fig.add_axes([0, 0, 1, 1]); bg.axis('off'); bg.set_xlim(0, 1); bg.set_ylim(0, 1)
    # window title bar
    bg.add_patch(Rectangle((0, 0.945), 1, 0.055, color='#e7e7e7'))
    bg.text(0.5, 0.972, title, ha='center', va='center', fontsize=10, color='#333')
    for k, c in enumerate(['#ff5f57', '#febc2e', '#28c840']):
        bg.add_patch(plt.Circle((0.975 - k * 0.018, 0.972), 0.006, color=c, transform=bg.transAxes))
    # banner
    bg.add_patch(Rectangle((0, 0.905), 1, 0.04, color='#fff3cd'))
    bg.text(0.5, 0.925, banner, ha='center', va='center', fontsize=9.5, color='#8a5a00', weight='bold')
    # legend row (IDE 2 style: coloured checkbox + label)
    x = 0.02
    for name, y, col in series:
        bg.add_patch(FancyBboxPatch((x, 0.858), 0.012, 0.022, boxstyle='round,pad=0.002', color=col))
        bg.text(x + 0.0035, 0.869, '✓', color='white', fontsize=7, va='center')
        bg.text(x + 0.018, 0.869, name, fontsize=9.5, va='center', color='#333')
        x += 0.018 + 0.0075 * len(name) + 0.03
    bg.text(0.835, 0.869, 'Interpolate', fontsize=9, va='center', color='#333')
    bg.add_patch(FancyBboxPatch((0.905, 0.861), 0.028, 0.016, boxstyle='round,pad=0.004', color='#008184'))
    bg.add_patch(plt.Circle((0.928, 0.869), 0.0065, color='white', transform=bg.transAxes))
    bg.text(0.955, 0.869, 'II', fontsize=11, va='center', color='#4e5b61')
    bg.text(0.975, 0.869, '⌫', fontsize=11, va='center', color='#4e5b61')
    # plot
    ax = fig.add_axes([0.06, 0.15, 0.925, 0.69])
    ax.set_facecolor('#ffffff')
    for s in ax.spines.values(): s.set_visible(False)
    ax.grid(True, color='#dae3e3', lw=0.8); ax.tick_params(colors='#4e5b61', labelsize=8.5, length=0)
    for name, y, col in series:
        ax.plot(np.arange(len(y)), y, color=col, lw=1.6)
    ax.set_xlim(0, len(series[0][1]) - 1)
    # bottom message bar
    bg.add_patch(Rectangle((0, 0), 1, 0.085, color='#f4f4f4'))
    bg.add_patch(FancyBboxPatch((0.015, 0.02), 0.72, 0.045, boxstyle='round,pad=0.003', ec='#c9d2d2', fc='white'))
    bg.text(0.025, 0.0425, "Type Message (Enter to send message to 'Arduino Uno' on " + port + ")", fontsize=8.5, va='center', color='#9aa5a5')
    for xx, t in [(0.75, 'New Line  ▾'), (0.87, f'{baud} baud  ▾')]:
        bg.add_patch(FancyBboxPatch((xx, 0.02), 0.105, 0.045, boxstyle='round,pad=0.003', ec='#c9d2d2', fc='white'))
        bg.text(xx + 0.01, 0.0425, t, fontsize=8.5, va='center', color='#333')
    fig.savefig(fname, dpi=150)

if __name__ == '__main__':
    d = np.loadtxt('sim_scan.csv', delimiter=',')
    cols = ['#0072B2', '#D55E00', '#009E73', '#E69F00']
    plotter([('code', d[:, 0], cols[0]), ('V_cmd', d[:, 1], cols[1]), ('I_pA', d[:, 2], cols[2]), ('V_diff', d[:, 3], cols[3])],
            'sim_plotter_shield_scan.png')
