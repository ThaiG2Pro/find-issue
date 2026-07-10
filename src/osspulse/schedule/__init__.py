"""``osspulse.schedule`` — cron scheduling support for V2 (AC-V2-002-001/-014).

Public surface exported here:
    ``generate_line``    — build a crontab line (schedule/cron.py)
    ``generate_workflow``— build a GitHub Actions workflow YAML (schedule/workflow.py)
    ``CrontabClient``    — mockable crontab subprocess wrapper (schedule/crontab.py)
    ``upsert_block``     — insert/replace managed block (schedule/crontab.py)
    ``remove_block``     — remove managed block (schedule/crontab.py)
    ``ScheduleError``    — fatal schedule error class (schedule/errors.py)
"""

from osspulse.schedule.cron import generate_line
from osspulse.schedule.crontab import CrontabClient, remove_block, upsert_block
from osspulse.schedule.errors import ScheduleError
from osspulse.schedule.workflow import generate_workflow

__all__ = [
    "CrontabClient",
    "ScheduleError",
    "generate_line",
    "generate_workflow",
    "remove_block",
    "upsert_block",
]
