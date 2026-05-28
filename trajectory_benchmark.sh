#!/bin/bash

CONTAINER="${1:?Не указан контейнер}"
BAG_NAME="${2:-MH_01_easy.bag}"
MODE="${3:-mono}"                           # mono | vio | msf
DATASET="${BAG_NAME%.bag}"

if [ "$MODE" = "vio" ]; then
    LAUNCH_FILE="/root/main_bag_vio.launch"
    DATASET_KEY="${DATASET}_vio"
    SVO_TOPIC="/svo/pose_cam/0"
    SVO_TYPE="pose"
elif [ "$MODE" = "msf" ]; then
    LAUNCH_FILE="/root/main_bag_msf.launch"
    DATASET_KEY="${DATASET}_msf"
    SVO_TOPIC="/msf_core/odometry"
    SVO_TYPE="odom"
else
    LAUNCH_FILE="/root/main_bag.launch"
    DATASET_KEY="${DATASET}"
    SVO_TOPIC="/svo/pose_cam/0"
    SVO_TYPE="pose"
fi

BAG_PATH="/home/mononoki/Datasets/${BAG_NAME}"
BAG_DURATION=$(python3 ~/EKF_VIO/get_bag_duration.py "$BAG_PATH")
OUT_DIR="$HOME/EKF_VIO/trajectory_results/${DATASET_KEY}"
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

if [ "$MODE" = "msf" ]; then
    echo "[2/4] Ждём инициализации SVO (10с)..."
    sleep 10
    echo "[2/4] Инициализируем MSF фильтр..."
    docker exec "$CONTAINER" bash -c \
      "source /opt/ros/noetic/setup.bash && \
       source /root/ros_ws/devel/setup.bash --extend && \
       rosservice call /msf_pose_sensor/pose_sensor/initialize_msf_scale \"scale: 1.0\"" 2>&1
else
    sleep 2
fi

echo "[3/4] Запускаем запись траектории..."
docker exec "$CONTAINER" bash -c \
  "source /opt/ros/noetic/setup.bash && \
   source /root/ros_ws/devel/setup.bash --extend && \
   source /root/svo_ws/devel/setup.bash --extend && \
   python3 /root/record.py \
     --bag_name ${DATASET_KEY} \
     --svo_topic ${SVO_TOPIC} \
     --svo_type ${SVO_TYPE} \
     --out_dir /results/${DATASET_KEY} > /tmp/record.log 2>&1 & \
   echo \$! > /tmp/record.pid"

wait $LAUNCH_PID

echo "[4/4] Завершаем запись..."
docker exec "$CONTAINER" bash -c 'kill $(cat /tmp/record.pid)'
sleep 2

docker cp "$CONTAINER":/tmp/svo.log "$OUT_DIR/svo.log"

python3 ~/EKF_VIO/evaluate_trajectory.py \
  --bag_name "${DATASET_KEY}" \
  --out_dir "${OUT_DIR}"

echo "Готово. Результаты: ${OUT_DIR}"
