"""
Trajectory evaluation script for EuRoC MAV dataset.
Usage:
    python evaluate_trajectory.py --gt results/data.csv --est results/MH_01_easy_svo.txt
    python evaluate_trajectory.py --gt results/data.csv --est results/MH_01_easy_svo.txt --no_scale
    python evaluate_trajectory.py --gt results/gt_tum.txt --est results/MH_01_easy_svo.txt --gt_format tum

Input formats:
    GT:  EuRoC CSV (data.csv) or TUM (timestamp_s tx ty tz qx qy qz qw)
    EST: TUM format (timestamp_s tx ty tz qx qy qz qw)
"""

import argparse
import copy
import csv
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from evo.core import metrics, sync
from evo.core.metrics import PoseRelation
from evo.tools import file_interface


def euroc_csv_to_tum(csv_path: str, tum_path: str):
    """Convert EuRoC state_groundtruth data.csv to TUM format."""
    with open(csv_path) as fin, open(tum_path, 'w') as fout:
        fout.write("# timestamp tx ty tz qx qy qz qw\n")
        reader = csv.reader(fin)
        next(reader)  # skip header
        for row in reader:
            ts = float(row[0]) / 1e9          # ns -> s
            px, py, pz = row[1], row[2], row[3]
            qw, qx, qy, qz = row[4], row[5], row[6], row[7]  # EuRoC: qw first
            fout.write(f"{ts:.9f} {px} {py} {pz} {qx} {qy} {qz} {qw}\n")
    print(f"Converted GT to TUM: {tum_path}")


def load_trajectories(gt_path: str, est_path: str, gt_format: str,
                      max_time_diff: float = 0.05):
    if gt_format == 'euroc':
        tum_path = gt_path.replace('.csv', '_tum.txt')
        euroc_csv_to_tum(gt_path, tum_path)
        gt_path = tum_path

    traj_ref = file_interface.read_tum_trajectory_file(gt_path)
    traj_est = file_interface.read_tum_trajectory_file(est_path)

    traj_ref_s, traj_est_s = sync.associate_trajectories(
        traj_ref, traj_est, max_diff=max_time_diff)
    print(f"GT  poses: {len(traj_ref.timestamps)}")
    print(f"EST poses: {len(traj_est.timestamps)}")
    print(f"Synced  : {len(traj_ref_s.timestamps)} pairs")
    return traj_ref_s, traj_est_s


def compute_metrics(traj_ref, traj_est_raw, correct_scale: bool):
    traj_est = copy.deepcopy(traj_est_raw)
    r_a, t_a, s = traj_est.align(traj_ref, correct_scale=correct_scale)

    ape_metric = metrics.APE(PoseRelation.translation_part)
    ape_metric.process_data((traj_ref, traj_est))
    ape_stats  = ape_metric.get_all_statistics()
    ape_errors = ape_metric.error

    rpe_metric = metrics.RPE(PoseRelation.translation_part, delta=1.0,
                              delta_unit=metrics.Unit.meters, all_pairs=False)
    rpe_metric.process_data((traj_ref, traj_est))
    rpe_stats  = rpe_metric.get_all_statistics()
    rpe_errors = rpe_metric.error

    path_len  = traj_ref.path_length
    drift_pct = (ape_stats['rmse'] / path_len) * 100

    return traj_est, ape_stats, ape_errors, rpe_stats, rpe_errors, path_len, drift_pct, s


def kitti_eval(traj_ref, traj_est_aligned, segment_lengths):
    """
    KITTI-style evaluation: t_rel [%] and r_rel [deg/m] averaged over
    all valid subsequences of each fixed length.
    """
    ref_xyz   = traj_ref.positions_xyz
    ref_poses = traj_ref.poses_se3
    est_poses = traj_est_aligned.poses_se3

    # Cumulative distances along reference path
    dists    = np.zeros(len(ref_xyz))
    diffs    = np.diff(ref_xyz, axis=0)
    dists[1:] = np.cumsum(np.linalg.norm(diffs, axis=1))

    results = {}
    for d in segment_lengths:
        t_errs, r_errs = [], []
        for i in range(len(ref_poses)):
            target = dists[i] + d
            if target > dists[-1]:
                break
            j = int(np.searchsorted(dists, target))
            if j >= len(ref_poses):
                break

            T_gt_rel  = np.linalg.inv(ref_poses[i]) @ ref_poses[j]
            T_est_rel = np.linalg.inv(est_poses[i]) @ est_poses[j]
            T_err     = np.linalg.inv(T_gt_rel) @ T_est_rel

            t_err = np.linalg.norm(T_err[:3, 3])
            cos_a = np.clip((np.trace(T_err[:3, :3]) - 1) / 2, -1, 1)
            r_err = np.degrees(np.arccos(cos_a))

            t_errs.append(t_err / d * 100)   # %
            r_errs.append(r_err / d)          # deg/m

        if t_errs:
            results[d] = dict(
                t_rel=np.mean(t_errs),
                t_rel_med=np.median(t_errs),
                r_rel=np.mean(r_errs),
                r_rel_med=np.median(r_errs),
                n=len(t_errs),
            )
    return results


