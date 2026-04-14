# ROS2 Humble 환경에서 camera_recorder 안전 실행 가이드

Last updated: 2026-04-14

이 문서는 `camera_recorder.py`를 ROS2 Humble 환경에서 **다른 프로젝트의 Python 환경을 건드리지 않고** 실행하는 방법을 다룬다.

---

## 문제의 뿌리: 버전 호환성

ROS2 Humble은 **Python 3.10 + NumPy 1.x**에 강하게 묶여 있다. `rclpy`, `cv_bridge` 등 ROS2 Python 패키지는 C 확장 모듈(`*_pybind11.cpython-310-*.so`)로 빌드되어 배포되며, 인터프리터 버전과 NumPy ABI가 정확히 맞아야만 import 된다.

다른 프로젝트가 Python 3.11/3.12나 NumPy 2.x를 요구하는 경우, 단일 환경에서 둘 다 만족시키는 것은 불가능. **격리가 필요**하다.

### 대표 에러 패턴

#### A. Python 버전 불일치

```
ModuleNotFoundError: No module named 'rclpy._rclpy_pybind11'
The C extension '/opt/ros/humble/lib/python3.10/site-packages/_rclpy_pybind11.cpython-310-x86_64-linux-gnu.so' isn't present on the system.
```

원인: `python3`가 Python 3.10이 아닌 다른 버전(예: uv의 Python 3.12)을 가리킴.
ROS2 Humble의 C 확장은 Python 3.10 전용.

#### B. NumPy ABI 불일치

```
A module that was compiled using NumPy 1.x cannot be run in NumPy 2.2.6 ...
AttributeError: _ARRAY_API not found
Segmentation fault (core dumped)
```

원인: `cv_bridge`가 NumPy 1.x ABI로 컴파일되었는데, 런타임에 NumPy 2.x가 로드됨. `imgmsg_to_cv2` 호출 시 segfault.

---

## 권장 환경 구성

### 원칙

1. **ROS2 전용 Python은 시스템 `/usr/bin/python3.10`만 사용.** 가상환경도 `--system-site-packages`로 만들어 `/opt/ros/humble/...`의 `rclpy`를 상속받는다.
2. **다른 프로젝트의 Python 환경과는 완전히 분리한다.** uv, conda 등이 제공하는 Python 3.11/3.12는 ROS2 용도로 사용 금지.
3. **NumPy는 1.x로 고정.** 시스템 Python 3.10에 `numpy<2` 설치.

### 현재 확인된 환경 (2026-04-14 기준)

```
/usr/bin/python3.10       ← ROS2 Humble 전용
/home/refi/.local/bin/python3 → 3.12 (uv, 다른 프로젝트용)
/home/refi/.local/bin/python3.12 → 3.12 (uv)

/home/refi/.local/lib/python3.10/site-packages/numpy/ → 1.26.4 ✓
/opt/ros/humble/local/lib/python3.10/dist-packages/ → rclpy, cv_bridge 등
```

`python3.10`으로 명시 호출하면 시스템 Python 3.10을 얻는다.

---

## 실행 방법

### 방법 1: `python3.10` 명시 호출 (가장 간단, 현재 동작 확인됨)

```bash
# 1. ROS2 Humble 환경 활성화 (기존 alias 'humble' 또는 직접)
source /opt/ros/humble/setup.bash

# 2. 기존 터미널에서 python3이 3.12를 가리키더라도 python3.10으로 직접 실행
python3.10 camera_recorder.py --branch-id MGOTEST --ffmpeg --video-label topview_video
```

**장점:** 별도 가상환경 없이 즉시 실행.
**단점:** 실수로 `python3`으로 실행하면 에러. 여러 명령 실행 시 매번 `python3.10` 입력 필요.

### 방법 2: ROS2 전용 venv (다중 실행/스크립트화 시 권장)

```bash
# 1. /usr/bin/python3.10 으로 venv 생성, 시스템 패키지(= ROS2 rclpy) 상속
/usr/bin/python3.10 -m venv --system-site-packages ~/.venvs/ros2-humble

# 2. 활성화 및 NumPy 1.x 고정
source ~/.venvs/ros2-humble/bin/activate
pip install 'numpy<2'
deactivate
```

실행할 때:

