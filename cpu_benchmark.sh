#!/bin/bash
# Использование: ./start_benchmark.sh <container> [bag_name]
CONTAINER="${1:-svo_perm}"
BAG_NAME="${2:-MH_01_easy.bag}"

cleanup() {
    echo "Остановка..."
    docker exec $CONTAINER pkill -f "roslaunch.*main_bag" 2>/dev/null
    kill $CPU_PID 2>/dev/null
    exit 0
}
trap cleanup SIGINT SIGTERM

echo "=== Запуск roslaunch в контейнере $CONTAINER ==="
docker exec $CONTAINER bash -c \
  "source /opt/ros/noetic/setup.bash && source ~/svo_ws/devel/setup.bash && exec roslaunch /root/main_bag.launch bag_name:=$BAG_NAME" &
LAUNCH_PID=$!

echo "Ожидание svo_node..."
until docker exec $CONTAINER pgrep -f svo_node > /dev/null 2>&1; do
    sleep 1
done
echo "svo_node обнаружен. Запуск мониторинга CPU."

CPU_LOG="/home/mononoki/results/cpu_${BAG_NAME%.*}.log"
docker exec $CONTAINER bash -c \
  "source /opt/ros/noetic/setup.bash && source ~/svo_ws/devel/setup.bash && top -b -d 1 -p \$(pgrep -f svo_node | head -1) | grep --line-buffered svo_node" > "$CPU_LOG" &
CPU_PID=$!

echo "Мониторинг CPU запущен (PID=$CPU_PID). Ожидание завершения bag..."

wait $LAUNCH_PID

kill $CPU_PID 2>/dev/null
wait $CPU_PID 2>/dev/null

if [ -f "$CPU_LOG" ]; then
    AVG=$(awk '{sum+=$9; count++} END {if(count>0) printf "%.2f", sum/count}' "$CPU_LOG")
    echo "Средняя загрузка CPU: $AVG%"
else
    echo "Лог CPU не найден."
fi

echo "Готово. Результаты: $CPU_LOG"