def print_kitti_results(kitti_res):
    print("\n=== KITTI-style Evaluation ===")
    print(f"  {'Seg [m]':>8}  {'t_rel [%]':>10}  {'r_rel [°/m]':>12}  {'samples':>8}")
    print("  " + "-" * 46)
    for d, v in sorted(kitti_res.items()):
        print(f"  {d:>8.0f}  {v['t_rel']:>10.4f}  {v['r_rel']:>12.4f}  {v['n']:>8}")


def print_results(ape_stats, rpe_stats, path_len, drift_pct, scale):
    print("\n=== ATE — Absolute Trajectory Error (m) ===")
    for k in ['rmse', 'mean', 'median', 'std', 'min', 'max']:
        print(f"  {k:8s}: {ape_stats[k]:.4f}")

    print("\n=== RPE — Relative Pose Error per 1m (m) ===")
    for k in ['rmse', 'mean', 'median', 'std', 'min', 'max']:
        print(f"  {k:8s}: {rpe_stats[k]:.4f}")

    print(f"\n=== Summary ===")
    print(f"  Path length    : {path_len:.2f} m")
    print(f"  Scale factor   : {scale:.4f}")
    print(f"  Drift (RMSE/L) : {drift_pct:.2f}%")


def plot_kitti(out_dir, kitti_res, dataset_name):
    if not kitti_res:
        return
    segs   = sorted(kitti_res.keys())
    t_vals = [kitti_res[d]['t_rel'] for d in segs]
    r_vals = [kitti_res[d]['r_rel'] for d in segs]
    labels = [f"{int(d)}m" for d in segs]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle(f'KITTI-style Evaluation — {dataset_name}', fontsize=13)

    bars1 = ax1.bar(labels, t_vals, color='steelblue', edgecolor='white', width=0.6)
    ax1.set(xlabel='Segment length', ylabel='t_rel [%]',
            title='Translational drift per segment')
    ax1.grid(True, axis='y', alpha=0.4)
    for bar, v in zip(bars1, t_vals):
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.05,
                 f'{v:.2f}%', ha='center', va='bottom', fontsize=9)

    bars2 = ax2.bar(labels, r_vals, color='darkorange', edgecolor='white', width=0.6)
    ax2.set(xlabel='Segment length', ylabel='r_rel [°/m]',
            title='Rotational drift per segment')
    ax2.grid(True, axis='y', alpha=0.4)
    for bar, v in zip(bars2, r_vals):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.001,
                 f'{v:.3f}', ha='center', va='bottom', fontsize=9)

    fig.tight_layout()
    fig.savefig(f'{out_dir}/kitti_style.png', dpi=150, bbox_inches='tight')
    plt.close()


