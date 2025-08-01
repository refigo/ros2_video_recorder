# ROS2 Camera Topic Recorder

A Python utility to record ROS2 camera topics to video files using either OpenCV or FFmpeg.

## Features

- Record ROS2 Image topics to MP4 video files
- Support for both OpenCV and FFmpeg backends
- Configurable FPS and video codecs
- Automatic timestamp-based file naming
- **Segmented recording** - automatically split videos into timed segments
- Real-time frame counting and logging
- Preset durations for testing (10s), 10 minutes, or 1 hour segments

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

# Segmented recording examples
python3 camera_recorder.py --segment-preset test    # 10-second segments for testing
python3 camera_recorder.py --segment-preset 10min   # 10-minute segments
python3 camera_recorder.py --segment-preset 1hour   # 1-hour segments
python3 camera_recorder.py --segment 30             # Custom 30-second segments

# Use the shell script
./record_camera.sh /camera/color/image_raw my_recording.mp4
```

### Command Line Arguments

- `--topic, -t`: Camera topic name (default: `/camera/color/image_raw`)
- `--output, -o`: Output video file (default: auto-generated with timestamp)
- `--fps, -f`: Output video FPS (default: 30)
- `--ffmpeg`: Use FFmpeg instead of OpenCV for encoding
- `--codec, -c`: Video codec - mp4v, xvid, h264 (OpenCV only, default: mp4v)
- `--segment, -s`: Segment duration in seconds (e.g., 10, 600, 3600)
- `--segment-preset`: Preset durations - test (10s), 10min (600s), 1hour (3600s)

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

## Segmented Recording

The recorder can automatically split recordings into multiple video files based on time duration. This is useful for:

- **Testing**: Short 10-second segments to verify functionality
- **Long recordings**: Manageable file sizes (10-minute or 1-hour segments)
- **Continuous recording**: Prevents single large files that might be corrupted
- **Storage management**: Easier to handle multiple smaller files

### Segment File Naming

Segmented files are automatically named with sequential numbers:
```
camera_recording_20240731_110330_seg001.mp4
camera_recording_20240731_110330_seg002.mp4
camera_recording_20240731_110330_seg003.mp4
...
```

### Segment Switching

- Seamless transition between segments (no frame loss)
- Each segment is properly closed before starting the next
- Timer-based switching ensures consistent segment durations
- Recording can be stopped at any time with Ctrl+C

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
