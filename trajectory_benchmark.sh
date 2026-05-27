#!/bin/bash

CONTAINER="${1:?Не указан контейнер}"
BAG_NAME="${2:-MH_01_easy.bag}"
BAG_PATH="/home/mononoki/Datasets/${BAG_NAME}"
BAG_DURATION=$(python3 ~/EKF_VIO/get_bag_duration.py "$BAG_PATH")
DATASET="${BAG_NAME%.bag}"                                      # MH_01_easy.bag → MH_01_easy
OUT_DIR="$HOME/EKF_VIO/trajectory_results/${DATASET}"
mkdir -p "$OUT_DIR"

echo "Датасет: ${DATASET}"
echo "Длина bag: ${BAG_DURATION}с"

echo "[1/3] Запускаем SVO + bag..."
docker exec "$CONTAINER" bash -c \
  "source /opt/ros/noetic/setup.bash && \
   source /root/ros_ws/devel/setup.bash --extend && \
   source /root/svo_ws/devel/setup.bash --extend && \
   timeout ${BAG_DURATION} roslaunch /root/main_bag.launch bag_name:=${BAG_NAME}" &
LAUNCH_PID=$!

sleep 2

echo "[2/3] Запускаем запись траектории..."
docker exec "$CONTAINER" bash -c \
  "source /opt/ros/noetic/setup.bash && \
   source /root/svo_ws/devel/setup.bash --extend && \
   python3 /root/record.py --bag_name ${DATASET} --out_dir /results/${DATASET} > /tmp/record.log 2>&1 & \
   echo \$! > /tmp/record.pid"

wait $LAUNCH_PID

echo "[3/3] Завершаем запись..."
docker exec "$CONTAINER" bash -c 'kill $(cat /tmp/record.pid)'
sleep 2

python3 ~/EKF_VIO/evaluate_trajectory.py --bag_name "${DATASET}" --out_dir "${OUT_DIR}"
echo "Готово. Результаты: ${OUT_DIR}"
