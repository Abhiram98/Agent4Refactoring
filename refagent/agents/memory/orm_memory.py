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
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def start_session(self, benchmark_id: int, agent_run_id: Optional[str] = None) -> str:
        """Start a new memory session."""
        session_id = f"session_{benchmark_id}_{uuid.uuid4().hex[:8]}"
        self.current_session_id = session_id

        with self.get_session() as db:
            memory_session = MemorySession(
                session_id=session_id,
                benchmark_id=benchmark_id,
                agent_run_id=agent_run_id,
                started_at=datetime.now(timezone.utc)
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
                context_data=json.dumps(context_data) if context_data else None
            )

            try:
                db.add(suggestion)
                db.commit()
                db.refresh(suggestion)
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
                    # No need to refresh - we already have the updated object
                    return existing

                raise

    def get_memory_feedback(self,
                            benchmark_id: int,
                            file_path: str,
                            limit: int = 10) -> str:
        """Generate memory-based feedback for LLM."""

        with self.get_session() as db:
            feedback_parts = []

            # Get recent invalid suggestions for this benchmark and file
            recent_invalid = db.query(RefactoringSuggestion).filter(
                and_(
                    RefactoringSuggestion.benchmark_id == benchmark_id,
                    RefactoringSuggestion.file_path == file_path,
                    RefactoringSuggestion.is_valid == False
                )
            ).order_by(desc(RefactoringSuggestion.created_at)).limit(limit // 2).all()

            if recent_invalid:
                invalid_names = [f"'{s.old_name}' → '{s.new_name}'" for s in recent_invalid]
                feedback_parts.append(
                    f"MEMORY: Previously FAILED suggestions to AVOID: {', '.join(invalid_names)}"
                )

                # Include specific failure reasons
                reasons = [s.critique_reason for s in recent_invalid if s.critique_reason][:3]
                if reasons:
                    feedback_parts.append(f"Failure reasons: {'; '.join(reasons)}")

            # Get recent valid suggestions for this benchmark and file
            recent_valid = db.query(RefactoringSuggestion).filter(
                and_(
                    RefactoringSuggestion.benchmark_id == benchmark_id,
                    RefactoringSuggestion.file_path == file_path,
                    RefactoringSuggestion.is_valid == True
                )
            ).order_by(desc(RefactoringSuggestion.created_at)).limit(limit // 2).all()

            if recent_valid:
                valid_names = [f"'{s.old_name}' → '{s.new_name}'" for s in recent_valid]
                feedback_parts.append(
                    f"MEMORY: Previously SUCCESSFUL patterns: {', '.join(valid_names)}"
                )

            # Get cross-benchmark successful patterns (same file type)
            file_extension = Path(file_path).suffix
            if file_extension:
                cross_benchmark_patterns = db.query(
                    RefactoringSuggestion.old_name,
                    RefactoringSuggestion.new_name,
                    func.count(RefactoringSuggestion.id).label('frequency'),
                    func.avg(func.cast(RefactoringSuggestion.is_valid, Float)).label('success_rate')
                ).filter(
                    and_(
                        RefactoringSuggestion.file_path.like(f'%{file_extension}'),
                        RefactoringSuggestion.benchmark_id != benchmark_id,  # Different benchmarks
                        RefactoringSuggestion.is_valid == True
                    )
                ).group_by(
                    RefactoringSuggestion.old_name,
                    RefactoringSuggestion.new_name
                ).having(
                    func.count(RefactoringSuggestion.id) >= 2  # Seen at least twice
                ).order_by(
                    desc('success_rate'),
                    desc('frequency')
                ).limit(3).all()

                if cross_benchmark_patterns:
                    pattern_strs = [
                        f"'{p.old_name}' → '{p.new_name}' ({p.frequency}x, {p.success_rate:.0%})"
                        for p in cross_benchmark_patterns
                    ]
                    feedback_parts.append(f"CROSS-BENCHMARK: {', '.join(pattern_strs)}")

            return " | ".join(feedback_parts) if feedback_parts else ""

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