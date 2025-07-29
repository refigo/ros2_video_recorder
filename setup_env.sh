#!/bin/bash

# Setup script for ROS2 Camera Recorder
echo "Setting up ROS2 Camera Recorder environment..."

# Source ROS2 environment
if [ -f "/opt/ros/humble/setup.bash" ]; then
    source /opt/ros/humble/setup.bash
    echo "✓ Sourced ROS2 Humble environment"
elif [ -f "/opt/ros/iron/setup.bash" ]; then
    source /opt/ros/iron/setup.bash
    echo "✓ Sourced ROS2 Iron environment"
elif [ -f "/opt/ros/jazzy/setup.bash" ]; then
    source /opt/ros/jazzy/setup.bash
    echo "✓ Sourced ROS2 Jazzy environment"
else
    echo "❌ ROS2 environment not found!"
    echo "Please install ROS2 first: https://docs.ros.org/en/humble/Installation.html"
    exit 1
fi

# Check if required packages are available
echo "Checking required packages..."

python3 -c "import rclpy" 2>/dev/null && echo "✓ rclpy available" || echo "❌ rclpy not found"
python3 -c "from sensor_msgs.msg import Image" 2>/dev/null && echo "✓ sensor_msgs available" || echo "❌ sensor_msgs not found"
python3 -c "from cv_bridge import CvBridge" 2>/dev/null && echo "✓ cv_bridge available" || echo "❌ cv_bridge not found"
python3 -c "import cv2" 2>/dev/null && echo "✓ OpenCV available" || echo "❌ OpenCV not found"
python3 -c "import numpy" 2>/dev/null && echo "✓ NumPy available" || echo "❌ NumPy not found"

# Check FFmpeg (optional)
if command -v ffmpeg &> /dev/null; then
    echo "✓ FFmpeg available (optional)"
else
    echo "⚠ FFmpeg not found (optional - install with: sudo apt install ffmpeg)"
fi

# Make scripts executable
chmod +x record_camera.sh
echo "✓ Made scripts executable"

echo ""
echo "Setup complete! You can now use:"
echo "  ./record_camera.sh                    # Record with default settings"
echo "  python3 camera_recorder.py --help    # See all options"
echo "  python3 test_recorder.py             # Start mock camera for testing"
echo ""
echo "Note: You need to source ROS2 environment in each new terminal:"
echo "  source /opt/ros/humble/setup.bash"
