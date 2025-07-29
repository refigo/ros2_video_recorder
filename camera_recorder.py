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
                 fps=30, use_ffmpeg=False, codec='mp4v'):
        super().__init__('camera_recorder')
        
        self.topic_name = topic_name
        self.fps = fps
        self.use_ffmpeg = use_ffmpeg
        self.codec = codec
        self.bridge = CvBridge()
        
        # Generate output filename if not provided
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.output_file = f"camera_recording_{timestamp}.mp4"
        else:
            self.output_file = output_file
            
        # Video writer objects
        self.video_writer = None
        self.ffmpeg_process = None
        self.frame_queue = queue.Queue()
        self.recording = False
        self.frame_count = 0
        
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
                if self.use_ffmpeg:
                    self.frame_queue.put(cv_image)
                else:
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
        self.get_logger().info(f"Recording started - Resolution: {self.width}x{self.height}")
        
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
            
            # Start thread to feed frames to FFmpeg
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
                
    def stop_recording(self):
        """Stop recording and cleanup resources"""
        if not self.recording:
            return
            
        self.recording = False
        self.get_logger().info(f"Stopping recording... Total frames: {self.frame_count}")
        
        if self.use_ffmpeg:
            # Wait for queue to empty
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
    
    args = parser.parse_args()
    
    # Initialize ROS2
    rclpy.init()
    
    try:
        # Create recorder node
        recorder = CameraRecorder(
            topic_name=args.topic,
            output_file=args.output,
            fps=args.fps,
            use_ffmpeg=args.ffmpeg,
            codec=args.codec
        )
        
        print(f"Starting camera recorder...")
        print(f"Topic: {args.topic}")
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