```bash
source /opt/ros/humble/setup.bash
source ~/.venvs/ros2-humble/bin/activate
python camera_recorder.py --branch-id MGOTEST --ffmpeg
```

**장점:** 활성화되면 `python`이 자동으로 올바른 해석기 지시. 다른 프로젝트의 venv/uv 환경과 깔끔히 격리.
**단점:** 초기 설정 1회 필요.

### 방법 3: 래퍼 스크립트 (운영 배포 시 권장)

`run_recorder.sh`:
```bash
#!/bin/bash
set -e
source /opt/ros/humble/setup.bash
exec /usr/bin/python3.10 "$(dirname "$0")/camera_recorder.py" "$@"
```

호출: `./run_recorder.sh --branch-id MGOTEST --ffmpeg`

M5 systemd 서비스 정의 시에도 `/usr/bin/python3.10` 경로를 명시하면 `$PATH` 우선순위 영향을 받지 않는다.

---

## 다른 프로젝트 환경과의 충돌 방지

### 피해야 할 패턴

- ❌ `pip install --user` 로 최신 NumPy를 시스템 Python 3.10에 설치 → 다음 실행 시 NumPy 2.x 로드 → segfault
- ❌ `uv pip install numpy` 등으로 프로젝트의 `.venv` 외부에 설치
- ❌ `python3` alias를 `python3.12`로 변경 → ROS2 터미널이 ROS 전혀 못 찾음
- ❌ conda activate 후 ROS2 실행 — conda의 Python이 우선되어 rclpy 로드 실패

### 권장 패턴

- ✅ ROS2 작업 전용 터미널과 다른 프로젝트 전용 터미널을 분리
- ✅ ROS2 실행은 항상 `/usr/bin/python3.10` 절대 경로 또는 `--system-site-packages` venv 사용
- ✅ 다른 프로젝트는 uv/poetry/conda로 자체 환경 격리 — 시스템 Python 3.10의 numpy 버전 건드리지 말 것
- ✅ `pip install` 대신 `uv pip install --python <project-venv>` 처럼 대상 명시

### 체크리스트 (실행 전 5초)

```bash
python3.10 -c "import sys; print(sys.executable)"
# → /usr/bin/python3.10

python3.10 -c "import numpy; print(numpy.__version__)"
# → 1.26.4 (2.x 이면 중단)

python3.10 -c "import rclpy; print('OK')"
# → OK (에러면 source /opt/ros/humble/setup.bash 누락)

python3.10 -c "from cv_bridge import CvBridge; print('OK')"
# → OK (segfault 위험 시 NumPy 버전 확인)
```

---

## 복구 시나리오

### NumPy가 어느새 2.x로 업그레이드 되었을 때

```bash
# 시스템 python3.10 영역의 numpy 다운그레이드
/usr/bin/python3.10 -m pip install --user --force-reinstall 'numpy<2'

# venv를 사용 중이라면
source ~/.venvs/ros2-humble/bin/activate
pip install --force-reinstall 'numpy<2'
```

### `python3` 명령이 3.12를 가리켜서 당황했을 때

위 "방법 1"처럼 `python3.10` 명시 호출로 즉시 해결. 재설정 없음.

### `_rclpy_pybind11` 에러만 따로 뜰 때

- `source /opt/ros/humble/setup.bash` 누락 여부 확인
- Python 인터프리터가 3.10인지 확인 (`python3.10` 강제)

---

## 참고

- ROS2 Humble 공식 트러블슈팅: https://docs.ros.org/en/humble/Guides/Installation-Troubleshooting.html#import-failing-without-library-present-on-the-system
- NumPy 2.0 마이그레이션 가이드: https://numpy.org/doc/stable/numpy_2_0_migration_guide.html
- 연관 이슈 발견 히스토리: `docs/history/07_m2_naming_wall_clock_srt_20260414_0900/`

---

## 요약

| 항목 | 값 |
|------|-----|
| Python | **3.10 (시스템 `/usr/bin/python3.10`)** |
| NumPy | **1.x (1.26.4 확인됨)** |
| ROS2 distro | Humble |
| 활성화 | `source /opt/ros/humble/setup.bash` |
| 실행 | `python3.10 camera_recorder.py ...` 또는 `--system-site-packages` venv |
| 격리 원칙 | 다른 프로젝트의 uv/conda 환경과 ROS2 세션을 분리 |
