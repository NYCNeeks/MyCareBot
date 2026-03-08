"""
Notion Manager — all reads/writes to Notion.
Includes user profile memory so the bot truly remembers you.
"""
import os
from datetime import datetime, date
from notion_client import Client


class NotionManager:
    def __init__(self):
        self.client = Client(auth=os.getenv("NOTION_TOKEN"))
        self.reminders_db  = os.getenv("NOTION_REMINDERS_DB_ID")
        self.tasks_db      = os.getenv("NOTION_TASKS_DB_ID")
        self.health_db     = os.getenv("NOTION_HEALTH_DB_ID")
        self.runs_db       = os.getenv("NOTION_RUNS_DB_ID")
        self.profile_db    = os.getenv("NOTION_PROFILE_DB_ID")
        self._profile_cache = None  # in-memory cache

    # ─────────────────────────────────────────
    # USER PROFILE / MEMORY
    # ─────────────────────────────────────────

    def get_user_profile(self, use_cache=True) -> dict:
        """Load the user profile from Notion — this is the bot's long-term memory."""
        if use_cache and self._profile_cache:
            return self._profile_cache

        try:
            results = self.client.databases.query(database_id=self.profile_db, page_size=1)
            pages = results.get("results", [])
            if not pages:
                return {}
            props = pages[0]["properties"]
            profile = {
                "name":          self.prop_text(props, "Name"),
                "running_goal":  self.prop_text(props, "Running Goal"),
                "vitamins":      self.prop_text(props, "Vitamins"),
                "skin_routine":  self.prop_text(props, "Skin Routine"),
                "diet_notes":    self.prop_text(props, "Diet Notes"),
                "health_notes":  self.prop_text(props, "Health Notes"),
                "timezone":      self.prop_text(props, "Timezone"),
                "checkin_time":  self.prop_text(props, "Check-in Time"),
                "morning_time":  self.prop_text(props, "Morning Message Time"),
            }
            self._profile_cache = profile
            return profile
        except Exception as e:
            print(f"[Notion] Error loading profile: {e}")
            return {}

    def update_profile(self, field: str, value: str) -> bool:
        """Update a single field in the user profile."""
        try:
            results = self.client.databases.query(database_id=self.profile_db, page_size=1)
            pages = results.get("results", [])
            if not pages:
                return False
            page_id = pages[0]["id"]
            self.client.pages.update(
                page_id=page_id,
                properties={field: {"rich_text": [{"text": {"content": value}}]}},
            )
            self._profile_cache = None  # invalidate cache
            return True
        except Exception as e:
            print(f"[Notion] Error updating profile: {e}")
            return False

    # ─────────────────────────────────────────
    # REMINDERS
    # ─────────────────────────────────────────

    def get_due_reminders(self) -> list:
        """Return reminders matching current HH:MM and today's weekday."""
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        current_day  = now.strftime("%A")
        try:
            results = self.client.databases.query(
                database_id=self.reminders_db,
                filter={"and": [
                    {"property": "Active",  "checkbox":     {"equals": True}},
                    {"property": "Time",    "rich_text":    {"equals": current_time}},
                    {"property": "Days",    "multi_select": {"contains": current_day}},
                ]},
            )
            return results.get("results", [])
        except Exception as e:
            print(f"[Notion] Error fetching due reminders: {e}")
            return []

    def get_all_reminders(self) -> list:
        try:
            results = self.client.databases.query(
                database_id=self.reminders_db,
                filter={"property": "Active", "checkbox": {"equals": True}},
            )
            return results.get("results", [])
        except Exception as e:
            print(f"[Notion] Error listing reminders: {e}")
            return []

    # ─────────────────────────────────────────
    # TASKS
    # ─────────────────────────────────────────

    def get_tasks(self, status=None) -> list:
        try:
            filter_obj = {"property": "Status", "select": {"equals": status}} if status else None
            results = self.client.databases.query(
                database_id=self.tasks_db,
                filter=filter_obj,
                sorts=[{"property": "Priority", "direction": "descending"}],
            )
            return results.get("results", [])
        except Exception as e:
            print(f"[Notion] Error fetching tasks: {e}")
            return []

    def add_task(self, name: str, steps: str, priority="Medium", due_date=None) -> bool:
        try:
            props = {
                "Task Name": {"title":     [{"text": {"content": name}}]},
                "Steps":     {"rich_text": [{"text": {"content": steps}}]},
                "Status":    {"select":    {"name": "To Do"}},
                "Priority":  {"select":    {"name": priority}},
            }
            if due_date:
                props["Due Date"] = {"date": {"start": due_date}}
            self.client.pages.create(parent={"database_id": self.tasks_db}, properties=props)
            return True
        except Exception as e:
            print(f"[Notion] Error adding task: {e}")
            return False

    def update_task_status(self, page_id: str, new_status: str) -> bool:
        try:
            self.client.pages.update(
                page_id=page_id,
                properties={"Status": {"select": {"name": new_status}}},
            )
            return True
        except Exception as e:
            print(f"[Notion] Error updating task: {e}")
            return False

    # ─────────────────────────────────────────
    # HEALTH LOG
    # ─────────────────────────────────────────

    def log_health(self, log_type: str, notes="", status="Done") -> bool:
        try:
            self.client.pages.create(
                parent={"database_id": self.health_db},
                properties={
                    "Date":   {"title":     [{"text": {"content": str(date.today())}}]},
                    "Type":   {"select":    {"name": log_type}},
                    "Status": {"select":    {"name": status}},
                    "Notes":  {"rich_text": [{"text": {"content": notes}}]},
                },
            )
            return True
        except Exception as e:
            print(f"[Notion] Error logging health: {e}")
            return False

    def get_health_logs(self, limit=20) -> list:
        try:
            results = self.client.databases.query(
                database_id=self.health_db,
                sorts=[{"property": "Date", "direction": "descending"}],
                page_size=limit,
            )
            raw = results.get("results", [])
            return [
                {
                    "type":   self.prop_select(r["properties"], "Type"),
                    "status": self.prop_select(r["properties"], "Status"),
                    "date":   self.prop_text(r["properties"],   "Date"),
                    "notes":  self.prop_text(r["properties"],   "Notes"),
                }
                for r in raw
            ]
        except Exception as e:
            print(f"[Notion] Error fetching health logs: {e}")
            return []

    # ─────────────────────────────────────────
    # RUNNING LOG
    # ─────────────────────────────────────────

    def log_run(self, distance_km: float, duration_min: int, notes="", feeling="Good") -> bool:
        try:
            pace = round(duration_min / distance_km, 2) if distance_km > 0 else 0
            self.client.pages.create(
                parent={"database_id": self.runs_db},
                properties={
                    "Date":         {"title":     [{"text": {"content": str(date.today())}}]},
                    "Distance (km)":{"number":    distance_km},
                    "Duration (min)":{"number":   duration_min},
                    "Pace (min/km)": {"number":   pace},
                    "Feeling":      {"select":    {"name": feeling}},
                    "Notes":        {"rich_text": [{"text": {"content": notes}}]},
                },
            )
            return True
        except Exception as e:
            print(f"[Notion] Error logging run: {e}")
            return False

    def get_run_history(self, limit=20) -> list:
        try:
            results = self.client.databases.query(
                database_id=self.runs_db,
                sorts=[{"property": "Date", "direction": "descending"}],
                page_size=limit,
            )
            raw = results.get("results", [])
            runs = []
            for r in raw:
                props = r["properties"]
                runs.append({
                    "date":     self.prop_text(props, "Date"),
                    "distance": props.get("Distance (km)",  {}).get("number", 0),
                    "duration": props.get("Duration (min)", {}).get("number", 0),
                    "pace":     props.get("Pace (min/km)",  {}).get("number", 0),
                    "feeling":  self.prop_select(props, "Feeling"),
                    "notes":    self.prop_text(props, "Notes"),
                })
            return runs
        except Exception as e:
            print(f"[Notion] Error fetching run history: {e}")
            return []

    def get_run_stats(self) -> dict:
        """Aggregate stats: total runs, total km, avg pace, longest run."""
        runs = self.get_run_history(limit=100)
        if not runs:
            return {}
        total_runs = len(runs)
        total_km   = sum(r["distance"] for r in runs)
        total_min  = sum(r["duration"] for r in runs)
        longest    = max(runs, key=lambda r: r["distance"])
        avg_pace   = round(total_min / total_km, 2) if total_km > 0 else 0
        return {
            "total_runs":     total_runs,
            "total_km":       round(total_km, 1),
            "total_duration": total_min,
            "avg_pace":       avg_pace,
            "longest_km":     longest["distance"],
            "longest_date":   longest["date"],
        }

    # ─────────────────────────────────────────
    # PROPERTY HELPERS
    # ─────────────────────────────────────────

    @staticmethod
    def prop_text(props: dict, key: str) -> str:
        try:
            prop  = props.get(key, {})
            ptype = prop.get("type", "")
            items = prop.get("title" if ptype == "title" else "rich_text", [])
            if isinstance(items, list) and items:
                return items[0].get("text", {}).get("content", "")
        except Exception:
            pass
        return ""

    @staticmethod
    def prop_select(props: dict, key: str) -> str:
        try:
            return props.get(key, {}).get("select", {}).get("name", "")
        except Exception:
            return ""

    @staticmethod
    def prop_multiselect(props: dict, key: str) -> list:
        try:
            return [i["name"] for i in props.get(key, {}).get("multi_select", [])]
        except Exception:
            return []
