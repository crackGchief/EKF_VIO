#!/usr/bin/env python3
import copy
import argparse
import os
from datetime import datetime

from evo.tools import file_interface
from evo.core  import sync, metrics


def load_tum(filepath):
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

    # --- 6. Сохранение в файл ---
    os.makedirs(out_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = os.path.join(out_dir, f"ate_{timestamp}.txt")

    with open(out_file, 'w') as f:
        f.write(f"GT файл:  {gt_file}\n")
        f.write(f"SVO файл: {est_file}\n")
        f.write(f"Выравнивание: {align_str}\n")
        f.write(f"GT поз: {len(traj_gt.timestamps)}\n")
        f.write(f"SVO поз: {len(traj_est.timestamps)}\n")
        f.write(f"\nATE (м):\n")
        f.write(f"  RMSE:   {ate_stats['rmse']:.4f}\n")
        f.write(f"  Mean:   {ate_stats['mean']:.4f}\n")
        f.write(f"  Median: {ate_stats['median']:.4f}\n")
        f.write(f"  Std:    {ate_stats['std']:.4f}\n")
        f.write(f"  Max:    {ate_stats['max']:.4f}\n")
        f.write(f"  Min:    {ate_stats['min']:.4f}\n")

    print(f"Результаты сохранены: {out_file}")
    return ate_stats


if __name__ == '__main__':
    BASE = os.path.dirname(os.path.abspath(__file__))

    parser = argparse.ArgumentParser()
    parser.add_argument('gt_file',
        nargs='?',
        default=os.path.join(BASE, 'trajectory_results', 'MH_01_easy.bag_gt.txt'),
        help='файл groundtruth (TUM формат)')
    parser.add_argument('est_file',
        nargs='?',
        default=os.path.join(BASE, 'trajectory_results', 'MH_01_easy.bag_svo.txt'),
        help='файл оценки SVO (TUM формат)')
    parser.add_argument('--out_dir',
        default=os.path.join(BASE, 'error_results'),
        help='папка для сохранения результатов')
    parser.add_argument('--no_scale', action='store_true',
        help='не корректировать масштаб (для стерео/IMU)')
    args = parser.parse_args()

    evaluate(args.gt_file, args.est_file, args.out_dir,
             correct_scale=not args.no_scale)
