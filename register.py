#!/usr/bin/env python3
"""
Zdrofit Automatic Fitness Class Registration CLI.
"""
import sys
import argparse
from pathlib import Path

from zdrofit.client import ZdrofitClient, DEFAULT_CLUB
from zdrofit.date_parser import parse_target_date
from zdrofit.scheduler import (
    generate_cron_command,
    generate_launchd_plist,
    generate_sync_cron_command,
    generate_sync_launchd_plist
)

def main():
    parser = argparse.ArgumentParser(
        description="Zdrofit Automatic Fitness Class Registration CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 1. Log in to your Zdrofit account (interactive, saves session.json)
  python register.py --login

  # 2. Check and register for all configured classes in range of 48h (from classes.json)
  python register.py --sync

  # 3. Preview status of configured classes without registering (dry-run)
  python register.py --sync --dry-run

  # 4. List classes for next Sunday
  python register.py --date next-sunday --list

  # 5. Schedule registration for Sztangi on Sunday at 08:30 (waits until Friday 08:30)
  python register.py --date next-sunday --time 08:30 --exercise sztangi --wait

  # 6. Show launchd and cron scheduling templates
  python register.py --schedule-help
        """
    )

    parser.add_argument(
        "--config",
        type=str,
        default="classes.json",
        help="Path to JSON configuration file defining target classes (default: classes.json)"
    )
    parser.add_argument(
        "--sync", "--auto",
        dest="sync",
        action="store_true",
        help="Check all classes in config file and register for all that are within the 48-hour window"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate execution without sending actual registration requests"
    )
    parser.add_argument(
        "--date",
        type=str,
        default="next-sunday",
        help="Target date: e.g. 'next-sunday', 'sunday', 'niedziela', 'tomorrow', '2026-10-25' (default: next-sunday)"
    )
    parser.add_argument(
        "--time",
        type=str,
        default="08:30",
        help="Class time: e.g. '08:30', '8:30', '19:30' (default: 08:30)"
    )
    parser.add_argument(
        "--exercise",
        type=str,
        default="sztangi",
        help="Exercise name: e.g. 'sztangi', 'szangi', 'trening silowy dla kobiet' (fuzzy matching supported, default: sztangi)"
    )
    parser.add_argument(
        "--club",
        type=str,
        default=DEFAULT_CLUB,
        help=f"Zdrofit club slug (default: {DEFAULT_CLUB})"
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Open browser window for manual login and save session cookies to session.json"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available classes matching date and/or exercise"
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Wait until registration opens (48 hours before class start) and register with millisecond precision"
    )
    parser.add_argument(
        "--now",
        action="store_true",
        help="Attempt registration immediately without waiting"
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser in visible mode (default: headless)"
    )
    parser.add_argument(
        "--schedule-help",
        action="store_true",
        help="Show instructions for setting up macOS launchd or cron automated scheduling"
    )

    args = parser.parse_args()

    # Schedule Help
    if args.schedule_help:
        print("\n=======================================================")
        print("  MACOS AUTOMATED SCHEDULING GUIDE")
        print("=======================================================")
        print("Registration for Zdrofit classes opens EXACTLY 48 hours before class start.")
        print("For Sunday 08:30 classes, registration opens on FRIDAY at 08:30:00.\n")

        print("=== MODE 1: Multi-Class Periodic Sync (Recommended for classes.json) ===")
        print("Runs periodically in background. Any configured class entering the 48h window is booked automatically.")
        print("Crontab (check every 5 minutes):")
        print("-------------------------------------------------------")
        print(generate_sync_cron_command(config_path=args.config, interval_minutes=5))
        print("-------------------------------------------------------")
        print("Or macOS launchd plist (run every 5 minutes in background):")
        print("-------------------------------------------------------")
        print(generate_sync_launchd_plist(config_path=args.config, interval_seconds=300))
        print("-------------------------------------------------------")

        print("\n=== MODE 2: Single-Class Precision Snipe (--wait) ===")
        print("Runs once, waits for opening second (08:30:00.000) and snipes with millisecond precision.")
        print("Crontab entry (Friday at 08:29 for Sunday 08:30 class):")
        print("-------------------------------------------------------")
        print(generate_cron_command(
            target_date=args.date,
            target_time=args.time,
            exercise=args.exercise,
            club=args.club,
            cron_minute=29,
            cron_hour=8,
            cron_weekday=5
        ))
        print("-------------------------------------------------------")
        print("macOS launchd plist (~/Library/LaunchAgents/com.zdrofit.registration.plist):")
        print("-------------------------------------------------------")
        print(generate_launchd_plist(
            target_date=args.date,
            target_time=args.time,
            exercise=args.exercise,
            club=args.club,
            run_weekday=5,
            run_hour=8,
            run_minute=29
        ))
        print("-------------------------------------------------------")
        print("Load the service:")
        print("  launchctl load ~/Library/LaunchAgents/com.zdrofit.registration.plist\n")

        print("=== MODE 3: Background Process with caffeinate (prevents Mac sleep) ===")
        print(f"  caffeinate -i python register.py --sync &")
        print(f"  caffeinate -i python register.py --date {args.date} --time {args.time} --exercise '{args.exercise}' --wait &")
        print("=======================================================\n")
        return

    client = ZdrofitClient(
        club_slug=args.club,
        session_file="session.json",
        headless=not args.headed
    )

    # 1. Login Mode
    if args.login:
        client.login_interactive()
        return

    # 2. Sync / Config Mode (checks all classes in configuration file)
    if args.sync:
        client.sync_configured_classes(
            config_path=args.config,
            dry_run=args.dry_run,
            wait_next=args.wait
        )
        return

    # Parse target date
    try:
        target_date = parse_target_date(args.date)
        target_day_str = target_date.strftime("%Y-%m-%d")
    except Exception as e:
        print(f"[-] Invalid date '{args.date}': {e}")
        sys.exit(1)

    # 2. List Mode
    if args.list:
        print(f"[*] Fetching schedule for {args.club} (Day: {target_day_str})...")
        schedule = client.fetch_schedule(target_day=target_day_str)
        print(f"[+] Total classes in schedule: {len(schedule)}\n")

        print(f"{'TIME':<7} | {'ACTIVITY':<30} | {'TRAINER':<22} | {'SPOTS':<6} | {'STATUS'}")
        print("-" * 85)
        for item in schedule:
            if item.day == target_day_str:
                status = item.status_text
                if item.is_registered:
                    status = "[REGISTERED]"
                elif item.can_book:
                    status = "[CAN BOOK]"
                elif item.is_early:
                    status = "[EARLY - 48h]"

                print(f"{item.time:<7} | {item.activity_title[:30]:<30} | {item.trainer[:22]:<22} | {item.spots:<6} | {status}")
        return

    # 3. Wait & Register Mode
    if args.wait:
        client.wait_and_register(
            date_str=args.date,
            time_str=args.time,
            exercise_query=args.exercise,
            dry_run=args.dry_run
        )
        return

    # 4. Immediate Register Mode
    if args.now:
        target_class = client.find_class(args.date, args.time, args.exercise)
        if not target_class:
            print(f"[-] No class matching '{args.exercise}' found on {target_day_str} at {args.time}.")
            sys.exit(1)

        if args.dry_run:
            print(f"[!] Dry-run enabled: would register for {target_class}.")
            return

        res = client.register_now(target_class)
        print(f"\nResult: {res}")
        return

    # Default action if neither --wait nor --now nor --list nor --login:
    # Find the class and display its details and registration status
    print(f"[*] Searching for class: '{args.exercise}' on {target_day_str} at {args.time} in {args.club}...")
    target_class = client.find_class(args.date, args.time, args.exercise)
    if not target_class:
        print(f"[-] No class matching '{args.exercise}' found on {target_day_str} at {args.time}.")
        print(f"    Run 'python register.py --date {args.date} --list' to see available classes.")
        sys.exit(1)

    print("\n[+] Target Class Found:")
    print(f"    ID:       {target_class.id}")
    print(f"    Activity: {target_class.activity_title} (slug: {target_class.activity_slug})")
    print(f"    Date:     {target_class.day} {target_class.time}")
    print(f"    Trainer:  {target_class.trainer}")
    print(f"    Spots:    {target_class.spots}")
    print(f"    Status:   {target_class.status_text}")
    if target_class.registration_opens_at:
        print(f"    Opens at: {target_class.registration_opens_at.strftime('%Y-%m-%d %H:%M:%S')} (48h prior)")

    print("\nTo schedule automatic registration, run:")
    print(f"  python register.py --date {args.date} --time {args.time} --exercise '{args.exercise}' --wait")
    print("Or to register immediately (if open):")
    print(f"  python register.py --date {args.date} --time {args.time} --exercise '{args.exercise}' --now")

if __name__ == "__main__":
    main()
