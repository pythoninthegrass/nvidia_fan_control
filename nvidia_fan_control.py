#!/usr/bin/env python3

"""
Aggressive NVIDIA GPU Fan Control Daemon for Headless GPUs
Designed for high-power AI workloads on RTX PRO 6000 cards

Run as: sudo python3 nvidia-fan-control.py
Or install as a systemd service
"""

import argparse
import logging
import pynvml
import signal
import sys
import time
from contextlib import suppress

# Configure logging for systemd journal
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)

# Quiet idle, aggressive ramp curve (DEFAULT)
# Matches NVIDIA default at idle, ramps hard above 45°C
QUIET_CURVE = [
    (40, 30),   # ≤40°C -> 30% (match NVIDIA default idle)
    (45, 40),   # 45°C -> 40% (gentle start)
    (50, 55),   # 50°C -> 55% (starting to work)
    (55, 75),   # 55°C -> 75% (ramping hard)
    (60, 90),   # 60°C -> 90% (aggressive)
    (65, 100),  # 65°C -> 100% (full blast)
]

# Aggressive fan curve: (temp_threshold, fan_speed_percent)
# Fans ramp up much earlier and faster than default
AGGRESSIVE_FAN_CURVE = [
    (30, 40),   # 30°C -> 40% (never let fans be quiet)
    (40, 50),   # 40°C -> 50%
    (50, 65),   # 50°C -> 65%
    (55, 75),   # 55°C -> 75%
    (60, 85),   # 60°C -> 85%
    (65, 95),   # 65°C -> 95%
    (70, 100),  # 70°C -> 100% (full blast)
]

# Even more aggressive "performance" curve
PERFORMANCE_FAN_CURVE = [
    (25, 50),   # 25°C -> 50% (always loud, always cool)
    (35, 60),   # 35°C -> 60%
    (45, 75),   # 45°C -> 75%
    (50, 85),   # 50°C -> 85%
    (55, 95),   # 55°C -> 95%
    (60, 100),  # 60°C -> 100%
]

# Maximum cooling - just run at 100% always
MAX_COOLING_CURVE = [
    (0, 100),   # Always 100%
]


class NvidiaFanController:
    def __init__(self, curve: list[tuple[int, int]], poll_interval: float = 2.0):
        self.curve = sorted(curve, key=lambda x: x[0])
        self.poll_interval = poll_interval
        self.running = False
        self.handles = []
        self.fan_counts = []

    def init(self):
        """Initialize NVML and get GPU handles"""
        pynvml.nvmlInit()
        count = pynvml.nvmlDeviceGetCount()

        log.info(f"Found {count} NVIDIA GPU(s)")

        for i in range(count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(handle)
            fan_count = pynvml.nvmlDeviceGetNumFans(handle)

            self.handles.append(handle)
            self.fan_counts.append(fan_count)

            log.info(f"  GPU {i}: {name} ({fan_count} fans)")

            # Enable manual fan control for all fans
            for fan_idx in range(fan_count):
                try:
                    pynvml.nvmlDeviceSetFanControlPolicy(
                        handle, fan_idx, pynvml.NVML_FAN_POLICY_MANUAL
                    )
                except pynvml.NVMLError as e:
                    log.warning(f"    Could not set manual control for fan {fan_idx}: {e}")

        log.info(f"Fan curve: {self.curve}")
        log.info(f"Poll interval: {self.poll_interval}s")

    def get_fan_speed_for_temp(self, temp: int) -> int:
        """Calculate fan speed based on temperature using the curve"""
        if temp <= self.curve[0][0]:
            return self.curve[0][1]

        if temp >= self.curve[-1][0]:
            return self.curve[-1][1]

        # Linear interpolation between curve points
        for i in range(len(self.curve) - 1):
            t1, s1 = self.curve[i]
            t2, s2 = self.curve[i + 1]

            if t1 <= temp <= t2:
                # Linear interpolation
                ratio = (temp - t1) / (t2 - t1)
                return int(s1 + ratio * (s2 - s1))

        return self.curve[-1][1]

    def update_fans(self):
        """Update fan speeds for all GPUs based on current temperatures"""
        for gpu_idx, (handle, fan_count) in enumerate(zip(self.handles, self.fan_counts, strict=False)):
            try:
                temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                target_speed = self.get_fan_speed_for_temp(temp)

                current_speeds = []
                for fan_idx in range(fan_count):
                    current = -1
                    with suppress(Exception):
                        current = pynvml.nvmlDeviceGetFanSpeed_v2(handle, fan_idx)
                    current_speeds.append(current)

                # Set fan speeds
                for fan_idx in range(fan_count):
                    try:
                        pynvml.nvmlDeviceSetFanSpeed_v2(handle, fan_idx, target_speed)
                    except pynvml.NVMLError as e:
                        log.error(f"GPU {gpu_idx} Fan {fan_idx}: Error setting speed: {e}")

                log.info(f"GPU {gpu_idx}: {temp}°C -> {target_speed}% (was: {current_speeds})")

            except pynvml.NVMLError as e:
                log.error(f"GPU {gpu_idx}: Error reading temperature: {e}")

    def restore_auto_control(self):
        """Restore automatic fan control on all GPUs"""
        log.info("Restoring automatic fan control...")
        for gpu_idx, (handle, fan_count) in enumerate(zip(self.handles, self.fan_counts, strict=False)):
            for fan_idx in range(fan_count):
                try:
                    pynvml.nvmlDeviceSetFanControlPolicy(
                        handle, fan_idx,
                        pynvml.NVML_FAN_POLICY_TEMPERATURE_CONTINOUS_SW
                    )
                    log.info(f"  GPU {gpu_idx} Fan {fan_idx}: Restored to auto")
                except pynvml.NVMLError as e:
                    log.error(f"  GPU {gpu_idx} Fan {fan_idx}: Could not restore: {e}")

    def run(self):
        """Main control loop"""
        self.running = True
        log.info("Fan control daemon started.")

        try:
            while self.running:
                self.update_fans()
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            log.info("Interrupted by user")
        finally:
            self.restore_auto_control()
            pynvml.nvmlShutdown()
            log.info("Fan control daemon stopped.")

    def stop(self):
        """Stop the control loop"""
        self.running = False


def main():
    parser = argparse.ArgumentParser(
        description="Aggressive NVIDIA GPU Fan Control for Headless Systems"
    )
    parser.add_argument(
        "--mode", "-m",
        choices=["quiet", "aggressive", "performance", "max"],
        default="quiet",
        help="Fan curve mode: quiet (default), aggressive, performance, or max (100%% always)"
    )
    parser.add_argument(
        "--interval", "-i",
        type=float,
        default=2.0,
        help="Poll interval in seconds (default: 2.0)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Set fans once and exit (don't run as daemon)"
    )

    args = parser.parse_args()

    curves = {
        "quiet": QUIET_CURVE,
        "aggressive": AGGRESSIVE_FAN_CURVE,
        "performance": PERFORMANCE_FAN_CURVE,
        "max": MAX_COOLING_CURVE,
    }

    curve = curves[args.mode]
    log.info(f"NVIDIA Fan Control - Mode: {args.mode.upper()}")
    log.info("=" * 50)

    controller = NvidiaFanController(curve, args.interval)

    # Handle signals for clean shutdown
    def signal_handler(sig, frame):
        log.info(f"Received signal {sig}")
        controller.stop()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    controller.init()

    if args.once:
        controller.update_fans()
        log.info("Ran once. Fans will return to auto control after a few minutes.")
    else:
        controller.run()


if __name__ == "__main__":
    main()
