"""
ORM-based memory manager for refactoring suggestions.
"""
from sqlalchemy import create_engine, and_, or_, desc, func, text, Integer, Float
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import uuid
from contextlib import contextmanager

from .memory_models import Base, RefactoringSuggestion, MemorySession


class ORMRefactoringMemory:
    """ORM-based persistent memory for refactoring suggestions."""

    def __init__(self, database_url: str = "sqlite:///refactoring_memory.db"):
        """
        Initialize the ORM memory manager.

        Args:
            database_url: SQLAlchemy database URL
                - SQLite: "sqlite:///memory.db"
                - PostgreSQL: "postgresql://user:pass@localhost/dbname"
                - MySQL: "mysql://user:pass@localhost/dbname"
        """
        self.engine = create_engine(
            database_url,
            echo=False,  # Set to True for SQL debugging
            pool_pre_ping=True  # Verify connections before use
        )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.current_session_id = None

        # Create tables if they don't exist
        self.create_tables()

    def create_tables(self):
        """Create all tables if they don't exist."""
        Base.metadata.create_all(bind=self.engine)

    @contextmanager
    def get_session(self) -> Session:
        """Context manager for database sessions."""
        session = self.SessionLocal()
        try:
            yield session
            # Don't auto-commit - let methods handle their own commits
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def start_session(self, benchmark_id: int, agent_run_id: Optional[str] = None, replication_enabled: Optional[bool] = None) -> str:
        """Start a new memory session."""
        session_id = f"session_{benchmark_id}_{uuid.uuid4().hex[:8]}"
        self.current_session_id = session_id

        with self.get_session() as db:
            memory_session = MemorySession(
                session_id=session_id,
                benchmark_id=benchmark_id,
                agent_run_id=agent_run_id,
                started_at=datetime.now(timezone.utc),
                replication_enabled=replication_enabled
            )
            db.add(memory_session)
            db.commit()

        return session_id

    def end_session(self, session_id: Optional[str] = None):
        """End a memory session and update statistics."""
        if session_id is None:
            session_id = self.current_session_id

        if session_id:
            with self.get_session() as db:
                session_obj = db.query(MemorySession).filter(
                    MemorySession.session_id == session_id
                ).first()

                if session_obj:
                    # Calculate session statistics
                    stats = db.query(
                        func.count(RefactoringSuggestion.id).label('total'),
                        func.sum(func.cast(RefactoringSuggestion.is_valid, Integer)).label('valid')
                    ).filter(RefactoringSuggestion.session_id == session_id).first()

                    session_obj.ended_at = datetime.now(timezone.utc)
                    session_obj.total_suggestions = stats.total or 0
                    session_obj.valid_suggestions = stats.valid or 0
                    session_obj.invalid_suggestions = (stats.total or 0) - (stats.valid or 0)

                    db.commit()

    def add_suggestion(self,
                       benchmark_id: int,
                       file_path: str,
                       old_name: str,
                       new_name: str,
                       line_num: int,
                       code_element_type: str,
                       is_valid: bool,
                       feedback: str = "",
                       critique_reason: str = "",
                       confidence_score: Optional[float] = None,
                       agent_iteration: Optional[int] = None,
                       llm_iteration: Optional[int] = None,
                       context_data: Optional[Dict[str, Any]] = None) -> RefactoringSuggestion:
        """Add a new suggestion to memory."""

        with self.get_session() as db:
            suggestion = RefactoringSuggestion(
                benchmark_id=benchmark_id,
                file_path=file_path,
                old_name=old_name,
                new_name=new_name,
                line_num=line_num,
                code_element_type=code_element_type,
                is_valid=is_valid,
                feedback=feedback,
                critique_reason=critique_reason,
                confidence_score=confidence_score,
                session_id=self.current_session_id,
                agent_iteration=agent_iteration,
                llm_iteration=llm_iteration,
                context_data=json.dumps(context_data) if context_data else None
            )

            try:
                db.add(suggestion)
                db.commit()
                # Detach from session to prevent lazy loading issues
                db.expunge(suggestion)
                return suggestion

            except IntegrityError:
                # Suggestion already exists, update it
                db.rollback()
                existing = db.query(RefactoringSuggestion).filter(
                    and_(
                        RefactoringSuggestion.benchmark_id == benchmark_id,
                        RefactoringSuggestion.file_path == file_path,
                        RefactoringSuggestion.old_name == old_name,
                        RefactoringSuggestion.new_name == new_name,
                        RefactoringSuggestion.line_num == line_num
                    )
                ).first()

                if existing:
                    existing.is_valid = is_valid
                    existing.feedback = feedback
                    existing.critique_reason = critique_reason
                    existing.confidence_score = confidence_score
                    existing.retry_count += 1
                    existing.updated_at = datetime.now(timezone.utc)
                    if context_data:
                        existing.context_data = json.dumps(context_data)

                    db.commit()
                    # Detach from session to prevent lazy loading issues
                    db.expunge(existing)
                    return existing

                raise

    def increment_llm_iteration(self, session_id: Optional[str] = None):
        """Increment the LLM iteration counter for the current session."""
        if session_id is None:
            session_id = self.current_session_id

        if session_id:
            with self.get_session() as db:
                session_obj = db.query(MemorySession).filter(
                    MemorySession.session_id == session_id
                ).first()

                if session_obj:
                    session_obj.total_llm_iterations = (session_obj.total_llm_iterations or 0) + 1
                    db.commit()
                    return session_obj.total_llm_iterations
        return 0

    def get_current_llm_iteration(self, session_id: Optional[str] = None) -> int:
        """Get the current LLM iteration number for the session."""
        if session_id is None:
            session_id = self.current_session_id

        if session_id:
            with self.get_session() as db:
                session_obj = db.query(MemorySession).filter(
                    MemorySession.session_id == session_id
                ).first()

                if session_obj:
                    return session_obj.total_llm_iterations or 0
        return 0

    def get_memory_feedback(self,
                            benchmark_id: int,
                            file_path: Optional[str] = None,
                            limit: int = 10) -> str:
        """Generate concise, actionable memory-based feedback for LLM.
        
        Args:
            benchmark_id: Current benchmark ID
            file_path: Specific file path, or None for cross-file feedback
            limit: Maximum number of suggestions to consider
        """

        with self.get_session() as db:
            feedback_parts = []

            # Build base query filter
            base_filter = [RefactoringSuggestion.benchmark_id == benchmark_id]
            if file_path is not None:
                base_filter.append(RefactoringSuggestion.file_path == file_path)

            # Get recent invalid suggestions - be very specific about what to avoid
            recent_invalid = db.query(RefactoringSuggestion).filter(
                and_(
                    *base_filter,
                    RefactoringSuggestion.is_valid == False
                )
            ).order_by(desc(RefactoringSuggestion.created_at)).limit(limit).all()

            if recent_invalid:
                if file_path is not None:
                    # File-specific feedback: include line numbers
                    failed_lines = list(set([s.line_num for s in recent_invalid if s.line_num]))
                    failed_patterns = list(set([f"{s.old_name}→{s.new_name}" for s in recent_invalid]))
                    
                    if failed_lines:
                        feedback_parts.append(f"AVOID lines: {failed_lines}")
                    # if failed_patterns:
                    #     feedback_parts.append(f"AVOID patterns: {failed_patterns}")
                # else:
                #     # Cross-file feedback: focus on patterns, not specific lines
                #     failed_patterns = list(set([f"{s.old_name}→{s.new_name}" for s in recent_invalid]))
                #     if failed_patterns:
                #         feedback_parts.append(f"AVOID patterns: {failed_patterns}")

            # Get recent valid suggestions - show what worked
            recent_valid = db.query(RefactoringSuggestion).filter(
                and_(
                    *base_filter,
                    RefactoringSuggestion.is_valid == True
                )
            ).order_by(desc(RefactoringSuggestion.created_at)).limit(limit).all()

            if recent_valid:
                if file_path is not None:
                    # File-specific: show completed lines
                    successful_lines = [s.line_num for s in recent_valid if s.line_num]
                    if successful_lines:
                        feedback_parts.append(f"COMPLETED lines: {successful_lines}")
                
                # Always show successful patterns (both file-specific and cross-file)
                successful_patterns = list(set([f"{s.old_name}→{s.new_name}" for s in recent_valid]))
                if successful_patterns:
                    feedback_parts.append(f"Example SUCCESS patterns: {successful_patterns}")

            # Keep it short and actionable
            result = " | ".join(feedback_parts) if feedback_parts else ""
            scope = "FILE" if file_path else "BENCHMARK"
            return f"MEMORY ({scope}): {result}" if result else ""

    def is_suggestion_previously_invalid(self,
                                         benchmark_id: int,
                                         file_path: str,
                                         old_name: str,
                                         new_name: str,
                                         line_num: Optional[int] = None) -> bool:
        """Check if suggestion was previously invalid."""

        with self.get_session() as db:
            query = db.query(RefactoringSuggestion).filter(
                and_(
                    RefactoringSuggestion.benchmark_id == benchmark_id,
                    RefactoringSuggestion.file_path == file_path,
                    RefactoringSuggestion.old_name == old_name,
                    RefactoringSuggestion.new_name == new_name,
                    RefactoringSuggestion.is_valid == False
                )
            )

            if line_num is not None:
                query = query.filter(RefactoringSuggestion.line_num == line_num)

            return query.first() is not None

    def get_memory_stats(self, benchmark_id: int, file_path: Optional[str] = None) -> Dict[str, Any]:
        """Get memory statistics."""

        with self.get_session() as db:
            query = db.query(RefactoringSuggestion).filter(
                RefactoringSuggestion.benchmark_id == benchmark_id
            )

            if file_path:
                query = query.filter(RefactoringSuggestion.file_path == file_path)

            stats = query.with_entities(
                func.count(RefactoringSuggestion.id).label('total'),
                func.sum(func.cast(RefactoringSuggestion.is_valid, Integer)).label('valid'),
                func.avg(RefactoringSuggestion.confidence_score).label('avg_confidence')
            ).first()

            total = stats.total or 0
            valid = stats.valid or 0

            return {
                "total_attempts": total,
                "valid_count": valid,
                "invalid_count": total - valid,
                "success_rate": (valid / total * 100) if total > 0 else 0,
                "average_confidence": round(stats.avg_confidence or 0, 2)
            }

    def get_suggestions_by_benchmark(self, benchmark_id: int) -> List[RefactoringSuggestion]:
        """Get all suggestions for a specific benchmark."""

        with self.get_session() as db:
            return db.query(RefactoringSuggestion).filter(
                RefactoringSuggestion.benchmark_id == benchmark_id
            ).order_by(RefactoringSuggestion.created_at).all()

    def clear_benchmark_memory(self, benchmark_id: int):
        """Clear all memory for a specific benchmark."""

        with self.get_session() as db:
            db.query(RefactoringSuggestion).filter(
                RefactoringSuggestion.benchmark_id == benchmark_id
            ).delete()
            db.commit()

    def get_successful_renames_for_file(self, file_path: str, benchmark_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get successful rename suggestions for a specific file."""
        with self.get_session() as db:
            query = db.query(RefactoringSuggestion).filter(
                and_(
                    RefactoringSuggestion.file_path == file_path,
                    RefactoringSuggestion.is_valid == True
                )
            )
            
            if benchmark_id:
                query = query.filter(RefactoringSuggestion.benchmark_id == benchmark_id)
            elif self.current_session_id:
                # Use current session's benchmark if available
                session_info = db.query(MemorySession).filter(
                    MemorySession.session_id == self.current_session_id
                ).first()
                if session_info:
                    query = query.filter(RefactoringSuggestion.benchmark_id == session_info.benchmark_id)
            
            suggestions = query.order_by(RefactoringSuggestion.created_at.desc()).all()
            
            return [
                {
                    'old_name': s.old_name,
                    'new_name': s.new_name,
                    'line_num': s.line_num,
                    'code_element_type': s.code_element_type,
                    'confidence_score': s.confidence_score,
                    'created_at': s.created_at
                }
                for s in suggestions
            ]

    def get_most_successful_patterns(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get the most successful transformation patterns across all benchmarks."""

        with self.get_session() as db:
            patterns = db.query(
                RefactoringSuggestion.old_name,
                RefactoringSuggestion.new_name,
                RefactoringSuggestion.code_element_type,
                func.count(RefactoringSuggestion.id).label('frequency'),
                func.avg(func.cast(RefactoringSuggestion.is_valid, Float)).label('success_rate')
            ).filter(
                RefactoringSuggestion.is_valid == True
            ).group_by(
                RefactoringSuggestion.old_name,
                RefactoringSuggestion.new_name,
                RefactoringSuggestion.code_element_type
            ).having(
                func.count(RefactoringSuggestion.id) >= 2  # Seen at least twice
            ).order_by(
                desc('success_rate'),
                desc('frequency')
            ).limit(limit).all()

            return [
                {
                    'old_name': p.old_name,
                    'new_name': p.new_name,
                    'code_element_type': p.code_element_type,
                    'frequency': p.frequency,
                    'success_rate': round(p.success_rate * 100, 1)
                }
                for p in patterns
            ]