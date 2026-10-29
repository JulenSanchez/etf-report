"""Kill any process listening on the dev Tuner port (config/tuner_config.json)."""
import subprocess
import sys

from tuner_config import DEV_TUNER_PORT

PORT = DEV_TUNER_PORT

try:
    output = subprocess.check_output(
        f'netstat -aon | findstr ":{PORT}"',
        shell=True, timeout=5
    ).decode(errors='replace')
    for line in output.strip().splitlines():
        if 'LISTENING' in line:
            pid = int(line.strip().split()[-1])
            subprocess.call(['taskkill', '/F', '/PID', str(pid)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"[kill_tuner] Killed PID {pid} on port {PORT}")
except (subprocess.TimeoutExpired, subprocess.CalledProcessError, ValueError):
    pass
