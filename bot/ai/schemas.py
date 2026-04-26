# Intent name constants
TASK_CREATE = "task_create"
TASK_LIST = "task_list"
TASK_COMPLETE = "task_complete"
TASK_UPDATE = "task_update"
TASK_DELETE = "task_delete"

STUDY_ADD_SUBJECT = "study_add_subject"
STUDY_ADD_RECORD = "study_add_record"
STUDY_LIST = "study_list"

SCHEDULE_ADD_EVENT = "schedule_add_event"
SCHEDULE_VIEW = "schedule_view"
SCHEDULE_PLAN_DAY = "schedule_plan_day"

REMINDER_CREATE = "reminder_create"
REMINDER_LIST = "reminder_list"
REMINDER_CANCEL = "reminder_cancel"

MEMORY_SAVE = "memory_save"
MEMORY_RECALL = "memory_recall"

PROJECT_CREATE = "project_create"
PROJECT_LIST = "project_list"
EXPENSE_ADD = "expense_add"
EXPENSE_STATS = "expense_stats"

SECTION_CREATE = "section_create"
SECTION_RECORD_ADD = "section_record_add"
SECTION_QUERY = "section_query"

REGIME_SLEEP_CALC = "regime_sleep_calc"
REGIME_DAY_PLAN = "regime_day_plan"

EXPORT_EXCEL = "export_excel"
EXPORT_TXT = "export_txt"
BACKUP_CREATE = "backup_create"
MENU_SHOW = "menu_show"
ANALYTICS_QUERY = "analytics_query"

CHAT = "chat"
UNKNOWN = "unknown"

# Destructive intents that require user confirmation
DESTRUCTIVE = {TASK_DELETE, "section_delete", "memory_clear"}
