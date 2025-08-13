import logging
import time
from typing import Dict, List, Optional
from enum import Enum
from pydantic import BaseModel
from datetime import datetime

class TaskStatus(Enum):
    """Enum for task status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskType(Enum):
    """Enum for task types"""
    WEB_SEARCH = "web_search"
    LINKEDIN_SCRAPING = "linkedin_scraping"
    OTHER_SCRAPING = "other_scraping"
    DATA_CLEANING = "data_cleaning"
    REPORT_GENERATION = "report_generation"

class TaskProgress(BaseModel):
    """Represents task progress information"""
    task_id: str
    task_type: TaskType
    status: TaskStatus
    progress_percentage: float = 0.0
    start_time: datetime
    end_time: Optional[datetime] = None
    error_message: Optional[str] = None
    details: Dict = {}

class TaskUpdaterAgent:
    """Agent responsible for monitoring execution progress and logging errors"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.tasks: Dict[str, TaskProgress] = {}
        self.workflow_start_time = datetime.now()
        self.overall_progress = 0.0
        
    def create_task(self, task_id: str, task_type: TaskType) -> str:
        """
        Create a new task for tracking
        
        Args:
            task_id: Unique identifier for the task
            task_type: Type of task being executed
            
        Returns:
            str: Task ID
        """
        task = TaskProgress(
            task_id=task_id,
            task_type=task_type,
            status=TaskStatus.PENDING,
            start_time=datetime.now()
        )
        
        self.tasks[task_id] = task
        self.logger.info(f"Created task: {task_id} ({task_type.value})")
        return task_id
    
    def update_task_status(self, task_id: str, status: TaskStatus, 
                          progress_percentage: float = None, 
                          error_message: str = None,
                          details: Dict = None) -> None:
        """
        Update task status and progress
        
        Args:
            task_id: Task identifier
            status: New status
            progress_percentage: Progress percentage (0-100)
            error_message: Error message if failed
            details: Additional details about the task
        """
        if task_id not in self.tasks:
            self.logger.warning(f"Task {task_id} not found")
            return
        
        task = self.tasks[task_id]
        task.status = status
        
        if progress_percentage is not None:
            task.progress_percentage = min(max(progress_percentage, 0.0), 100.0)
        
        if error_message:
            task.error_message = error_message
            self.logger.error(f"Task {task_id} failed: {error_message}")
        
        if details:
            task.details.update(details)
        
        if status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            task.end_time = datetime.now()
        
        self.logger.info(f"Task {task_id} status updated: {status.value} "
                        f"({task.progress_percentage:.1f}%)")
        
        # Update overall progress
        self._update_overall_progress()
    
    def get_task_status(self, task_id: str) -> Optional[TaskProgress]:
        """
        Get current status of a task
        
        Args:
            task_id: Task identifier
            
        Returns:
            TaskProgress: Current task progress or None if not found
        """
        return self.tasks.get(task_id)
    
    def get_all_tasks(self) -> List[TaskProgress]:
        """
        Get all tasks
        
        Returns:
            List[TaskProgress]: List of all tasks
        """
        return list(self.tasks.values())
    
    def get_failed_tasks(self) -> List[TaskProgress]:
        """
        Get all failed tasks
        
        Returns:
            List[TaskProgress]: List of failed tasks
        """
        return [task for task in self.tasks.values() if task.status == TaskStatus.FAILED]
    
    def get_overall_progress(self) -> float:
        """
        Get overall workflow progress
        
        Returns:
            float: Overall progress percentage (0-100)
        """
        return self.overall_progress
    
    def get_workflow_summary(self) -> Dict:
        """
        Get workflow summary
        
        Returns:
            Dict: Summary of the workflow execution
        """
        total_tasks = len(self.tasks)
        completed_tasks = len([t for t in self.tasks.values() if t.status == TaskStatus.COMPLETED])
        failed_tasks = len([t for t in self.tasks.values() if t.status == TaskStatus.FAILED])
        in_progress_tasks = len([t for t in self.tasks.values() if t.status == TaskStatus.IN_PROGRESS])
        
        workflow_duration = datetime.now() - self.workflow_start_time
        
        return {
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "in_progress_tasks": in_progress_tasks,
            "overall_progress": self.overall_progress,
            "workflow_duration_seconds": workflow_duration.total_seconds(),
            "start_time": self.workflow_start_time.isoformat(),
            "current_time": datetime.now().isoformat()
        }
    
    def log_task_event(self, task_id: str, event: str, details: Dict = None) -> None:
        """
        Log a task event
        
        Args:
            task_id: Task identifier
            event: Event description
            details: Additional details
        """
        log_message = f"Task {task_id}: {event}"
        if details:
            log_message += f" - {details}"
        
        self.logger.info(log_message)
    
    def log_error(self, task_id: str, error: Exception, context: str = "") -> None:
        """
        Log an error for a specific task
        
        Args:
            task_id: Task identifier
            error: Exception that occurred
            context: Additional context
        """
        error_message = f"Task {task_id} error: {str(error)}"
        if context:
            error_message += f" (Context: {context})"
        
        self.logger.error(error_message, exc_info=True)
        
        # Update task status to failed
        self.update_task_status(task_id, TaskStatus.FAILED, error_message=str(error))
    
    def _update_overall_progress(self) -> None:
        """Update overall workflow progress based on individual task progress"""
        if not self.tasks:
            self.overall_progress = 0.0
            return
        
        # Calculate weighted progress based on task types
        total_weight = 0
        weighted_progress = 0
        
        task_weights = {
            TaskType.LINKEDIN_SCRAPING: 0.6,  # Combined search + scraping
            TaskType.OTHER_SCRAPING: 0.2,
            TaskType.DATA_CLEANING: 0.1,
            TaskType.REPORT_GENERATION: 0.1
        }
        
        for task in self.tasks.values():
            weight = task_weights.get(task.task_type, 0.1)
            total_weight += weight
            
            # Adjust progress based on status
            if task.status == TaskStatus.COMPLETED:
                weighted_progress += weight * 100.0
            elif task.status == TaskStatus.IN_PROGRESS:
                weighted_progress += weight * task.progress_percentage
            elif task.status == TaskStatus.FAILED:
                # Failed tasks contribute partial progress based on what was completed
                weighted_progress += weight * min(task.progress_percentage, 50.0)
        
        if total_weight > 0:
            self.overall_progress = weighted_progress / total_weight
        else:
            self.overall_progress = 0.0
    
    def reset_workflow(self) -> None:
        """Reset the workflow for a new execution"""
        self.tasks.clear()
        self.workflow_start_time = datetime.now()
        self.overall_progress = 0.0
        self.logger.info("Workflow reset")
    
    def export_task_logs(self) -> str:
        """
        Export task logs as a formatted string
        
        Returns:
            str: Formatted task logs
        """
        log_lines = []
        log_lines.append("=== TASK EXECUTION LOG ===")
        log_lines.append(f"Workflow Start: {self.workflow_start_time}")
        log_lines.append(f"Overall Progress: {self.overall_progress:.1f}%")
        log_lines.append("")
        
        for task in self.tasks.values():
            log_lines.append(f"Task: {task.task_id}")
            log_lines.append(f"  Type: {task.task_type.value}")
            log_lines.append(f"  Status: {task.status.value}")
            log_lines.append(f"  Progress: {task.progress_percentage:.1f}%")
            log_lines.append(f"  Start: {task.start_time}")
            if task.end_time:
                log_lines.append(f"  End: {task.end_time}")
                duration = task.end_time - task.start_time
                log_lines.append(f"  Duration: {duration.total_seconds():.1f}s")
            if task.error_message:
                log_lines.append(f"  Error: {task.error_message}")
            if task.details:
                log_lines.append(f"  Details: {task.details}")
            log_lines.append("")
        
        return "\n".join(log_lines)
