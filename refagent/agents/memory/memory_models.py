from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text, DateTime, Float, UniqueConstraint, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
import json

Base = declarative_base()


class RefactoringSuggestion(Base):
    """ORM model for refactoring suggestions with memory."""

    __tablename__ = 'refactoring_suggestions'

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Core identifiers
    benchmark_id = Column(Integer, nullable=False, index=True)
    file_path = Column(String(500), nullable=False, index=True)
    old_name = Column(String(200), nullable=False)
    new_name = Column(String(200), nullable=False)
    snippet = Column(String, nullable=False)
    line_num = Column(Integer, nullable=True)
    code_element_type = Column(String(50), nullable=True)

    # Validation results
    is_valid = Column(Boolean, nullable=False, index=True)
    feedback = Column(Text, nullable=True)
    critique_reason = Column(Text, nullable=True)
    confidence_score = Column(Float, nullable=True)  # 0.0-1.0

    # Context metadata
    session_id = Column(String(100), nullable=True, index=True)
    agent_iteration = Column(Integer, nullable=True)
    retry_count = Column(Integer, default=0)
    llm_iteration = Column(Integer, nullable=True)  # Track which LLM call iteration this was

    # Additional context (JSON field for flexibility)
    context_data = Column(Text, nullable=True)  # JSON string

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Composite unique constraint to prevent duplicates
    __table_args__ = (
        UniqueConstraint('benchmark_id', 'file_path', 'old_name', 'new_name', 'line_num',
                         name='uq_suggestion_identity'),
        Index('idx_benchmark_file', 'benchmark_id', 'file_path'),
        Index('idx_validity_time', 'is_valid', 'created_at'),
        Index('idx_session_time', 'session_id', 'created_at'),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'benchmark_id': self.benchmark_id,
            'file_path': self.file_path,
            'old_name': self.old_name,
            'new_name': self.new_name,
            'line_num': self.line_num,
            'code_element_type': self.code_element_type,
            'is_valid': self.is_valid,
            'feedback': self.feedback,
            'critique_reason': self.critique_reason,
            'confidence_score': self.confidence_score,
            'session_id': self.session_id,
            'agent_iteration': self.agent_iteration,
            'retry_count': self.retry_count,
            'llm_iteration': self.llm_iteration,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'context_data': json.loads(self.context_data) if self.context_data else None
        }

    def get_summary(self, add_context=False) -> str:
        summary = f"`{self.old_name}` -> `{self.new_name}` on line {self.line_num}."
        if add_context:
            summary += f"\nContext: {self.snippet}"
        return summary

    def __str__(self):
        return f"{self.old_name} -> {self.new_name} on line {self.line_num}"

    def __eq__(self, other):
        if isinstance(other, RefactoringSuggestion):
            return (self.old_name == other.old_name
                    and self.new_name == other.new_name
                    and self.line_num == other.line_num
                    and self.file_path == other.file_path)
        return False


class MemorySession(Base):
    """Track memory sessions for debugging and analysis."""

    __tablename__ = 'memory_sessions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), nullable=False, unique=True, index=True)
    benchmark_id = Column(Integer, nullable=False)
    agent_run_id = Column(String(100), nullable=True)

    # Session metadata
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)
    replication_enabled = Column(Boolean, nullable=True)  # Track if replication was on/off

    # Statistics
    total_suggestions = Column(Integer, default=0)
    valid_suggestions = Column(Integer, default=0)
    invalid_suggestions = Column(Integer, default=0)
    total_llm_iterations = Column(Integer, default=0)  # Track total LLM iterations in this session

    # Additional session info
    session_metadata = Column(Text, nullable=True)  # JSON


class ExamplePair(Base):
    __tablename__ = "example_pairs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    old_name = Column(String, nullable=False)
    new_name = Column(String, nullable=False)
    is_positive = Column(Boolean, nullable=False)  # True = positive example, False = negative
    created_at = Column(DateTime, default=datetime.utcnow)


class RenameScope(Base):
    __tablename__ = 'rename_scopes'
    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    scope = Column(String, nullable=False)

