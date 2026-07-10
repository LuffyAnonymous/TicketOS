import threading
import time
from datetime import datetime
import extensions as context
from database import get_db, DBAppEvent
from services.order_service import check_all_platforms_once

class SchedulerService:
    def __init__(self):
        self.lock = threading.Lock()
        self.last_run_time = None
        self.last_run_status = "Idle"
        self.job_history = []  # Logs job runs: {"timestamp": ..., "status": ..., "message": ...}
        self.paused = False
        self._status = "Stopped"

    def log_job(self, status, message):
        run_entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": status,
            "message": message
        }
        self.job_history.append(run_entry)
        if len(self.job_history) > 100:
            self.job_history.pop(0)

        # Save to DB log table
        db = get_db()
        if db:
            try:
                db.add(DBAppEvent(
                    level="INFO" if status in ("Success", "Resumed", "Paused") else "WARNING" if status == "Retry" else "ERROR",
                    source="scheduler",
                    message=f"Job {status}: {message}"
                ))
                db.commit()
            except:
                pass
            finally:
                db.close()

    def run_sync_once(self, manual=False):
        """
        Executes a synchronization cycle across all platform adapters.
        Supports retry on failure.
        """
        with self.lock:
            start_time = datetime.now()
            self.last_run_time = start_time.strftime("%Y-%m-%d %H:%M:%S")
            self.last_run_status = "Running"
            context.state.log(f"Scheduler: Starting sync cycle (manual={manual})")
            
            max_retries = 3
            errors = []
            for attempt in range(1, max_retries + 1):
                try:
                    seen_keys = context.state.load_seen_orders()
                    errors = check_all_platforms_once(seen_keys)
                    if not errors:
                        duration = (datetime.now() - start_time).total_seconds()
                        self.last_run_status = "Success"
                        self.log_job("Success", f"Sync completed successfully in {duration:.1f}s")
                        return True
                    else:
                        self.log_job("Retry", f"Sync attempt {attempt}/{max_retries} failed with errors: {', '.join(errors)}")
                        context.state.log(f"Scheduler: Attempt {attempt} returned errors: {errors}")
                except Exception as ex:
                    errors = [str(ex)]
                    self.log_job("Retry", f"Sync attempt {attempt}/{max_retries} failed with exception: {ex}")
                    context.state.log(f"Scheduler: Attempt {attempt} failed with exception: {ex}")
                
                if attempt < max_retries:
                    # Wait 5 seconds before retrying
                    for _ in range(5):
                        if context.state.stop_event.is_set():
                            break
                        time.sleep(1)
            
            # If we reached here, it failed all attempts
            self.last_run_status = "Failed"
            self.log_job("Failed", f"Sync failed after {max_retries} attempts. Errors: {', '.join(errors)}")
            return False

    def scheduler_loop(self):
        """
        Background loop executing interval-based checks.
        """
        self._status = "Running"
        context.state.running = True
        context.state.log("Scheduler: Background thread loop started")
        
        try:
            while not context.state.stop_event.is_set():
                if not self.paused:
                    self.run_sync_once(manual=False)
                
                interval_mins = int(context.state.settings.get("interval_minutes", 30))
                interval_secs = interval_mins * 60
                
                for _ in range(interval_secs):
                    if context.state.stop_event.is_set():
                        break
                    time.sleep(1)
        finally:
            self._status = "Stopped"
            context.state.running = False
            context.state.log("Scheduler: Background thread loop stopped")

    def start(self):
        """
        Starts the background interval scheduling thread.
        """
        with self.lock:
            if context.state.running or self._status in ("Starting", "Running"):
                return False
            self._status = "Starting"
            context.state.stop_event.clear()
            self.paused = False
            context.state.worker_thread = threading.Thread(target=self.scheduler_loop, daemon=True)
            context.state.worker_thread.start()
            return True

    def stop(self):
        """
        Stops the background interval scheduling thread.
        """
        with self.lock:
            if self._status in ("Starting", "Running"):
                self._status = "Stopping"
            context.state.stop_event.set()

    def pause(self):
        """
        Pauses interval execution.
        """
        self.paused = True
        self.log_job("Paused", "Scheduler execution paused")

    def resume(self):
        """
        Resumes interval execution.
        """
        self.paused = False
        self.log_job("Resumed", "Scheduler execution resumed")
