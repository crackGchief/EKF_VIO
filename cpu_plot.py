#!/usr/bin/env python3
import sys, os, re
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

out_dir = sys.argv[1]

with open(os.path.join(out_dir, "cpu_samples.txt")) as f:
    vals = [float(x) for x in f.read().split() if x.strip()]

if not vals:
    print("Нет данных в cpu_samples.txt")
    sys.exit(1)

vals = np.array(vals)
t    = np.arange(len(vals))
avg  = vals.mean()

# ── Парсим svo.log ────────────────────────────────────────────────
reinit_times = []
init_times   = []

t_start_file = os.path.join(out_dir, "t_start.txt")
svo_log_file = os.path.join(out_dir, "svo.log")

if os.path.exists(t_start_file) and os.path.exists(svo_log_file):
    with open(t_start_file) as f:
        t_start = float(f.read().strip())

    ansi_re = re.compile(r'\x1b\[[0-9;]*m')
    ts_re   = re.compile(r'\[(\d+\.\d+),')

    with open(svo_log_file) as f:
        for line in f:
            line = ansi_re.sub('', line)
            m = ts_re.search(line)
            if not m:
                continue
            rel_t = float(m.group(1)) - t_start
            if rel_t < -2 or rel_t > len(vals) + 5:
                continue
            if 'DepthFilter: RESET' in line:
                reinit_times.append(rel_t)
            elif 'Init: Triangulated' in line:
                pts_m = re.search(r'Triangulated (\d+)', line)
                pts = int(pts_m.group(1)) if pts_m else '?'
                init_times.append((rel_t, pts))

    grouped_resets = []
    for rt in sorted(reinit_times):
        if grouped_resets and rt - grouped_resets[-1] < 2.0:
            continue
        grouped_resets.append(rt)

    print(f"Найдено: RESET={len(grouped_resets)}, Init={len(init_times)}")
else:
    grouped_resets = []
    print("t_start.txt или svo.log не найден — без событий")

# ── График ────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(14, 5))

ax.fill_between(t, vals, alpha=0.2, color='steelblue')
ax.plot(t, vals, color='steelblue', lw=1.4, label='svo_node CPU%')
ax.axhline(avg, color='red', ls='--', lw=1.4,
           label=f'Среднее: {avg:.1f}%')
ax.axhline(100, color='gray', ls=':', lw=0.8, alpha=0.5,
           label='100% = 1 ядро')

first_reset = True
for rt in grouped_resets:
    ax.axvline(rt, color='tomato', ls='--', lw=1.2, alpha=0.85,
               label='DepthFilter: RESET' if first_reset else '_')
    first_reset = False

first_init = True
for (it, pts) in init_times:
    ax.axvline(it, color='seagreen', ls='-', lw=1.2, alpha=0.85,
               label='Init: Triangulated' if first_init else '_')
    ax.text(it + 0.5, vals.max() * 0.85, f'{pts}pt',
            color='seagreen', fontsize=7, va='top')
    first_init = False

ax.set(xlabel='Время (с)', ylabel='%CPU  (100% = 1 ядро)',
       title='CPU svo_node — Raspberry Pi 5, MH_01_easy')
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(out_dir, 'cpu_usage.png'), dpi=150)
print("График: cpu_usage.png")

stats = (
    f"=== CPU svo_node ===\n"
    f"  Замеров      : {len(vals)}\n"
    f"  Среднее      : {avg:.1f}%  (~{avg/100:.2f} ядра из 4)\n"
    f"  Максимум     : {vals.max():.1f}%\n"
    f"  Минимум      : {vals.min():.1f}%\n"
    f"  Стд. откл.   : {vals.std():.1f}%\n"
    f"  Реинитов     : {len(grouped_resets)}\n"
    f"  Успешных init: {len(init_times)}\n"
)
print(stats)
with open(os.path.join(out_dir, 'cpu_stats.txt'), 'w') as f:
    f.write(stats)
