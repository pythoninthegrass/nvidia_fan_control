# NVIDIA Aggressive Fan Control

A Python-based fan control daemon for headless NVIDIA GPUs, designed for high-power AI workloads.

## Features

- **Multiple fan curves** - From quiet idle to maximum cooling
- **Headless operation** - Works without X11/display (uses NVML directly)
- **Multiple modes** - Choose between quiet, aggressive, performance, or max cooling
- **Systemd service** - Runs automatically on boot
- **Graceful shutdown** - Restores automatic fan control when stopped

## Fan Curves

### Quiet Mode (default)

Matches NVIDIA default at idle, ramps aggressively under load.

| Temperature | Fan Speed |
| ----------- | --------- |
| ≤40°C | 20% |
| 50°C | 30% |
| 60°C | 45% |
| 70°C | 65% |
| 75°C | 80% |
| 80°C+ | 100% |

### Aggressive Mode

| Temperature | Fan Speed |
| ----------- | --------- |
| 30°C | 40% |
| 40°C | 50% |
| 50°C | 65% |
| 55°C | 75% |
| 60°C | 85% |
| 65°C | 95% |
| 70°C+ | 100% |

### Performance Mode

| Temperature | Fan Speed |
| ----------- | --------- |
| 25°C | 50% |
| 35°C | 60% |
| 45°C | 75% |
| 50°C | 85% |
| 55°C | 95% |
| 60°C+ | 100% |

### Max Mode

Always runs fans at 100%.

## Requirements

- NVIDIA GPU with fan control support
- Python 3.13+
- Root/sudo access (required for fan control)
- [uv](https://docs.astral.sh/uv/)

### Tested on

| OS | Version |
| -- | ------- |
| Ubuntu | 26.04 |
| CachyOS | 2026.06 (kernel 7.0.11) |

## Installation

### 1. Install the tool

```bash
# Fan control daemon only
sudo uv tool install "git+https://github.com/pythoninthegrass/nvidia_fan_control"

# With the vLLM stress tester
sudo uv tool install "git+https://github.com/pythoninthegrass/nvidia_fan_control[stress]"
```

### 2. Install the systemd service

```bash
sudo cp nvidia-fan-control.service /etc/systemd/system/
sudo systemctl daemon-reload
```

### 3. Enable and start the service

```bash
sudo systemctl enable --now nvidia-fan-control.service
```

## Usage

### Check service status

```bash
sudo systemctl status nvidia-fan-control
```

### View live logs

```bash
journalctl -u nvidia-fan-control -f
```

### Stop the service (restores automatic fan control)

```bash
sudo systemctl stop nvidia-fan-control
```

### Restart with different mode

Edit the service file to change the mode:

```bash
sudo nano /etc/systemd/system/nvidia-fan-control.service
```

Change the `ExecStart` line:

```ini
# For quiet mode (default - silent idle, aggressive ramp):
ExecStart=/root/.local/bin/nvidia-fan-control --mode quiet --interval 1

# For aggressive mode (always audible):
ExecStart=/root/.local/bin/nvidia-fan-control --mode aggressive --interval 1

# For performance mode (louder, cooler):
ExecStart=/root/.local/bin/nvidia-fan-control --mode performance --interval 1

# For max cooling (100% always):
ExecStart=/root/.local/bin/nvidia-fan-control --mode max --interval 1
```

Then reload and restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart nvidia-fan-control
```

## Manual Usage

```bash
# Run once and exit (fans return to auto after a few minutes)
sudo nvidia-fan-control --once

# Run as daemon with custom interval
sudo nvidia-fan-control --mode performance --interval 2

# Show help
nvidia-fan-control --help
```

## Command Line Options

| Option | Description |
| ------ | ----------- |
| `--mode`, `-m` | Fan curve mode: `quiet` (default), `aggressive`, `performance`, or `max` |
| `--interval`, `-i` | Poll interval in seconds (default: 2.0) |
| `--once` | Set fans once and exit (don't run as daemon) |

## Uninstall

```bash
sudo systemctl stop nvidia-fan-control
sudo systemctl disable nvidia-fan-control
sudo rm /etc/systemd/system/nvidia-fan-control.service
sudo uv tool uninstall nvidia-fan-control
sudo systemctl daemon-reload
```

## Troubleshooting

### Service won't start

Check logs:
```bash
journalctl -u nvidia-fan-control -n 50 --no-pager
```

### Permission denied errors

The service must run as root. Check that the service file has `User=root`.

### Fans not responding

Ensure NVIDIA persistence daemon is running:
```bash
sudo systemctl status nvidia-persistenced
```

### Fans reset to default after stopping

This is expected behavior - the script restores automatic fan control when stopped.

## License

MIT
