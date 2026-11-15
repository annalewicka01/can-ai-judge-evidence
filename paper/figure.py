"""Figure 1: correct assurance ratings by model and prompt (rounds 2-3 pooled)."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
summary = json.loads((ROOT / 'results/discrimination-summary.json').read_text())
MODELS = [('astra', 'astra'), ('mini', 'mini'), ('nano', 'nano')]
ARMS = ['passive', 'ordinary', 'targeted']
SERIES = [('D', 'Deficient papers', '#2a78d6'), ('A', 'Adequate papers', '#eb6834')]
INK, MUTED, SURFACE = '#0b0b0b', '#52514e', '#fcfcfb'


def count(model, arm, kind):
    return sum(summary[i]['cells'][f'{model}|{arm}'][f'{kind}_correct'] for i in ('iteration_2', 'iteration_3'))


plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9})
fig, axes = plt.subplots(1, 3, figsize=(7.0, 2.6), sharey=True, facecolor=SURFACE)
width = 0.38
for ax, (key, label) in zip(axes, MODELS):
    ax.set_facecolor(SURFACE)
    for j, (kind, _, colour) in enumerate(SERIES):
        xs = [i + (j - 0.5) * (width + 0.02) for i in range(len(ARMS))]
        ys = [count(key, arm, kind) for arm in ARMS]
        ax.bar(xs, ys, width, color=colour, zorder=2)
        for x, y in zip(xs, ys):
            ax.text(x, y + 0.4, str(y), ha='center', va='bottom', fontsize=7.5, color=INK)
    ax.set_xticks(range(len(ARMS)), ARMS, color=INK)
    ax.set_title(label, fontsize=9, color=INK)
    ax.set_ylim(0, 23)
    ax.set_yticks([0, 10, 20])
    for side in ('top', 'right'):
        ax.spines[side].set_visible(False)
    for side in ('left', 'bottom'):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=MUTED, length=2)
axes[0].set_ylabel('Correct ratings (of 20)', color=INK)
fig.legend([plt.Rectangle((0, 0), 1, 1, color=c) for _, _, c in SERIES], [n for _, n, _ in SERIES],
           loc='upper center', ncol=2, frameon=False, bbox_to_anchor=(0.5, 1.04))
fig.tight_layout(rect=(0, 0, 1, 0.92))
fig.savefig(Path(__file__).with_name('figure1.png'), dpi=300, facecolor=SURFACE)
