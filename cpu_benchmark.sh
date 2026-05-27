#!/bin/bash

CONTAINER="${1:?Не указан контейнер}"
BAG_NAME="${2:-MH_01_easy.bag}"
MODE="${3:-mono}"             # mono или vio
DATASET="${BAG_NAME%.bag}"
BAG_PATH="/home/mononoki/Datasets/${BAG_NAME}"
BAG_DURATION=$(python3 ~/EKF_VIO/get_bag_duration.py "$BAG_PATH")

if [ "$MODE" = "vio" ]; then
    LAUNCH_FILE="/root/main_bag_vio.launch"
    OUT_DIR="$HOME/EKF_VIO/cpu_results/${DATASET}_vio"
else
    LAUNCH_FILE="/root/main_bag.launch"
    OUT_DIR="$HOME/EKF_VIO/cpu_results/${DATASET}"
fi
mkdir -p "$OUT_DIR"

echo "Датасет : ${DATASET}"
echo "Режим   : ${MODE}"
echo "Длина   : ${BAG_DURATION}с"
echo "Результаты: ${OUT_DIR}"

echo "[1/4] Запускаем SVO + bag..."
docker exec "$CONTAINER" bash -c \
  "source /opt/ros/noetic/setup.bash && \
   source /root/ros_ws/devel/setup.bash --extend && \
   source /root/svo_ws/devel/setup.bash --extend && \
   timeout ${BAG_DURATION} roslaunch ${LAUNCH_FILE} bag_name:=${BAG_NAME} > /tmp/svo.log 2>&1" &
LAUNCH_PID=$!

echo "[2/4] Мониторинг CPU svo_node..."
python3 ~/EKF_VIO/cpu_monitor.py "$OUT_DIR/cpu_samples.txt"

wait $LAUNCH_PID 2>/dev/null

echo "[3/4] Копируем лог SVO..."
docker cp "$CONTAINER":/tmp/svo.log "$OUT_DIR/svo.log"

echo "[4/4] График и статистика..."
python3 ~/EKF_VIO/cpu_plot.py "$OUT_DIR"

echo "Готово. Результаты: ${OUT_DIR}"