def save_plots(out_dir, traj_ref, traj_est_aligned,
               ape_errors, ape_stats,
               rpe_errors, rpe_stats, dataset_name):
    os.makedirs(out_dir, exist_ok=True)

    t0      = traj_ref.timestamps[0]
    time_ax = traj_ref.timestamps - t0
    ref_xyz = traj_ref.positions_xyz
    est_xyz = traj_est_aligned.positions_xyz

    # 1. Trajectory XY
    fig, ax = plt.subplots(figsize=(9, 7))
    ax.plot(ref_xyz[:,0], ref_xyz[:,1], 'b-', lw=1.5, label='Ground Truth')
    ax.plot(est_xyz[:,0], est_xyz[:,1], 'r-', lw=1.5, label='Estimated')
    ax.plot(ref_xyz[0,0], ref_xyz[0,1], 'bs', ms=9)
    ax.plot(est_xyz[0,0], est_xyz[0,1], 'r^', ms=9)
    ax.set(xlabel='X [m]', ylabel='Y [m]',
           title=f'Trajectory XY — {dataset_name}')
    ax.legend(); ax.grid(True, alpha=0.4); ax.set_aspect('equal')
    fig.savefig(f'{out_dir}/trajectory_xy.png', dpi=150, bbox_inches='tight')
    plt.close()

    # 2. Trajectory 3D
    fig = plt.figure(figsize=(10, 8))
    ax3 = fig.add_subplot(111, projection='3d')
    ax3.plot(ref_xyz[:,0], ref_xyz[:,1], ref_xyz[:,2], 'b-', lw=1.5, label='GT')
    ax3.plot(est_xyz[:,0], est_xyz[:,1], est_xyz[:,2], 'r-', lw=1.5, label='EST')
    ax3.set(xlabel='X [m]', ylabel='Y [m]', zlabel='Z [m]',
            title=f'Trajectory 3D — {dataset_name}')
    ax3.legend()
    fig.savefig(f'{out_dir}/trajectory_3d.png', dpi=150, bbox_inches='tight')
    plt.close()

    # 3. ATE over time
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(time_ax, ape_errors, color='tomato', lw=1, alpha=0.85)
    ax.fill_between(time_ax, ape_errors, alpha=0.15, color='tomato')
    ax.axhline(ape_stats['mean'], color='navy', ls='--', lw=1.2,
               label=f"mean={ape_stats['mean']:.3f} m")
    ax.axhline(ape_stats['rmse'], color='green', ls=':', lw=1.5,
               label=f"rmse={ape_stats['rmse']:.3f} m")
    ax.set(xlabel='Time [s]', ylabel='ATE [m]',
           title=f'Absolute Trajectory Error — {dataset_name}')
    ax.legend(); ax.grid(True, alpha=0.4)
    fig.savefig(f'{out_dir}/ate_over_time.png', dpi=150, bbox_inches='tight')
    plt.close()

    # 4. RPE over time
    rpe_time = time_ax[:len(rpe_errors)]
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(rpe_time, rpe_errors, color='seagreen', lw=1, alpha=0.85)
    ax.fill_between(rpe_time, rpe_errors, alpha=0.15, color='seagreen')
    ax.axhline(rpe_stats['mean'], color='navy', ls='--', lw=1.2,
               label=f"mean={rpe_stats['mean']:.3f} m")
    ax.axhline(rpe_stats['rmse'], color='red', ls=':', lw=1.5,
               label=f"rmse={rpe_stats['rmse']:.3f} m")
    ax.set(xlabel='Time [s]', ylabel='RPE [m]',
           title=f'Relative Pose Error (1m) — {dataset_name}')
    ax.legend(); ax.grid(True, alpha=0.4)
    fig.savefig(f'{out_dir}/rpe_over_time.png', dpi=150, bbox_inches='tight')
    plt.close()

    # 5. ATE heatmap on trajectory
    fig, ax = plt.subplots(figsize=(9, 7))
    sc = ax.scatter(est_xyz[:,0], est_xyz[:,1], c=ape_errors,
                    cmap='RdYlGn_r', s=5, vmin=0)
    ax.plot(ref_xyz[:,0], ref_xyz[:,1], 'b-', lw=1, alpha=0.5, label='GT')
    cbar = plt.colorbar(sc, ax=ax); cbar.set_label('ATE [m]')
    ax.set(xlabel='X [m]', ylabel='Y [m]',
           title=f'ATE Heatmap — {dataset_name}')
    ax.legend(); ax.grid(True, alpha=0.4); ax.set_aspect('equal')
    fig.savefig(f'{out_dir}/ate_heatmap.png', dpi=150, bbox_inches='tight')
    plt.close()

    print(f"\nPlots saved to: {out_dir}/")
    for f in sorted(os.listdir(out_dir)):
        print(f"  {f}")


def main():
    parser = argparse.ArgumentParser(description="Trajectory evaluation for EuRoC MAV")
    parser.add_argument('--gt',  required=True, help='Ground truth file')
    parser.add_argument('--est', required=True, help='Estimated trajectory (TUM format)')
    parser.add_argument('--gt_format', default='euroc', choices=['euroc', 'tum'],
                        help='GT format: euroc (data.csv) or tum')
    parser.add_argument('--no_scale', action='store_true',
                        help='SE3 alignment only (no scale correction). Use for metric VIO.')
    parser.add_argument('--out', default=None,
                        help='Output directory for plots (default: next to --est file)')
    parser.add_argument('--max_diff', type=float, default=0.05,
                        help='Max timestamp diff for sync [s] (default: 0.05)')
    parser.add_argument('--name', default=None,
                        help='Dataset name for plot titles')
    parser.add_argument('--segments', nargs='+', type=float,
                        default=[5, 10, 20, 30, 50],
                        help='Segment lengths for KITTI eval [m] (default: 5 10 20 30 50)')
    args = parser.parse_args()

    correct_scale = not args.no_scale
    out_dir = args.out or os.path.join(os.path.dirname(args.est), 'plots')
    dataset_name = args.name or os.path.basename(args.est).replace('.txt', '')

    print(f"GT  : {args.gt}  [{args.gt_format}]")
    print(f"EST : {args.est}")
    print(f"Mode: {'Sim3 (scale corrected)' if correct_scale else 'SE3 (metric)'}")

    traj_ref, traj_est = load_trajectories(
        args.gt, args.est, args.gt_format, args.max_diff)

    traj_aligned, ape_stats, ape_errors, rpe_stats, rpe_errors, \
        path_len, drift_pct, scale = compute_metrics(traj_ref, traj_est, correct_scale)

    print_results(ape_stats, rpe_stats, path_len, drift_pct, scale)

    kitti_res = kitti_eval(traj_ref, traj_aligned, args.segments)
    print_kitti_results(kitti_res)

    save_plots(out_dir, traj_ref, traj_aligned,
               ape_errors, ape_stats, rpe_errors, rpe_stats, dataset_name)
    plot_kitti(out_dir, kitti_res, dataset_name)


if __name__ == '__main__':
    main()
