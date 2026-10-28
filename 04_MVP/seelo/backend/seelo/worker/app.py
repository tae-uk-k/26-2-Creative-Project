"""Procrastinate 앱(06 1장). 작업 모듈은 단계마다 채운다."""

from procrastinate import App, PsycopgConnector

from seelo.config import get_settings

TASK_MODULES = [
    "seelo.worker.tasks_collect",
    "seelo.worker.tasks_measure",
    "seelo.worker.tasks_plan",
    "seelo.worker.tasks_fix",
    "seelo.worker.tasks_report",
    "seelo.worker.tasks_email",
    "seelo.worker.periodic",
]

app = App(
    connector=PsycopgConnector(conninfo=get_settings().queue_database_dsn),
    import_paths=TASK_MODULES,
)
