#!/home/qingyuxue/Projects/voice_toolkit/venv/bin/python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from voice_assistant.scheduler import DiaryScheduler

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        sched = DiaryScheduler()
        sched.run_once()
    else:
        sched = DiaryScheduler()
        print("[pc] diary scheduler started (check every 60s)")
        try:
            sched.run_forever()
        except KeyboardInterrupt:
            print("\n[pc] stopped")


if __name__ == "__main__":
    main()
