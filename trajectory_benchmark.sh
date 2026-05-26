#!/bin/bash

CONTAINER="${1:?Не указан контейнер}"
BAG_NAME="${2:-MH_01_easy.bag}"
BAG_DURATION=180
OUT_DIR="$HOME/EKF_VIO/trajectory_results"
mkdir -p "$OUT_DIR"

docker exec "$CONTAINER" bash -c \
  "source /opt/ros/noetic/setup.bash && \
   source /root/ros_ws/devel/setup.bash --extend && \
   source /root/svo_ws/devel/setup.bash --extend && \
   timeout ${BAG_DURATION} roslaunch /root/main_bag.launch bag_name:=${BAG_NAME}" &
LAUNCH_PID=$!

sleep 2

echo "[2/3] Запускаем запись траектории..."
docker exec "$CONTAINER" bash -c \
  'source /opt/ros/noetic/setup.bash && \
   source /root/svo_ws/devel/setup.bash --extend && \
   python3 /root/record.py & \
   echo $! > /tmp/record.pid'

wait $LAUNCH_PID


docker exec "$CONTAINER" bash -c 'kill $(cat /tmp/record.pid)'
sleep 2

python3 evaluate_trajectory.py --no_scale

echo "Готово"
