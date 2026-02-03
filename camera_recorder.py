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
from datetime import datetime


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
        
        # Base filename for segmented recording
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if self.segment_duration:
                self.base_filename = f"camera_recording_{timestamp}"
                self.output_file = f"{self.base_filename}_seg001.mp4"
            else:
                self.output_file = f"camera_recording_{timestamp}.mp4"
        else:
            if self.segment_duration:
                # Remove extension and add segment info
                base = os.path.splitext(output_file)[0]
                ext = os.path.splitext(output_file)[1] or '.mp4'
                self.base_filename = base
                self.output_file = f"{base}_seg001{ext}"
            else:
                self.output_file = output_file
            
        # Video writer objects
        self.video_writer = None
        self.ffmpeg_process = None
        self.ffmpeg_thread = None
        self.frame_queue = queue.Queue()
        self.recording = False
        self.frame_count = 0
        self.writer_lock = threading.Lock()
        
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
                with self.writer_lock:
                    if self.use_ffmpeg:
                        self.frame_queue.put(cv_image)
                    else:
                        if self.video_writer:
                            self.video_writer.write(cv_image)
                    
                self.frame_count += 1
                if self.frame_count % 30 == 0:  # Log every 30 frames
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
        self.segment_start_time = datetime.now()
        
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
            segment_duration = datetime.now() - self.segment_start_time

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

            self.segment_start_time = datetime.now()
            self.frame_count = 0  # Reset frame count for new segment
            new_segment_file = self.output_file

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
            self._release_current_writer_locked()
        
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
