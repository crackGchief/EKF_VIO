#!/usr/bin/env python3
import time, os, sys, subprocess

OUT_FILE = sys.argv[1] if len(sys.argv) > 1 else "/home/mononoki/EKF_VIO/cpu_results/cpu_samples.txt"
OUT_DIR  = os.path.dirname(OUT_FILE)

def cpu_ticks(pid):
    with open(f"/proc/{pid}/stat") as f:
        fields = f.read().split()
    return int(fields[13]) + int(fields[14])

CLK_TCK = os.sysconf("SC_CLK_TCK")

print("Жду svo_node...", flush=True)
while True:
    r = subprocess.run(["pgrep", "-f", "svo_node"],
                       capture_output=True, text=True)
    if r.returncode == 0:
        pid = int(r.stdout.strip().splitlines()[0])
        break
    time.sleep(1)

t_start = time.time()
print(f"svo_node найден на хосте, PID={pid}", flush=True)

# Сохраняем t_start — нужен plot.py для сопоставления с логом
with open(os.path.join(OUT_DIR, "t_start.txt"), "w") as f:
    f.write(str(t_start))

samples    = []
prev_ticks = cpu_ticks(pid)
prev_t     = t_start

while True:
    time.sleep(1)
    try:
        curr_ticks = cpu_ticks(pid)
    except FileNotFoundError:
        print("svo_node завершился.", flush=True)
        break

    curr_t  = time.time()
    cpu_pct = ((curr_ticks - prev_ticks) / CLK_TCK) / (curr_t - prev_t) * 100
    samples.append(cpu_pct)
    print(f"  {len(samples):3d}s  {cpu_pct:6.1f}%", flush=True)

    prev_ticks = curr_ticks
    prev_t     = curr_t

with open(OUT_FILE, "w") as f:
    f.write("\n".join(f"{v:.1f}" for v in samples))
print(f"\nСохранено {len(samples)} замеров в {OUT_FILE}")
