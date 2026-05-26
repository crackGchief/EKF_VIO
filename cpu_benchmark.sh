#!/bin/bash
# Использование: bash cpu_benchmark.sh <container_name> [bag_name]
# Пример:        bash cpu_benchmark.sh svo_o MH_01_easy.bag

CONTAINER="${1:?Не укзан контейнер}"
BAG_NAME="${2:-MH_01_easy.bag}"
BAG_DURATION=180
OUT_DIR="$HOME/EKF_VIO/cpu_results"
mkdir -p "$OUT_DIR"


echo "[1/4] Запускаем SVO + bag..."
docker exec "$CONTAINER" bash -c \
  "source /opt/ros/noetic/setup.bash && \
   source /root/ros_ws/devel/setup.bash --extend && \
   source /root/svo_ws/devel/setup.bash --extend && \
   timeout ${BAG_DURATION} roslaunch /root/main_bag.launch bag_name:=${BAG_NAME} > /tmp/svo.log 2>&1" &
LAUNCH_PID=$!

echo "[2/4] Мониторинг CPU svo_node..."
python3 ~/EKF_VIO/cpu_monitor.py "$OUT_DIR/cpu_samples.txt"

wait $LAUNCH_PID 2>/dev/null

echo "[3/4] Копируем лог SVO..."
docker cp "$CONTAINER":/tmp/svo.log "$OUT_DIR/svo.log"

echo "[4/4] График и статистика..."
python3 ~/EKF_VIO/cpu_plot.py "$OUT_DIR"

echo ""
echo "Готово. Результаты: $OUT_DIR/"
