#!/bin/bash

# Simple script to record camera topic
# Usage: ./record_camera.sh [topic_name] [output_file]

# Source ROS2 environment
if [ -f "/opt/ros/humble/setup.bash" ]; then
    source /opt/ros/humble/setup.bash
    echo "Sourced ROS2 Humble environment"
elif [ -f "/opt/ros/iron/setup.bash" ]; then
    source /opt/ros/iron/setup.bash
    echo "Sourced ROS2 Iron environment"
elif [ -f "/opt/ros/jazzy/setup.bash" ]; then
    source /opt/ros/jazzy/setup.bash
    echo "Sourced ROS2 Jazzy environment"
else
    echo "Warning: ROS2 environment not found. Please source your ROS2 setup manually."
fi

TOPIC=${1:-"/camera/color/image_raw"}
OUTPUT=${2:-""}

if [ ! -z "$OUTPUT" ]; then
    python3 camera_recorder.py --topic "$TOPIC" --output "$OUTPUT"
else
    python3 camera_recorder.py --topic "$TOPIC"
fi
