#!/bin/bash

# Test script for segmented recording
echo "Testing segmented camera recording..."
echo "This will run the mock camera publisher and recorder with 10-second segments"
echo ""

# Source ROS2 environment
if [ -f "/opt/ros/humble/setup.bash" ]; then
    source /opt/ros/humble/setup.bash
    echo "✓ Sourced ROS2 Humble environment"
else
    echo "❌ ROS2 environment not found!"
    exit 1
fi

echo ""
echo "Starting mock camera publisher in background..."
python3 test_recorder.py &
PUBLISHER_PID=$!

echo "Waiting 3 seconds for publisher to start..."
sleep 3

echo ""
echo "Starting segmented recording (10-second segments)..."
echo "This will record for about 30 seconds, creating 3 segments"
echo "Press Ctrl+C to stop early"
echo ""

# Run recorder with test segmentation
timeout 35s python3 camera_recorder.py --segment-preset test --output test_segments 2>/dev/null || true

echo ""
echo "Stopping mock camera publisher..."
kill $PUBLISHER_PID 2>/dev/null || true
wait $PUBLISHER_PID 2>/dev/null || true

echo ""
echo "Recording complete! Check the generated segment files:"
ls -la test_segments_seg*.mp4 2>/dev/null || echo "No segment files found"

echo ""
echo "Test completed!"
