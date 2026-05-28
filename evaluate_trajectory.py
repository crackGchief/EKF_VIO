#!/usr/bin/env python3
import copy
import argparse
import os
import re
from datetime import datetime

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from evo.tools import file_interface
from evo.core  import sync, metrics


def load_tum(filepath):
    # Фильтруем битые строки (нулевые байты, возникают при kill record.py)
    import tempfile
    with open(filepath, 'rb') as f:
        raw = f.read()
    if b'\x00' in raw:
        lines = raw.split(b'\n')
        clean = [l.replace(b'\x00', b'').decode('utf-8', errors='ignore').strip()
                 for l in lines if l.replace(b'\x00', b'').strip()]
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        tmp.write('\n'.join(clean) + '\n')
        tmp.flush()
        tmp.close()
        filepath = tmp.name
    return file_interface.read_tum_trajectory_file(filepath)


def evaluate(gt_file, est_file, out_dir, correct_scale=True, max_diff=0.02):

    # --- 1. Загрузка ---
    traj_gt  = load_tum(gt_file)
    traj_est = load_tum(est_file)

    print(f"GT:  {len(traj_gt.timestamps)} поз")
    print(f"SVO: {len(traj_est.timestamps)} поз")

    # --- 2. Синхронизация по времени ---
    traj_gt, traj_est = sync.associate_trajectories(traj_gt, traj_est, max_diff)
    print(f"Совпало пар: {len(traj_gt.timestamps)}")

    # --- 3. Выравнивание ---
    traj_est_aligned = copy.deepcopy(traj_est)
    traj_est_aligned.align(traj_gt, correct_scale=correct_scale)
    align_str = "Sim3 (с коррекцией масштаба)" if correct_scale else "SE3 (без коррекции масштаба)"
    print(f"Выравнивание: {align_str}")

    # --- 4. Подсчёт ATE ---
    ate_metric = metrics.APE(metrics.PoseRelation.translation_part)
    ate_metric.process_data((traj_gt, traj_est_aligned))
    ate_stats = ate_metric.get_all_statistics()

    # --- 5. Вывод в терминал ---
    print("\n========== ATE (м) ==========")
    print(f"  RMSE:   {ate_stats['rmse']:.4f}")
    print(f"  Mean:   {ate_stats['mean']:.4f}")
    print(f"  Median: {ate_stats['median']:.4f}")
    print(f"  Std:    {ate_stats['std']:.4f}")
    print(f"  Max:    {ate_stats['max']:.4f}")
    print(f"  Min:    {ate_stats['min']:.4f}")
    print("==============================\n")

    

    # --- 7. Парсим svo.log для событий реинициализации ---
    reinit_times = []
    init_times   = []
    svo_log_file = os.path.join(out_dir, 'svo.log')

    if os.path.exists(svo_log_file):
        t0_ros  = traj_gt.timestamps[0]
        t_end   = traj_gt.timestamps[-1]
        ansi_re = re.compile(r'\x1b\[[0-9;]*m')
        ts_re   = re.compile(r'\[\d+\.\d+, (\d+\.\d+)\]')

        with open(svo_log_file) as f:
            for line in f:
                line = ansi_re.sub('', line)
                m = ts_re.search(line)
                if not m:
                    continue
                rel_t = float(m.group(1)) - t0_ros
                if rel_t < -2 or rel_t > (t_end - t0_ros) + 5:
                    continue
                if 'DepthFilter: RESET' in line:
                    reinit_times.append(rel_t)
                elif 'Init: Triangulated' in line:
                    pts_m = re.search(r'Triangulated (\d+)', line)
                    pts = int(pts_m.group(1)) if pts_m else 0
                    init_times.append((rel_t, pts))

        grouped_resets = []
        for rt in sorted(reinit_times):
            if grouped_resets and rt - grouped_resets[-1] < 2.0:
                continue
            grouped_resets.append(rt)

        print(f"Найдено событий: RESET={len(grouped_resets)}, Init={len(init_times)}")
    else:
        grouped_resets = []
        print("svo.log не найден — без событий на графике")

    # --- 8. График ATE по времени ---
    errors  = ate_metric.error
    t0      = traj_gt.timestamps[0]
    time_ax = traj_gt.timestamps - t0

    fig, ax = plt.subplots(figsize=(14, 5))
    ax.plot(time_ax, errors, color='steelblue', lw=1, alpha=0.9, label='ATE')
    ax.fill_between(time_ax, errors, alpha=0.15, color='steelblue')
    ax.axhline(ate_stats['rmse'], color='red', ls='--',  lw=1.5, label=f"rmse  = {ate_stats['rmse']:.4f} м")

    first_reset = True
    for rt in grouped_resets:
        ax.axvline(rt, color='C0', ls='--',
                   label='DepthFilter: RESET' if first_reset else '_')
        first_reset = False

    first_init = True
    for (it, pts) in init_times:
        ax.axvline(it, color='seagreen', ls='--',
                   label='Init: Triangulated' if first_init else '_')
        first_init = False

    ax.set(xlabel='Время (с)', ylabel='ATE (м)',title=f'{os.path.basename(out_dir)}')
    ax.legend(fontsize=9)
    fig.tight_layout()

    plot_file = os.path.join(out_dir, 'ate_over_time.png')
    fig.savefig(plot_file, dpi=150)
    plt.close()
    print(f"График сохранён: {plot_file}")

    return ate_stats


if __name__ == '__main__':
    BASE = os.path.dirname(os.path.abspath(__file__))
    TRAJ_DIR = os.path.join(BASE, 'trajectory_results')

    parser = argparse.ArgumentParser()
    parser.add_argument('--bag_name',
        default='MH_01_easy',
        help='имя датасета без .bag (например MH_01_easy)')
    parser.add_argument('--out_dir',
        default=None,
        help='папка для сохранения результатов')
    parser.add_argument('--no_scale', action='store_true',
        help='не корректировать масштаб (для стерео/IMU)')
    args = parser.parse_args()

    # Пути к файлам строятся из bag_name автоматически
    gt_file  = os.path.join(TRAJ_DIR, args.bag_name, f"{args.bag_name}_gt.txt")
    est_file = os.path.join(TRAJ_DIR, args.bag_name, f"{args.bag_name}_svo.txt")
    out_dir  = args.out_dir or os.path.join(TRAJ_DIR, args.bag_name)

    evaluate(gt_file, est_file, out_dir, correct_scale=not args.no_scale)
