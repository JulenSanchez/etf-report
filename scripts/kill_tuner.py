"""Kill any process listening on port 5179 (Quant Tuner)."""
import subprocess
import sys

PORT = 5179

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
