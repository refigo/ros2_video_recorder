#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2
import numpy as np
import argparse
import os
import subprocess
import threading
import queue
import csv
from datetime import datetime, timezone, timedelta


KST = timezone(timedelta(hours=9))


class CameraRecorder(Node):
    def __init__(self, topic_name='/camera/color/image_raw', output_file=None, 
                 fps=30, use_ffmpeg=False, codec='mp4v', segment_duration=None):
        super().__init__('camera_recorder')
        
        self.topic_name = topic_name
        self.fps = fps
        self.use_ffmpeg = use_ffmpeg
        self.codec = codec
        self.bridge = CvBridge()
        self.segment_duration = segment_duration  # Duration in seconds for each video segment
        self.timezone = KST
        self.timezone_label = 'KST'
        self.session_dir = None
        
        # Base filename for segmented recording
        if output_file is None:
            timestamp_str = datetime.now(self.timezone).strftime("%Y%m%d_%H%M%S")
            session_name = f"session_{timestamp_str}"
            self.session_dir = os.path.join('videos', session_name)
            os.makedirs(self.session_dir, exist_ok=True)
            base_name = f"camera_recording_{timestamp_str}"
            if self.segment_duration:
                self.base_filename = os.path.join(self.session_dir, base_name)
                self.output_file = f"{self.base_filename}_seg001.mp4"
            else:
                self.base_filename = os.path.join(self.session_dir, base_name)
                self.output_file = f"{self.base_filename}.mp4"
        else:
            if self.segment_duration:
                # Remove extension and add segment info
                base = os.path.splitext(output_file)[0]
                ext = os.path.splitext(output_file)[1] or '.mp4'
                self.base_filename = base
                self.output_file = f"{base}_seg001{ext}"
            else:
                self.output_file = output_file
            output_dir = os.path.dirname(self.output_file)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            
        # Video writer objects
        self.video_writer = None
        self.ffmpeg_process = None
        self.ffmpeg_thread = None
        self.frame_queue = queue.Queue()
        self.recording = False
        self.frame_count = 0
        self.writer_lock = threading.Lock()
        self.frame_records = []
        
        # Segmentation variables
        self.segment_number = 1
        self.segment_start_time = None
        self.total_segments = 0
        self.segment_timer = None
        
        # Image dimensions (will be set when first frame arrives)
        self.width = None
        self.height = None
        
        # Create subscriber
        self.subscription = self.create_subscription(
            Image,
            self.topic_name,
            self.image_callback,
            10
        )
        
        self.get_logger().info(f"Camera recorder initialized")
        self.get_logger().info(f"Topic: {self.topic_name}")
        self.get_logger().info(f"Output: {self.output_file}")
        self.get_logger().info(f"FPS: {self.fps}")
        self.get_logger().info(f"Using FFmpeg: {self.use_ffmpeg}")
        
    def image_callback(self, msg):
        try:
            # Convert ROS Image message to OpenCV format
            cv_image = self.bridge.imgmsg_to_cv2(msg, "bgr8")
            
            # Initialize video writer on first frame
            if not self.recording:
                self.initialize_recording(cv_image)
                
            # Record frame
            if self.recording:
                should_log = False
                with self.writer_lock:
                    if self.use_ffmpeg:
                        self.frame_queue.put(cv_image)
                    else:
                        if self.video_writer:
                            self.video_writer.write(cv_image)
                    
                    self.frame_count += 1
                    wall_time = datetime.now(self.timezone)
                    ros_stamp = None
                    if hasattr(msg, 'header') and hasattr(msg.header, 'stamp'):
                        ros_stamp = (msg.header.stamp.sec, msg.header.stamp.nanosec)
                    self.frame_records.append({
                        'frame_idx': self.frame_count,
                        'wall_time': wall_time,
                        'ros_stamp': ros_stamp
                    })
                    if self.frame_count % 30 == 0:
                        should_log = True
                
                if should_log:
                    self.get_logger().info(f"Recorded {self.frame_count} frames")
                    
        except Exception as e:
            self.get_logger().error(f"Error processing frame: {str(e)}")
            
    def initialize_recording(self, first_frame):
        """Initialize video recording with the first frame"""
        self.height, self.width = first_frame.shape[:2]
        
        if self.use_ffmpeg:
            self.initialize_ffmpeg()
        else:
            self.initialize_opencv()
            
        self.recording = True
        self.segment_start_time = datetime.now(self.timezone)
        
        # Start segment timer if segmentation is enabled
        if self.segment_duration:
            self.start_segment_timer()
        
        self.get_logger().info(f"Recording started - Resolution: {self.width}x{self.height}")
        if self.segment_duration:
            self.get_logger().info(f"Segmentation enabled - {self.segment_duration}s per segment")
        
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
            self.output_file,
            fourcc,
            self.fps,
            (self.width, self.height)
        )
        
        if not self.video_writer.isOpened():
            raise RuntimeError("Failed to open video writer")
            
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
            '-crf', '23',
            self.output_file
        ]
        
        try:
            self.ffmpeg_process = subprocess.Popen(
                ffmpeg_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Start thread to feed frames to FFmpeg (only once)
            if not self.ffmpeg_thread or not self.ffmpeg_thread.is_alive():
                self.ffmpeg_thread = threading.Thread(target=self.ffmpeg_writer_thread)
                self.ffmpeg_thread.daemon = True
                self.ffmpeg_thread.start()
            
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
            while not self.frame_queue.empty():
                pass
            if self.ffmpeg_process:
                self.ffmpeg_process.stdin.close()
                self.ffmpeg_process.wait()
                self.ffmpeg_process = None
        else:
            if self.video_writer:
                self.video_writer.release()
                self.video_writer = None

    def _format_srt_timestamp(self, delta):
        total_ms = int(delta.total_seconds() * 1000)
        if total_ms < 0:
            total_ms = 0
        hours, remainder = divmod(total_ms, 3600000)
        minutes, remainder = divmod(remainder, 60000)
        seconds, millis = divmod(remainder, 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"

    def _write_segment_metadata(self, video_path, frame_records, segment_start_time):
        """Write CSV + SRT files with timestamp metadata for a segment."""
        if not video_path or not frame_records or not segment_start_time:
            return

        base, _ = os.path.splitext(video_path)
        csv_path = f"{base}_timestamps.csv"
        srt_path = f"{base}_timestamps.srt"
        try:
            with open(csv_path, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['frame_idx', 'ros_stamp_sec', 'ros_stamp_nanosec', 'wall_time_iso'])
                for record in frame_records:
                    ros_sec = record['ros_stamp'][0] if record['ros_stamp'] else ''
                    ros_nsec = record['ros_stamp'][1] if record['ros_stamp'] else ''
                    writer.writerow([
                        record['frame_idx'],
                        ros_sec,
                        ros_nsec,
                        record['wall_time'].isoformat()
                    ])
        except Exception as exc:
            self.get_logger().error(f"Failed to write CSV timestamps for {video_path}: {str(exc)}")

        try:
            frame_duration = 1.0 / self.fps if self.fps > 0 else 0.0
            srt_entries = []
            previous_second = None
            entry_start_delta = None
            entry_text = ''
            last_actual_delta = None

            def build_entry_text(record):
                wall_str = record['wall_time'].strftime('%Y-%m-%dT%H:%M:%S')
                return f"{wall_str}+0900 {self.timezone_label}"

            for record in frame_records:
                actual_delta = record['wall_time'] - segment_start_time
                if actual_delta < timedelta(0):
                    actual_delta = timedelta(0)
                elapsed_seconds = int(actual_delta.total_seconds())
                quantized_delta = timedelta(seconds=elapsed_seconds)
                text = build_entry_text(record)
                if entry_start_delta is None:
                    entry_start_delta = quantized_delta
                    entry_text = text
                    previous_second = elapsed_seconds
                elif elapsed_seconds != previous_second:
                    srt_entries.append((entry_start_delta, quantized_delta, entry_text))
                    entry_start_delta = quantized_delta
                    entry_text = text
                    previous_second = elapsed_seconds
                else:
                    entry_text = text
                last_actual_delta = actual_delta

            if entry_start_delta is not None:
                segment_end_delta = (last_actual_delta or timedelta(0))
                min_display = max(frame_duration, 1.0)
                end_delta = segment_end_delta + timedelta(seconds=min_display)
                if end_delta <= entry_start_delta:
                    end_delta = entry_start_delta + timedelta(seconds=min_display)
                srt_entries.append((entry_start_delta, end_delta, entry_text))

            with open(srt_path, 'w') as srt_file:
                for idx, (start_delta, end_delta, text) in enumerate(srt_entries, start=1):
                    start_str = self._format_srt_timestamp(start_delta)
                    end_str = self._format_srt_timestamp(end_delta)
                    srt_file.write(f"{idx}\n{start_str} --> {end_str}\n")
                    srt_file.write(f"{text}\n\n")
            self.get_logger().info(f"Saved timestamp metadata: {csv_path}, {srt_path}")
        except Exception as exc:
            self.get_logger().error(f"Failed to write subtitles for {video_path}: {str(exc)}")
    
    def start_segment_timer(self):
        """Start timer for segment switching"""
        if self.segment_timer:
            self.segment_timer.cancel()
        
        self.segment_timer = threading.Timer(self.segment_duration, self.switch_segment)
        self.segment_timer.daemon = True
        self.segment_timer.start()
    
    def switch_segment(self):
        """Switch to next video segment"""
        if not self.recording:
            return
            
        next_segment = self.segment_number + 1
        self.get_logger().info(f"Switching to segment {next_segment}...")

        with self.writer_lock:
            completed_segment = self.segment_number
            completed_file = self.output_file
            completed_start_time = self.segment_start_time
            completed_records = self.frame_records
            segment_duration = datetime.now(self.timezone) - self.segment_start_time

            # Close current segment
            self._release_current_writer_locked()

            # Prepare next segment
            self.segment_number += 1
            self.total_segments += 1

            if hasattr(self, 'base_filename'):
                ext = os.path.splitext(completed_file)[1]
                self.output_file = f"{self.base_filename}_seg{self.segment_number:03d}{ext}"

            # Reinitialize recording for new segment
            if self.use_ffmpeg:
                self.initialize_ffmpeg()
            else:
                self.initialize_opencv()

            self.segment_start_time = datetime.now(self.timezone)
            self.frame_count = 0  # Reset frame count for new segment
            self.frame_records = []
            new_segment_file = self.output_file

        self._write_segment_metadata(completed_file, completed_records, completed_start_time)

        # Start timer for next segment
        self.start_segment_timer()

        self.get_logger().info(
            f"Segment {completed_segment} completed: {completed_file} ({segment_duration.total_seconds():.1f}s)"
        )
        self.get_logger().info(f"Started recording segment {self.segment_number}: {new_segment_file}")
    
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
            final_records = self.frame_records
            final_segment_start = self.segment_start_time
            self._release_current_writer_locked()
            self.frame_records = []

        self._write_segment_metadata(final_video, final_records, final_segment_start)

        # Print recording summary
        if self.segment_duration:
            total_segments = self.segment_number
            self.get_logger().info(f"Recording completed - {total_segments} segments saved")
            self.get_logger().info(f"Last segment: {os.path.abspath(self.output_file)}")
            if hasattr(self, 'base_filename'):
                self.get_logger().info(f"All segments saved with pattern: {self.base_filename}_seg*.mp4")
        else:
            self.get_logger().info(f"Recording saved to: {os.path.abspath(self.output_file)}")
        
    def __del__(self):
        self.stop_recording()


def main():
    parser = argparse.ArgumentParser(description='Record ROS2 camera topic to video')
    parser.add_argument('--topic', '-t', default='/camera/color/image_raw',
                       help='Camera topic name (default: /camera/color/image_raw)')
    parser.add_argument('--output', '-o', default=None,
                       help='Output video file (default: auto-generated timestamp)')
    parser.add_argument('--fps', '-f', type=int, default=30,
                       help='Output video FPS (default: 30)')
    parser.add_argument('--ffmpeg', action='store_true',
                       help='Use FFmpeg instead of OpenCV for encoding')
    parser.add_argument('--codec', '-c', default='mp4v',
                       choices=['mp4v', 'xvid', 'h264'],
                       help='Video codec (default: mp4v, only for OpenCV)')
    parser.add_argument('--segment', '-s', type=int, default=None,
                       help='Segment duration in seconds (e.g., 10 for testing, 600 for 10min, 3600 for 1hr)')
    parser.add_argument('--segment-preset', choices=['test', '10min', '1hour'],
                       help='Preset segment durations: test=10s, 10min=600s, 1hour=3600s')
    
    args = parser.parse_args()
    
    # Process segment duration
    segment_duration = None
    if args.segment_preset:
        preset_durations = {
            'test': 10,
            '10min': 600,
            '1hour': 3600
        }
        segment_duration = preset_durations[args.segment_preset]
    elif args.segment:
        segment_duration = args.segment
    
    # Initialize ROS2
    rclpy.init()
    
    try:
        # Create recorder node
        recorder = CameraRecorder(
            topic_name=args.topic,
            output_file=args.output,
            fps=args.fps,
            use_ffmpeg=args.ffmpeg,
            codec=args.codec,
            segment_duration=segment_duration
        )
        
        print(f"Starting camera recorder...")
        print(f"Topic: {args.topic}")
        if segment_duration:
            print(f"Segmentation: {segment_duration}s per segment")
            print(f"Files will be saved as: *_seg001.mp4, *_seg002.mp4, etc.")
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
