#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2
import numpy as np
import argparse
import os
import subprocess
import threading
import queue
from datetime import datetime, timezone, timedelta


KST = timezone(timedelta(hours=9))


class CameraRecorder(Node):
    def __init__(self, topic_name='/camera/color/image_raw', output_file=None,
                 fps=30, use_ffmpeg=False, codec='mp4v', segment_duration=None,
                 branch_id=None, video_label='topview_video',
                 crf=23, maxrate=None):
        super().__init__('camera_recorder')

        self.topic_name = topic_name
        self.fps = fps
        self.use_ffmpeg = use_ffmpeg
        self.codec = codec
        self.bridge = CvBridge()
        self.segment_duration = segment_duration  # Duration in seconds for each video segment
        self.timezone = KST
        self.timezone_label = 'KST'
        self.branch_id = branch_id
        self.video_label = video_label
        self.crf = str(crf)
        self.maxrate = maxrate

        # Output directory
        self.output_dir = output_file if output_file else 'videos'
        os.makedirs(self.output_dir, exist_ok=True)

        # Generate initial filename
        now = datetime.now(self.timezone)
        self.output_file, self.srt_path = self._generate_paths(now)
            
        # Video writer objects
        self.video_writer = None
        self.ffmpeg_process = None
        self.ffmpeg_thread = None
        self.frame_queue = queue.Queue()
        self.recording = False
        self.frame_count = 0
        self.writer_lock = threading.Lock()
        
        # Frame duplication for irregular frame rate correction
        self.last_frame_time = None
        self.last_frame = None

        # Segmentation variables
        self.segment_number = 1
        self.segment_start_time = None
        self.total_segments = 0
        self.segment_timer = None
        
        # SRT real-time writing state
        self.srt_file = None
        self.srt_index = 0
        self.srt_previous_second = None
        self.srt_entry_start_delta = None
        self.srt_entry_text = None

        # Image dimensions (will be set when first frame arrives)
        self.width = None
        self.height = None
        
        # Create subscriber with BEST_EFFORT QoS to match typical camera publishers
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=10
        )
        self.subscription = self.create_subscription(
            Image,
            self.topic_name,
            self.image_callback,
            sensor_qos
        )
        
        self.get_logger().info(f"Camera recorder initialized")
        self.get_logger().info(f"Topic: {self.topic_name}")
        self.get_logger().info(f"Output: {self.output_file}")
        self.get_logger().info(f"FPS: {self.fps}")
        self.get_logger().info(f"Using FFmpeg: {self.use_ffmpeg}")
        
    @staticmethod
    def _recording_path(final_path):
        """Prepend '.recording_' to the basename of a path."""
        directory = os.path.dirname(final_path)
        return os.path.join(directory, f".recording_{os.path.basename(final_path)}")

    def _generate_paths(self, timestamp):
        """Generate MP4 and SRT file paths from a timestamp.

        Returns (mp4_path, srt_path) using the naming convention:
        {BRANCH_ID}_{YYYYMMDD}T{HHMMSS}+0900_{video_label}.{ext}
        """
        name = f"{self.branch_id}_{timestamp.strftime('%Y%m%dT%H%M%S')}+0900_{self.video_label}"
        mp4_path = os.path.join(self.output_dir, f"{name}.mp4")
        srt_path = os.path.join(self.output_dir, f"{name}.srt")
        return mp4_path, srt_path

    def _write_frame(self, frame):
        """Write a single frame to the video output. Caller must hold writer_lock."""
        if self.use_ffmpeg:
            if self.ffmpeg_process and self.ffmpeg_process.stdin:
                try:
                    self.ffmpeg_process.stdin.write(frame.tobytes())
                except (OSError, BrokenPipeError):
                    pass
        else:
            if self.video_writer:
                self.video_writer.write(frame)

    def _convert_to_bgr(self, msg):
        """Convert ROS Image message to BGR8 OpenCV image.

        Handles both colour (e.g. rgb8, bgr8, bayer) and depth (16UC1, 32FC1)
        encodings.  Depth images are normalised to 0-255 grayscale and then
        converted to 3-channel BGR so the downstream video writer always
        receives a consistent format.
        """
        encoding = msg.encoding

        if encoding in ('16UC1', '32FC1'):
            # Depth image — passthrough to preserve raw values
            depth = self.bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')
            if encoding == '32FC1':
                # metres → millimetres, then clip to uint16 range
                depth = np.clip(depth * 1000.0, 0, 65535).astype(np.uint16)
            # Normalise to 0-255
            valid = depth[depth > 0]
            max_val = float(np.percentile(valid, 99)) if valid.size > 0 else 1.0
            normalised = np.clip(depth.astype(np.float32) / max_val * 255.0, 0, 255).astype(np.uint8)
            return cv2.cvtColor(normalised, cv2.COLOR_GRAY2BGR)

        # Colour image — standard conversion
        return self.bridge.imgmsg_to_cv2(msg, 'bgr8')

    def image_callback(self, msg):
        try:
            # Convert ROS Image message to OpenCV format
            cv_image = self._convert_to_bgr(msg)

            # Initialize video writer on first frame
            if not self.recording:
                self.initialize_recording(cv_image)

            # Record frame
            if self.recording:
                should_log = False
                now = datetime.now(self.timezone)

                with self.writer_lock:
                    if self.last_frame_time is None:
                        # First frame: just write once and initialize
                        self._write_frame(cv_image)
                        self.frame_count += 1
                    else:
                        elapsed = (now - self.last_frame_time).total_seconds()
                        expected_frames = max(1, round(elapsed * self.fps))
                        duplicate_count = expected_frames - 1

                        # Write duplicates of the previous frame to fill the gap
                        for i in range(duplicate_count):
                            self._write_frame(self.last_frame)
                            self.frame_count += 1

                        # Write the current frame
                        self._write_frame(cv_image)
                        self.frame_count += 1

                    self.last_frame_time = now
                    self.last_frame = cv_image
                    self._update_srt(now)

                    if self.frame_count % 30 == 0:
                        should_log = True

                if should_log:
                    self.get_logger().info(f"Recorded {self.frame_count} frames")

        except Exception as e:
            self.get_logger().error(f"Error processing frame: {str(e)}")
            
    def initialize_recording(self, first_frame):
        """Initialize video recording with the first frame"""
        self.height, self.width = first_frame.shape[:2]

        # Set recording flag before starting ffmpeg writer thread
        # so the thread doesn't exit immediately on its loop condition
        self.recording = True

        if self.use_ffmpeg:
            self.initialize_ffmpeg()
        else:
            self.initialize_opencv()
        self.segment_start_time = datetime.now(self.timezone)
        self._open_srt_file()

        # Always start segment timer (wall-clock hourly by default)
        self.start_segment_timer()

        self.get_logger().info(f"Recording started - Resolution: {self.width}x{self.height}")
        if self.segment_duration:
            self.get_logger().info(f"Segmentation: {self.segment_duration}s per segment (fixed duration)")
        else:
            self.get_logger().info(f"Segmentation: wall-clock aligned (split at every :00)")
        
    def initialize_opencv(self):
        """Initialize OpenCV video writer"""
        # Define codec
        if self.codec == 'mp4v':
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        elif self.codec == 'xvid':
            fourcc = cv2.VideoWriter_fourcc(*'XVID')
        elif self.codec == 'h264':
            fourcc = cv2.VideoWriter_fourcc(*'H264')
        else:
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            
        self.video_writer = cv2.VideoWriter(
            self._recording_path(self.output_file),
            fourcc,
            self.fps,
            (self.width, self.height)
        )
        
        if not self.video_writer.isOpened():
            raise RuntimeError("Failed to open video writer")
            
    @staticmethod
    def _double_rate(rate_str: str) -> str:
        """Double an ffmpeg rate string (e.g. '2M' → '4M', '1500k' → '3000k')."""
        import re
        m = re.match(r'^(\d+(?:\.\d+)?)([kKmMgG]?)$', rate_str)
        if not m:
            return rate_str
        return f"{float(m.group(1)) * 2:g}{m.group(2)}"

    def initialize_ffmpeg(self):
        """Initialize FFmpeg process for video encoding"""
        ffmpeg_cmd = [
            'ffmpeg',
            '-y',  # Overwrite output file
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-s', f'{self.width}x{self.height}',
            '-pix_fmt', 'bgr24',
            '-r', str(self.fps),
            '-i', '-',  # Input from stdin
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', self.crf,
            '-pix_fmt', 'yuv420p',
        ]
        if self.maxrate:
            ffmpeg_cmd += ['-maxrate', self.maxrate, '-bufsize', self._double_rate(self.maxrate)]
        ffmpeg_cmd += [
            self._recording_path(self.output_file)
        ]
        
        try:
            self.ffmpeg_process = subprocess.Popen(
                ffmpeg_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
        except Exception as e:
            raise RuntimeError(f"Failed to start FFmpeg: {str(e)}")
            
    def ffmpeg_writer_thread(self):
        """Thread function to write frames to FFmpeg process"""
        while self.recording or not self.frame_queue.empty():
            try:
                frame = self.frame_queue.get(timeout=1.0)
                if self.ffmpeg_process and self.ffmpeg_process.stdin:
                    self.ffmpeg_process.stdin.write(frame.tobytes())
                    self.ffmpeg_process.stdin.flush()
            except queue.Empty:
                continue
            except Exception as e:
                self.get_logger().error(f"Error writing frame to FFmpeg: {str(e)}")
                break

    def _release_current_writer_locked(self):
        """Release current writer resources. Caller must hold writer_lock."""
        if self.use_ffmpeg:
            if self.ffmpeg_process:
                try:
                    self.ffmpeg_process.stdin.close()
                except OSError:
                    pass
                try:
                    self.ffmpeg_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.ffmpeg_process.kill()
                    self.ffmpeg_process.wait()
                self.ffmpeg_process = None
        else:
            if self.video_writer:
                self.video_writer.release()
                self.video_writer = None

    def _rename_recording_to_final(self, final_mp4_path):
        """Rename .recording_ prefixed files to their final names."""
        recording_mp4 = self._recording_path(final_mp4_path)
        if os.path.exists(recording_mp4):
            os.rename(recording_mp4, final_mp4_path)

    def _format_srt_timestamp(self, delta):
        total_ms = int(delta.total_seconds() * 1000)
        if total_ms < 0:
            total_ms = 0
        hours, remainder = divmod(total_ms, 3600000)
        minutes, remainder = divmod(remainder, 60000)
        seconds, millis = divmod(remainder, 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"

    def _open_srt_file(self):
        """Open SRT file for real-time append writing."""
        srt_recording_path = self._recording_path(self.srt_path)
        self.srt_file = open(srt_recording_path, 'w')
        self.srt_index = 0
        self.srt_previous_second = None
        self.srt_entry_start_delta = None
        self.srt_entry_text = None

    def _close_srt_file(self):
        """Flush the last SRT entry and close the file."""
        if self.srt_file is None:
            return
        # Write the final pending entry
        if self.srt_entry_start_delta is not None and self.srt_entry_text is not None:
            end_second = (self.srt_previous_second or 0) + 1
            end_delta = timedelta(seconds=end_second)
            self._flush_srt_entry(end_delta)
        self.srt_file.close()
        self.srt_file = None
        # Rename .recording_ SRT to final path
        recording_srt = self._recording_path(self.srt_path)
        if os.path.exists(recording_srt):
            os.rename(recording_srt, self.srt_path)

    def _flush_srt_entry(self, end_delta):
        """Write a completed SRT entry to the file."""
        if self.srt_file is None or self.srt_entry_start_delta is None:
            return
        self.srt_index += 1
        start_str = self._format_srt_timestamp(self.srt_entry_start_delta)
        end_str = self._format_srt_timestamp(end_delta)
        self.srt_file.write(f"{self.srt_index}\n{start_str} --> {end_str}\n")
        self.srt_file.write(f"{self.srt_entry_text}\n\n")
        self.srt_file.flush()

    def _update_srt(self, now):
        """Called per-frame to update SRT with real-time wall-clock timestamps.

        Writes one SRT entry per wall-clock second boundary.
        """
        if self.srt_file is None or self.segment_start_time is None:
            return
        actual_delta = now - self.segment_start_time
        if actual_delta < timedelta(0):
            actual_delta = timedelta(0)
        elapsed_seconds = int(actual_delta.total_seconds())
        quantized_delta = timedelta(seconds=elapsed_seconds)
        text = f"{now.strftime('%Y-%m-%dT%H:%M:%S')}+0900 {self.timezone_label}"

        if self.srt_previous_second is None:
            # First frame
            self.srt_entry_start_delta = quantized_delta
            self.srt_entry_text = text
            self.srt_previous_second = elapsed_seconds
        elif elapsed_seconds != self.srt_previous_second:
            # Crossed a second boundary — flush the previous entry
            self._flush_srt_entry(quantized_delta)
            self.srt_entry_start_delta = quantized_delta
            self.srt_entry_text = text
            self.srt_previous_second = elapsed_seconds
        else:
            # Same second — update text (last frame in this second wins)
            self.srt_entry_text = text

    def _seconds_until_next_boundary(self):
        """Calculate seconds until the next segment boundary.

        If segment_duration is set, use fixed duration.
        Otherwise, use wall-clock hourly alignment (next :00).
        """
        if self.segment_duration:
            return self.segment_duration
        now = datetime.now(self.timezone)
        return 3600 - (now.minute * 60 + now.second)

    def start_segment_timer(self):
        """Start timer for segment switching"""
        if self.segment_timer:
            self.segment_timer.cancel()

        delay = self._seconds_until_next_boundary()
        self.segment_timer = threading.Timer(delay, self.switch_segment)
        self.segment_timer.daemon = True
        self.segment_timer.start()
        self.get_logger().info(f"Next segment switch in {delay}s")
    
    def switch_segment(self):
        """Switch to next video segment"""
        if not self.recording:
            return
            
        next_segment = self.segment_number + 1
        self.get_logger().info(f"Switching to segment {next_segment}...")

        with self.writer_lock:
            completed_file = self.output_file
            segment_duration = datetime.now(self.timezone) - self.segment_start_time

            # Close current segment
            self._close_srt_file()
            self._release_current_writer_locked()

            # Prepare next segment
            self.segment_number += 1
            self.total_segments += 1

            now = datetime.now(self.timezone)
            self.output_file, self.srt_path = self._generate_paths(now)

            # Reinitialize recording for new segment
            if self.use_ffmpeg:
                self.initialize_ffmpeg()
            else:
                self.initialize_opencv()

            self.segment_start_time = now
            self.frame_count = 0
            self.last_frame_time = None
            self.last_frame = None
            self._open_srt_file()
            new_segment_file = self.output_file

        self._rename_recording_to_final(completed_file)

        # Start timer for next segment
        self.start_segment_timer()

        self.get_logger().info(
            f"Segment completed: {completed_file} ({segment_duration.total_seconds():.1f}s)"
        )
        self.get_logger().info(f"Started recording: {new_segment_file}")
    
    def stop_recording(self):
        """Stop recording and cleanup resources"""
        if not self.recording:
            return
            
        self.recording = False
        
        # Cancel segment timer if running
        if self.segment_timer:
            self.segment_timer.cancel()
            self.segment_timer = None
        
        self.get_logger().info(f"Stopping recording... Total frames in current segment: {self.frame_count}")
        
        with self.writer_lock:
            final_video = self.output_file
            self._close_srt_file()
            self._release_current_writer_locked()

        self._rename_recording_to_final(final_video)

        # Print recording summary
        total_segments = self.segment_number
        self.get_logger().info(f"Recording completed - {total_segments} segment(s) saved to {self.output_dir}/")
        
    def __del__(self):
        self.stop_recording()


def main():
    parser = argparse.ArgumentParser(description='Record ROS2 camera topic to video')
    parser.add_argument('--topic', '-t', default='/camera/color/image_raw',
                       help='Camera topic name (default: /camera/color/image_raw)')
    parser.add_argument('--output-dir', '-o', default=None,
                       help='Output directory (default: videos/)')
    parser.add_argument('--fps', '-f', type=int, default=30,
                       help='Output video FPS (default: 30)')
    parser.add_argument('--ffmpeg', action='store_true',
                       help='Use FFmpeg instead of OpenCV for encoding')
    parser.add_argument('--codec', '-c', default='mp4v',
                       choices=['mp4v', 'xvid', 'h264'],
                       help='Video codec (default: mp4v, only for OpenCV)')
    parser.add_argument('--segment', '-s', type=int, default=None,
                       help='Segment duration in seconds (e.g., 10 for testing, 600 for 10min, 3600 for 1hr)')
    parser.add_argument('--branch-id', required=True,
                       help='Branch identifier (e.g., BB003)')
    parser.add_argument('--video-label', default='topview_video',
                       help='Video label for filename (default: topview_video)')
    parser.add_argument('--crf', type=int, default=23,
                       help='CRF value for libx264 (default: 23, recommend 28-30 for ops)')
    parser.add_argument('--maxrate', default=None,
                       help='Max bitrate cap for libx264 VBR (e.g., 2M). Suppresses night-time bitrate spikes')

    args = parser.parse_args()

    # Process segment duration
    segment_duration = args.segment if args.segment else None
    
    # Initialize ROS2
    rclpy.init()
    
    try:
        # Create recorder node
        recorder = CameraRecorder(
            topic_name=args.topic,
            output_file=args.output_dir,
            fps=args.fps,
            use_ffmpeg=args.ffmpeg,
            codec=args.codec,
            segment_duration=segment_duration,
            branch_id=args.branch_id,
            video_label=args.video_label,
            crf=args.crf,
            maxrate=args.maxrate,
        )
        
        print(f"Starting camera recorder...")
        print(f"Topic: {args.topic}")
        print(f"Branch ID: {args.branch_id}")
        print(f"Video label: {args.video_label}")
        if args.ffmpeg:
            crf_info = f"CRF: {args.crf}"
            if args.maxrate:
                crf_info += f", maxrate: {args.maxrate}"
            print(crf_info)
        if segment_duration:
            print(f"Segmentation: {segment_duration}s per segment")
        print(f"Press Ctrl+C to stop recording")
        
        # Spin the node
        rclpy.spin(recorder)
        
    except KeyboardInterrupt:
        print("\nStopping recording...")
        
    finally:
        if 'recorder' in locals():
            recorder.stop_recording()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
