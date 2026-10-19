import shlex
import sys
from pathlib import Path
from xml.sax.saxutils import escape

LAUNCHD_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.zdrofit.registration</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>{script_path}</string>
        <string>--date</string>
        <string>{target_date}</string>
        <string>--time</string>
        <string>{target_time}</string>
        <string>--exercise</string>
        <string>{exercise}</string>
        <string>--club</string>
        <string>{club}</string>
        <string>--wait</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>{weekday}</integer> <!-- 1=Monday, ..., 5=Friday, 7=Sunday -->
        <key>Hour</key>
        <integer>{hour}</integer>
        <key>Minute</key>
        <integer>{minute}</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>{stdout_path}</string>
    <key>StandardErrorPath</key>
    <string>{stderr_path}</string>
    <key>WorkingDirectory</key>
    <string>{work_dir}</string>
</dict>
</plist>
"""

def generate_launchd_plist(
    target_date: str = "next-sunday",
    target_time: str = "08:30",
    exercise: str = "sztangi",
    club: str = "zerniki-wroclawskie-zasluczanska",
    run_weekday: int = 5, # Friday (opens 48h before Sunday)
    run_hour: int = 8,
    run_minute: int = 29
) -> str:
    """Generate launchd plist for macOS scheduling."""
    work_dir = Path.cwd().resolve()
    python_path = sys.executable
    script_path = work_dir / "register.py"
    log_dir = work_dir / "logs"
    log_dir.mkdir(exist_ok=True)

    return LAUNCHD_TEMPLATE.format(
        python_path=escape(str(python_path)),
        script_path=escape(str(script_path)),
        target_date=escape(target_date),
        target_time=escape(target_time),
        exercise=escape(exercise),
        club=escape(club),
        weekday=run_weekday,
        hour=run_hour,
        minute=run_minute,
        stdout_path=escape(str(log_dir / "zdrofit_out.log")),
        stderr_path=escape(str(log_dir / "zdrofit_err.log")),
        work_dir=escape(str(work_dir))
    )

def generate_cron_command(
    target_date: str = "next-sunday",
    target_time: str = "08:30",
    exercise: str = "sztangi",
    club: str = "zerniki-wroclawskie-zasluczanska",
    cron_minute: int = 29,
    cron_hour: int = 8,
    cron_weekday: int = 5 # Friday
) -> str:
    """Generate cron command string for crontab -e."""
    work_dir = Path.cwd().resolve()
    python_path = sys.executable
    script_path = work_dir / "register.py"
    log_dir = work_dir / "logs"
    log_dir.mkdir(exist_ok=True)

    q = shlex.quote
    return (
        f"{cron_minute} {cron_hour} * * {cron_weekday} cd {q(str(work_dir))} && {q(python_path)} {q(str(script_path))}"
        f" --date {q(target_date)} --time {q(target_time)} --exercise {q(exercise)} --club {q(club)}"
        f" --wait >> {q(str(log_dir / 'cron.log'))} 2>&1"
    )

def generate_sync_cron_command(config_path: str = "classes.json", interval_minutes: int = 5) -> str:
    """Generate cron command to run sync periodically."""
    work_dir = Path.cwd().resolve()
    python_path = sys.executable
    script_path = work_dir / "register.py"
    log_dir = work_dir / "logs"
    log_dir.mkdir(exist_ok=True)

    q = shlex.quote
    return (
        f"*/{interval_minutes} * * * * cd {q(str(work_dir))} && {q(python_path)} {q(str(script_path))}"
        f" --config {q(config_path)} --sync >> {q(str(log_dir / 'sync_cron.log'))} 2>&1"
    )

def generate_sync_launchd_plist(config_path: str = "classes.json", interval_seconds: int = 300) -> str:
    """Generate launchd plist for periodic sync."""
    work_dir = Path.cwd().resolve()
    python_path = sys.executable
    script_path = work_dir / "register.py"
    log_dir = work_dir / "logs"
    log_dir.mkdir(exist_ok=True)
    python_path, script_path, config_path, log_dir, work_dir = (
        escape(str(v)) for v in (python_path, script_path, config_path, log_dir, work_dir)
    )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.zdrofit.sync</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>{script_path}</string>
        <string>--config</string>
        <string>{config_path}</string>
        <string>--sync</string>
    </array>
    <key>StartInterval</key>
    <integer>{interval_seconds}</integer>
    <key>StandardOutPath</key>
    <string>{log_dir}/sync_out.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/sync_err.log</string>
    <key>WorkingDirectory</key>
    <string>{work_dir}</string>
</dict>
</plist>
"""
