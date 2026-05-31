#!/home/qingyuxue/Projects/voice_toolkit/venv/bin/python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from voice_assistant.scheduler import DiaryScheduler

def main():
    sched = DiaryScheduler()
    sched.run_once()


if __name__ == "__main__":
    main()
