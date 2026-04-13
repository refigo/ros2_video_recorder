# QoS BEST_EFFORT 호환성 수정

Date: 2026-03-03 18:18

## 목표

그리퍼 카메라 토픽(`/gripper/camera/image_raw`) 구독 시 QoS 비호환으로 프레임이 수신되지 않는 문제를 해결한다.

## 증상

레코더를 그리퍼 카메라 토픽으로 실행하면 프레임이 전혀 수신되지 않고, ROS2 로그에 다음 경고가 출력됨:

```
incompatible QoS. No messages will be received from it.
Last incompatible policy: RELIABILITY
```

## 원인

그리퍼 카메라 퍼블리셔는 **BEST_EFFORT** QoS로 발행하고 있었으나,
`camera_recorder.py`의 구독자는 ROS2 기본값인 **RELIABLE** QoS를 사용하고 있었다.

ROS2 QoS 정책상 RELIABLE 구독자는 BEST_EFFORT 퍼블리셔의 메시지를 수신할 수 없다:

| 퍼블리셔 | 구독자 | 호환성 |
|-----------|--------|--------|
| BEST_EFFORT | BEST_EFFORT | **O** |
| BEST_EFFORT | RELIABLE | **X** ← 문제 |
| RELIABLE | BEST_EFFORT | **O** |
| RELIABLE | RELIABLE | **O** |

## 수정 내용

`camera_recorder.py`의 구독 QoS를 센서 데이터에 적합한 BEST_EFFORT로 변경:

```python
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy

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
```

## 호환성

BEST_EFFORT 구독자는 RELIABLE 퍼블리셔와도 호환되므로,
기존 RealSense 등 RELIABLE로 발행하는 카메라에서도 정상 동작한다.

## 검증

```bash
python3 camera_recorder.py --topic /gripper/camera/image_raw --segment 60
```

변경 후 `Recording started - Resolution: 720x480` 로그가 출력되며 정상 녹화 확인.
