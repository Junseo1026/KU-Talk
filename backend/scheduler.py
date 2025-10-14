"""Scheduler to run the crawler daily at 08:00.

This uses APScheduler to schedule the job. Run this script in the background
on the server to have the crawler check for new posts every day at 08:00.

Usage: set env (`source .env`), then `python scheduler.py` or run with nohup.
"""
import os
import sys
from apscheduler.schedulers.blocking import BlockingScheduler
from datetime import datetime

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)

from crawler import KKUCrawler


def job():
    print(f"[{datetime.now().isoformat()}] Scheduler job starting: checking for new posts...")
    c = KKUCrawler()
    c.run(max_pages=3)
    print(f"[{datetime.now().isoformat()}] Scheduler job finished")


def main():
    sched = BlockingScheduler(timezone="UTC")
    # Run daily at 08:00 KST (UTC+9). APScheduler expects timezone-aware times;
    # we schedule at 23:00 UTC previous day, which corresponds to 08:00 KST.
    # Alternatively, if the server runs in local timezone change accordingly.
    sched.add_job(job, 'cron', hour=23, minute=0)
    print("Scheduler started, job scheduled daily at 08:00 KST (23:00 UTC)")
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        print('Scheduler stopped')


if __name__ == '__main__':
    main()

