#!/usr/bin/env python3

"""
Test script to verify the camera recorder functionality.
This script can be used to test the recorder with a mock camera publisher.
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2
import numpy as np
import threading
import time


class MockCameraPublisher(Node):
    """Mock camera publisher for testing the recorder"""
    
    def __init__(self):
        super().__init__('mock_camera_publisher')
        
        self.publisher = self.create_publisher(Image, '/camera/color/image_raw', 10)
        self.bridge = CvBridge()
        self.timer = self.create_timer(1.0/30.0, self.publish_frame)  # 30 FPS
        
        # Create a simple test pattern
        self.frame_count = 0
        self.width = 640
        self.height = 480
        
        self.get_logger().info("Mock camera publisher started")
        self.get_logger().info("Publishing to: /camera/color/image_raw")
        
    def publish_frame(self):
        """Generate and publish a test frame"""
        
        # Create a test pattern with moving elements
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        
        # Background gradient
        for y in range(self.height):
            frame[y, :, 0] = int(255 * y / self.height)  # Red gradient
            
        # Moving circle
        center_x = int(self.width/2 + 100 * np.sin(self.frame_count * 0.1))
        center_y = int(self.height/2 + 50 * np.cos(self.frame_count * 0.1))
        cv2.circle(frame, (center_x, center_y), 30, (0, 255, 0), -1)
        
        # Frame counter text
        cv2.putText(frame, f"Frame: {self.frame_count}", 
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        # Timestamp
        timestamp = time.strftime("%H:%M:%S")
        cv2.putText(frame, timestamp, 
                   (10, self.height - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # Convert to ROS Image message
        try:
            image_msg = self.bridge.cv2_to_imgmsg(frame, "bgr8")
            image_msg.header.stamp = self.get_clock().now().to_msg()
            image_msg.header.frame_id = "camera_frame"
            
            self.publisher.publish(image_msg)
            self.frame_count += 1
            
            if self.frame_count % 90 == 0:  # Log every 3 seconds
                self.get_logger().info(f"Published {self.frame_count} frames")
                
        except Exception as e:
            self.get_logger().error(f"Error publishing frame: {str(e)}")


def main():
    print("Mock Camera Publisher for Testing")
    print("This will publish test frames to /camera/color/image_raw")
    print("Run the camera_recorder.py in another terminal to test recording")
    print("Press Ctrl+C to stop")
    
    rclpy.init()
    
    try:
        publisher = MockCameraPublisher()
        rclpy.spin(publisher)
    except KeyboardInterrupt:
        print("\nStopping mock camera publisher...")
    finally:
        rclpy.shutdown()


if __name__ == '__main__':
    main()
