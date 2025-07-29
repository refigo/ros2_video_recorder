# ROS2 Camera Topic Recorder

A Python utility to record ROS2 camera topics to video files using either OpenCV or FFmpeg.

## Features

- Record ROS2 Image topics to MP4 video files
- Support for both OpenCV and FFmpeg backends
- Configurable FPS and video codecs
- Automatic timestamp-based file naming
- Real-time frame counting and logging

## Requirements

- ROS2 (Humble/Iron/Jazzy)
- Python 3.8+
- OpenCV
- FFmpeg (optional, for FFmpeg backend)

## Installation

### Prerequisites
- ROS2 (Humble/Iron/Jazzy) must be installed
- The following ROS2 packages should be available:
  - `ros-humble-rclpy`
  - `ros-humble-sensor-msgs` 
  - `ros-humble-cv-bridge`

### Setup

1. **Source ROS2 environment** (required for each terminal session):
```bash
source /opt/ros/humble/setup.bash
```

2. **Install additional Python dependencies** (if needed):
```bash
pip install numpy
```

3. **For FFmpeg support** (optional, for better video compression):
```bash
sudo apt update
sudo apt install ffmpeg
```

4. **Make scripts executable**:
```bash
chmod +x record_camera.sh
```

## Usage

### Basic Usage

Record the default camera topic:
```bash
python3 camera_recorder.py
```

### Advanced Usage

```bash
# Specify custom topic and output file
python3 camera_recorder.py --topic /my_camera/image_raw --output my_video.mp4

# Use FFmpeg backend for better compression
python3 camera_recorder.py --ffmpeg --fps 60

# Specify video codec (OpenCV only)
python3 camera_recorder.py --codec h264

# Use the shell script
./record_camera.sh /camera/color/image_raw my_recording.mp4
```

### Command Line Arguments

- `--topic, -t`: Camera topic name (default: `/camera/color/image_raw`)
- `--output, -o`: Output video file (default: auto-generated with timestamp)
- `--fps, -f`: Output video FPS (default: 30)
- `--ffmpeg`: Use FFmpeg instead of OpenCV for encoding
- `--codec, -c`: Video codec - mp4v, xvid, h264 (OpenCV only, default: mp4v)

## Backends

### OpenCV Backend (Default)
- Faster startup time
- Good for real-time recording
- Limited codec options
- May have compatibility issues with some players

### FFmpeg Backend
- Better compression and quality
- More codec options
- Wider compatibility
- Slightly higher CPU usage
- Requires FFmpeg installation

## Example Output

```
Camera recorder initialized
Topic: /camera/color/image_raw
Output: camera_recording_20240729_143852.mp4
FPS: 30
Using FFmpeg: False
Recording started - Resolution: 640x480
Recorded 30 frames
Recorded 60 frames
...
^C
Stopping recording... Total frames: 1247
Recording saved to: /home/user/camera_recording_20240729_143852.mp4
```

## Troubleshooting

1. **No frames received**: Check if the camera topic is publishing
   ```bash
   ros2 topic list
   ros2 topic echo /camera/color/image_raw --once
   ```

2. **Video writer failed**: Try different codec or use FFmpeg backend

3. **Permission denied**: Make the script executable
   ```bash
   chmod +x record_camera.sh
   ```

4. **FFmpeg not found**: Install FFmpeg or use OpenCV backend

## Notes

- The recorder automatically detects image dimensions from the first frame
- Recording stops gracefully with Ctrl+C
- Output files are saved in the current directory unless full path is specified
- Frame rate in output video may differ from topic publishing rate
