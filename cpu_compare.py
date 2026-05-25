#!/usr/bin/env python3
"""
Сравнительный график CPU по всем датасетам.
Использование: python3 cpu_compare.py ~/EKF_VIO/cpu_results
"""
import sys, os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

results_root = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/EKF_VIO/cpu_results")

# Собираем все датасеты у которых есть cpu_samples.txt
datasets = {}
for name in sorted(os.listdir(results_root)):
    samples_file = os.path.join(results_root, name, "cpu_samples.txt")
    if os.path.isfile(samples_file):
        with open(samples_file) as f:
            vals = [float(x) for x in f.read().split() if x.strip()]
        if vals:
            datasets[name] = np.array(vals)

if not datasets:
    print("Нет данных — запусти cpu_benchmark.sh хотя бы для одного датасета")
    sys.exit(1)

print(f"Датасетов для сравнения: {len(datasets)}")

# ── График 1: все треки CPU на одном поле ─────────────────────────
colors = plt.cm.tab10(np.linspace(0, 1, len(datasets)))

fig, ax = plt.subplots(figsize=(14, 5))
for (name, vals), color in zip(datasets.items(), colors):
    t   = np.arange(len(vals))
    avg = vals.mean()
    ax.plot(t, vals, lw=1.0, alpha=0.7, color=color,
            label=f'{name}  avg={avg:.1f}%')

ax.axhline(100, color='gray', ls=':', lw=0.8, alpha=0.5, label='100% = 1 ядро')
ax.set(xlabel='Время (с)', ylabel='%CPU  (100% = 1 ядро)',
       title='CPU svo_node — Raspberry Pi 5, все датасеты')
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)
fig.tight_layout()
out1 = os.path.join(results_root, 'compare_timeline.png')
fig.savefig(out1, dpi=150)
print(f"График треков: {out1}")

# ── График 2: boxplot среднего по датасетам ───────────────────────
fig2, ax2 = plt.subplots(figsize=(max(6, len(datasets) * 1.5), 5))
names = list(datasets.keys())
avgs  = [datasets[n].mean() for n in names]
maxs  = [datasets[n].max()  for n in names]

x = np.arange(len(names))
w = 0.35
bars_avg = ax2.bar(x - w/2, avgs, w, label='Среднее CPU%', color='steelblue', alpha=0.8)
bars_max = ax2.bar(x + w/2, maxs, w, label='Макс CPU%',    color='tomato',    alpha=0.8)

for bar in bars_avg:
    ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
             f'{bar.get_height():.1f}', ha='center', va='bottom', fontsize=8)
for bar in bars_max:
    ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
             f'{bar.get_height():.1f}', ha='center', va='bottom', fontsize=8)

ax2.axhline(100, color='gray', ls=':', lw=0.8, alpha=0.5, label='100% = 1 ядро')
ax2.set_xticks(x)
ax2.set_xticklabels(names, rotation=15, ha='right')
ax2.set(ylabel='%CPU  (100% = 1 ядро)',
        title='Среднее и максимум CPU svo_node — Raspberry Pi 5')
ax2.legend(fontsize=8)
ax2.grid(True, alpha=0.3, axis='y')
fig2.tight_layout()
out2 = os.path.join(results_root, 'compare_bar.png')
fig2.savefig(out2, dpi=150)
print(f"График баров: {out2}")

# ── Таблица в терминале ───────────────────────────────────────────
print(f"\n{'Датасет':<25} {'Среднее':>10} {'Макс':>8} {'Мин':>8} {'Замеров':>9}")
print("-" * 65)
for name, vals in datasets.items():
    print(f"{name:<25} {vals.mean():>9.1f}% {vals.max():>7.1f}% "
          f"{vals.min():>7.1f}% {len(vals):>8}s")
