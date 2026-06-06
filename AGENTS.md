# AGENTS.md

This file provides guidance to AI agents when working with code in this repository.

## Overview

Python package providing a headless NVIDIA GPU fan control daemon (`nvidia-fan-control`) and an optional vLLM load-testing utility (`stress-vllm`). Uses `pynvml` (NVML bindings) to set fan speeds — no X11/display required. Requires root.

## Package Structure

```
main.py                         # symlink → src/nvidia_fan_control/main.py
src/nvidia_fan_control/
    __init__.py                 # re-exports main; entry point: nvidia-fan-control
    main.py                     # fan control daemon
    stress_vllm.py              # vLLM stress tester; entry point: stress-vllm
pyproject.toml
nvidia-fan-control.service
```

## Runtime

Python 3.13 managed via `mise`.

## Installation

```bash
# Install the fan control daemon
uv tool install "git+https://github.com/pythoninthegrass/nvidia_fan_control"

# Install with the vLLM stress tester (adds aiohttp)
uv tool install "git+https://github.com/pythoninthegrass/nvidia_fan_control[stress]"
```

## Common Commands

```bash
# Run the daemon manually (requires root)
sudo nvidia-fan-control --mode quiet --interval 2

# Run once and exit
sudo nvidia-fan-control --once

# Systemd service
sudo systemctl status nvidia-fan-control
journalctl -u nvidia-fan-control -f

# Stress test vLLM (edit VLLM_URL and MODEL constants first)
stress-vllm
```

## Linting

```bash
# Check
mise exec -- ruff check .
mise exec -- ruff format --check --diff .

# Fix
mise exec -- ruff check --fix .
mise exec -- ruff format .

# Pre-commit (runs ruff + markdownlint + hygiene checks)
mise exec -- prek run --all-files
```

Config: `ruff.toml` — line length 130, target Python 3.13, `fix-only = true`.

## Architecture

`NvidiaFanController` in `src/nvidia_fan_control/main.py` manages all GPUs found via NVML:

- `init()` — calls `nvmlInit()`, enumerates GPUs, sets `NVML_FAN_POLICY_MANUAL` on every fan
- `get_fan_speed_for_temp(temp)` — linear interpolation between sorted curve points
- `update_fans()` — reads each GPU's temperature, computes target speed, calls `nvmlDeviceSetFanSpeed_v2`
- `restore_auto_control()` — called on shutdown; sets `NVML_FAN_POLICY_TEMPERATURE_CONTINOUS_SW` to hand control back to the driver
- `run()` — poll loop; catches `SIGTERM`/`SIGINT` via `signal_handler` → `controller.stop()`

Fan curves are module-level constants (`QUIET_CURVE`, `AGGRESSIVE_FAN_CURVE`, `PERFORMANCE_FAN_CURVE`, `MAX_COOLING_CURVE`) — list of `(temp_threshold, fan_speed_percent)` tuples, sorted ascending by temperature in `__init__`.

## Deployment

Service file `nvidia-fan-control.service` must be deployed to `/etc/systemd/system/`. The service depends on `nvidia-persistenced.service`.

Install the tool as root before deploying the service:

```bash
sudo uv tool install "git+https://github.com/pythoninthegrass/nvidia_fan_control"
sudo cp nvidia-fan-control.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nvidia-fan-control
```

To change mode after deployment, edit `ExecStart` in the service file and run `systemctl daemon-reload && systemctl restart nvidia-fan-control`.
