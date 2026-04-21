# RealSense USB Stability: Overnight Frame Timeout

## Incident (2026-04-21)

Recording ran successfully from 14:08 to ~23:53 (9.75 hours). After midnight, the RealSense D435 stopped producing frames. The recorder continued running (segment timer kept switching hourly) but produced empty MP4s and 0-byte SRT files.

## Symptoms

**RealSense node logs:**
```
WARNING [backend-v4l2.cpp:1858] Frames didn't arrived within 5 seconds
ERROR [librealsense-exception.h:52] get_xu(...). xioctl(UVCIOC_CTRL_QUERY) failed Last Error: Connection timed out
ERROR [global_timestamp_reader.cpp:253] Error during time_diff_keeper polling: ... Connection timed out
```

**Recorder behavior:**
- `image_callback` stops being called (no new messages on topic)
- Segment timer keeps firing → opens new files → 0 frames written
- Result: empty `.srt` files (0 bytes), tiny/empty `.mp4` files
- Service remains `active (running)` — no crash, no error log

**Verification:**
```bash
# Topic exists but no data flowing:
ros2 topic hz /camera/color/image_raw    # no output (timeout)
ros2 topic echo /camera/color/image_raw --once  # returns stale frame with old timestamp
```

## Root Cause

USB autosuspend is enabled for the RealSense device:

```
/sys/bus/usb/devices/2-3/power/control = auto
/sys/bus/usb/devices/2-3/power/autosuspend_delay_ms = 2000
```

After 2 seconds of perceived inactivity, the kernel's USB power management may suspend the port. Once suspended, the RealSense firmware loses USB communication and enters a "frames timeout" state it cannot recover from without a node restart or USB reset.

## Recovery

### Restart camera node

```bash
# If using ros2 launch:
# Kill and relaunch the RealSense node

# If using systemd:
sudo systemctl restart realsense2_camera_node
```

### USB reset (if node restart doesn't recover)

```bash
# Find device:
lsusb | grep "8086:0b07"
# Bus 002 Device 003

# Reset:
sudo usbreset /dev/bus/usb/002/003

# Then restart the RealSense node
```

## Prevention

### Disable USB autosuspend for RealSense

**Immediate (until reboot):**
```bash
echo -1 | sudo tee /sys/bus/usb/devices/2-3/power/autosuspend_delay_ms
echo on | sudo tee /sys/bus/usb/devices/2-3/power/control
```

**Permanent (udev rule):**
```bash
# /etc/udev/rules.d/99-realsense-no-autosuspend.rules
ACTION=="add", ATTRS{idVendor}=="8086", ATTRS{idProduct}=="0b07", \
  ATTR{power/autosuspend_delay_ms}="-1", ATTR{power/control}="on"
```

Then reload:
```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### Global USB autosuspend disable (nuclear option)

```bash
# /etc/default/grub — add to GRUB_CMDLINE_LINUX_DEFAULT:
usbcore.autosuspend=-1
```

Not recommended for laptops (battery drain), but fine for always-on robot PCs.

## Recorder Improvement (Future)

The recorder should detect "no frames received for N seconds" and:
1. Log a WARNING
2. Optionally restart itself (via systemd `Restart=on-failure` + exit with error code)

Currently the recorder silently produces empty segments when the camera dies. This is safe (no data loss, no crash) but wastes disk/upload cycles on empty files.

Possible implementation:
```python
# In image_callback or a watchdog timer:
if (now - self.last_frame_time) > timedelta(seconds=30):
    self.get_logger().error("No frames for 30s — camera may be dead")
    sys.exit(1)  # systemd will restart us
```

## Related

- USB 3.x is required for RealSense D435 depth+color streaming
- Intel RealSense SDK known issue: [github.com/IntelRealSense/librealsense/issues/6292](https://github.com/IntelRealSense/librealsense/issues/6292)
- The D435 firmware does not auto-recover from USB suspend — requires full re-enumeration
