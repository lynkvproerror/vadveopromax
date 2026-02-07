"""
VEO Pro Max - Expired Transfer Handler

Reference: SESSION_06_WORKFLOWS_SECURITY.md
Role: Transfer work from expired cookie to healthy one
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict
from datetime import datetime
from enum import Enum
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.session import AccountSession
from core.dispatcher import Task, TaskState


class TransferStatus(str, Enum):
    """Work transfer status."""
    PENDING = "pending"
    TRANSFERRED = "transferred"
    FAILED = "failed"
    NO_HEALTHY_COOKIE = "no_healthy_cookie"


@dataclass
class TransferResult:
    """Result of work transfer."""
    success: bool
    source_email: str
    target_email: Optional[str] = None
    tasks_transferred: int = 0
    continuations_handled: int = 0
    message: str = ""


@dataclass
class PendingWork:
    """Pending work from an expired cookie."""
    task: Task
    is_continuation: bool = False
    parent_task_id: Optional[str] = None
    chain_position: int = 0  # Position in continuation chain


class ExpiredCookieTransferHandler:
    """Handle work transfer when cookie expires.
    
    Features:
    - Collect pending work from expired cookie
    - Find healthy cookie for transfer
    - Handle continuation chains specially
    """
    
    def __init__(self):
        self._sessions: Dict[str, AccountSession] = {}
        self._pending_by_email: Dict[str, List[PendingWork]] = {}
    
    def register_session(self, session: AccountSession):
        """Register a session."""
        self._sessions[session.email] = session
    
    def unregister_session(self, email: str):
        """Remove a session."""
        if email in self._sessions:
            del self._sessions[email]
    
    def collect_pending_work(
        self,
        email: str,
        tasks: List[Task],
    ) -> List[PendingWork]:
        """Collect pending work from an expired cookie.
        
        Args:
            email: Expired cookie email
            tasks: All tasks that were assigned to this email
        
        Returns:
            List of PendingWork items
        """
        pending = []
        
        # Find tasks assigned to this email that are not complete
        for task in tasks:
            if task.assigned_account != email:
                continue
            
            if task.state in (TaskState.COMPLETED, TaskState.CANCELLED, TaskState.FAILED):
                continue
            
            # Determine if continuation
            is_continuation = task.is_continuation
            chain_pos = self._get_chain_position(task, tasks)
            
            work = PendingWork(
                task=task,
                is_continuation=is_continuation,
                parent_task_id=task.parent_task_id,
                chain_position=chain_pos,
            )
            pending.append(work)
        
        # Store for transfer
        self._pending_by_email[email] = pending
        
        return pending
    
    def _get_chain_position(self, task: Task, all_tasks: List[Task]) -> int:
        """Get position in continuation chain."""
        if not task.parent_task_id:
            return 0
        
        position = 1
        current_parent = task.parent_task_id
        
        while current_parent:
            # Find parent task
            parent = next(
                (t for t in all_tasks if t.id == current_parent),
                None
            )
            if parent and parent.parent_task_id:
                position += 1
                current_parent = parent.parent_task_id
            else:
                break
        
        return position
    
    def find_healthy_cookie(
        self,
        exclude_email: str,
        min_slots: int = 1,
    ) -> Optional[AccountSession]:
        """Find a healthy cookie for transfer.
        
        Args:
            exclude_email: Email to exclude (expired one)
            min_slots: Minimum available slots required
        
        Returns:
            AccountSession if found, None otherwise
        """
        candidates = []
        
        for email, session in self._sessions.items():
            if email == exclude_email:
                continue
            
            if not session.is_ready:
                continue
            
            if session.available_slots < min_slots:
                continue
            
            candidates.append(session)
        
        if not candidates:
            return None
        
        # Prefer session with most available slots
        candidates.sort(key=lambda s: s.available_slots, reverse=True)
        return candidates[0]
    
    def transfer_work(
        self,
        source_email: str,
        target_session: Optional[AccountSession] = None,
    ) -> TransferResult:
        """Transfer work from expired cookie to healthy one.
        
        Args:
            source_email: Expired cookie email
            target_session: Target session (auto-find if None)
        
        Returns:
            TransferResult
        """
        pending = self._pending_by_email.get(source_email, [])
        
        if not pending:
            return TransferResult(
                success=True,
                source_email=source_email,
                message="No pending work to transfer",
            )
        
        # Find target if not provided
        if not target_session:
            target_session = self.find_healthy_cookie(source_email)
        
        if not target_session:
            return TransferResult(
                success=False,
                source_email=source_email,
                message="No healthy cookie available for transfer",
            )
        
        # Separate by type
        regular_tasks = [w for w in pending if not w.is_continuation]
        continuation_tasks = [w for w in pending if w.is_continuation]
        
        # Sort continuations by chain position (parent first)
        continuation_tasks.sort(key=lambda w: w.chain_position)
        
        # Transfer regular tasks
        transferred = 0
        for work in regular_tasks:
            work.task.assigned_account = target_session.email
            work.task.state = TaskState.READY
            transferred += 1
        
        # Handle continuations specially
        cont_handled = 0
        for work in continuation_tasks:
            result = self._handle_continuation_transfer(
                work,
                target_session,
            )
            if result:
                cont_handled += 1
        
        # Clear pending
        del self._pending_by_email[source_email]
        
        return TransferResult(
            success=True,
            source_email=source_email,
            target_email=target_session.email,
            tasks_transferred=transferred,
            continuations_handled=cont_handled,
            message=f"Transferred {transferred} tasks, {cont_handled} continuations",
        )
    
    def _handle_continuation_transfer(
        self,
        work: PendingWork,
        target_session: AccountSession,
    ) -> bool:
        """Handle special case of continuation transfer.
        
        Continuations need their parent to complete first.
        If parent is also pending, keep them together.
        """
        task = work.task
        
        # If waiting for parent, keep in waiting state
        if task.state == TaskState.WAITING:
            task.assigned_account = target_session.email
            # State stays WAITING - will be resolved when parent completes
            return True
        
        # If ready or running, reassign
        task.assigned_account = target_session.email
        if task.state == TaskState.RUNNING:
            # Reset to ready for re-execution
            task.state = TaskState.READY
        
        return True
    
    def get_pending_work(self, email: str) -> List[PendingWork]:
        """Get pending work for an email."""
        return self._pending_by_email.get(email, [])
    
    def get_all_pending_emails(self) -> List[str]:
        """Get all emails with pending work."""
        return list(self._pending_by_email.keys())
    
    def clear_pending(self, email: str):
        """Clear pending work for an email (e.g., after manual resolution)."""
        if email in self._pending_by_email:
            del self._pending_by_email[email]
