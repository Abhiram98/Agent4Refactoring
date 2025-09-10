#!/usr/bin/env python3
"""
Calculate Recall@k from the memory database.

This script analyzes the refactoring memory database to compute:
- Recall@k: How many oracle refactorings were found by iteration k
- Precision@k: How many suggested refactorings were valid by iteration k
- Success rate trends across LLM iterations
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import pandas as pd

try:
    import refagent.benchmark.load as bm_load
    import refagent.refactoring_types.refactorings as refactoring_types
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure you're running from the project root directory")
    sys.exit(1)


@dataclass
class MemoryStats:
    """Statistics for a single benchmark at a specific iteration."""
    benchmark_id: int
    llm_iteration: int
    total_suggestions: int
    valid_suggestions: int
    invalid_suggestions: int
    recall: float
    precision: float
    oracle_count: int
    found_oracle_count: int


def connect_to_memory_db(db_path: str) -> sqlite3.Connection:
    """Connect to the memory database."""
    if not Path(db_path).exists():
        raise FileNotFoundError(f"Memory database not found: {db_path}")
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Enable column access by name
    return conn


def load_oracle_data(benchmark_file_path: str) -> Dict[int, List[refactoring_types.RefminerOut]]:
    """Load oracle data from benchmark file."""
    with open(benchmark_file_path) as f:
        benchmark_json = json.load(f)
    
    benchmark: List[bm_load.RenameItem] = bm_load.load_benchmark(benchmark_json, bench_type=bm_load.RenameItem)
    
    oracle_data = {}
    for item in benchmark:
        oracle_data[item.ref_id] = item.refactoring_changes
    
    return oracle_data


def get_benchmark_iterations(conn: sqlite3.Connection, benchmark_id: int, replication_enabled: Optional[bool] = None) -> List[int]:
    """Get all LLM iterations for a benchmark, optionally filtered by replication status."""
    cursor = conn.cursor()
    
    if replication_enabled is not None:
        # Join with memory_sessions to filter by replication_enabled
        cursor.execute("""
            SELECT DISTINCT rs.llm_iteration 
            FROM refactoring_suggestions rs
            JOIN memory_sessions ms ON rs.session_id = ms.session_id
            WHERE rs.benchmark_id = ? AND rs.llm_iteration IS NOT NULL 
                  AND ms.replication_enabled = ?
            ORDER BY rs.llm_iteration
        """, (benchmark_id, replication_enabled))
    else:
        # No replication filter
        cursor.execute("""
            SELECT DISTINCT llm_iteration 
            FROM refactoring_suggestions 
            WHERE benchmark_id = ? AND llm_iteration IS NOT NULL
            ORDER BY llm_iteration
        """, (benchmark_id,))
    
    return [row[0] for row in cursor.fetchall()]


def get_suggestions_up_to_iteration(conn: sqlite3.Connection, 
                                  benchmark_id: int, 
                                  file_path: str,
                                  max_iteration: int,
                                  replication_enabled: Optional[bool] = None) -> List[Dict]:
    """Get all suggestions up to a specific LLM iteration, optionally filtered by replication status."""
    cursor = conn.cursor()
    
    if replication_enabled is not None:
        # Join with memory_sessions to filter by replication_enabled
        cursor.execute("""
            SELECT rs.old_name, rs.new_name, rs.line_num, rs.code_element_type, rs.is_valid, 
                   rs.llm_iteration, rs.feedback, rs.created_at
            FROM refactoring_suggestions rs
            JOIN memory_sessions ms ON rs.session_id = ms.session_id
            WHERE rs.benchmark_id = ? AND rs.file_path = ? AND rs.llm_iteration <= ? 
                  AND ms.replication_enabled = ?
            ORDER BY rs.llm_iteration, rs.created_at
        """, (benchmark_id, file_path, max_iteration, replication_enabled))
    else:
        # No replication filter
        cursor.execute("""
            SELECT old_name, new_name, line_num, code_element_type, is_valid, llm_iteration,
                   feedback, created_at
            FROM refactoring_suggestions 
            WHERE benchmark_id = ? AND file_path = ? AND llm_iteration <= ?
            ORDER BY llm_iteration, created_at
        """, (benchmark_id, file_path, max_iteration))
    
    return [dict(row) for row in cursor.fetchall()]





def calculate_recall_at_k(conn: sqlite3.Connection,
                         benchmark_id: int,
                         oracle_data: Dict[int, List[refactoring_types.RefminerOut]],
                         max_iteration: int,
                         replication_enabled: Optional[bool] = None) -> Optional[MemoryStats]:
    """Calculate Recall@k and Precision@k for a benchmark up to iteration k (cumulative)."""
    
    if benchmark_id not in oracle_data:
        return None
    
    oracle_refactorings = oracle_data[benchmark_id]
    if not oracle_refactorings:
        return None
    
    # Get the file path for this benchmark
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT file_path 
        FROM refactoring_suggestions 
        WHERE benchmark_id = ?
        LIMIT 1
    """, (benchmark_id,))
    
    result = cursor.fetchone()
    if not result:
        return None
    
    file_path = result[0]
    
    # Calculate cumulative recall based on replication mode
    if replication_enabled is None:
        # Without replication: cumulative valid suggestions from iterations 1 to max_iteration
        all_suggestions = get_suggestions_up_to_iteration(conn, benchmark_id, file_path, max_iteration, None)
        
        if not all_suggestions:
            return None
        
        # Filter to iterations 1 to max_iteration
        cumulative_suggestions = [s for s in all_suggestions if s['llm_iteration'] <= max_iteration]
        
        # For precision calculation, use current iteration suggestions
        current_iteration_suggestions = [s for s in all_suggestions if s['llm_iteration'] == max_iteration]
        total_suggestions = len(current_iteration_suggestions)
        valid_suggestions = sum(1 for s in current_iteration_suggestions if s['is_valid'])
        invalid_suggestions = total_suggestions - valid_suggestions
        
        # Count unique valid suggestions across all iterations up to max_iteration
        valid_suggestion_list = [s for s in cumulative_suggestions if s['is_valid']]
        unique_valid_suggestions = []
        seen_suggestions = set()
        
        for suggestion in valid_suggestion_list:
            key = (suggestion['old_name'], suggestion['line_num'])
            if key not in seen_suggestions:
                unique_valid_suggestions.append(suggestion)
                seen_suggestions.add(key)
        
        found_oracle_count = len(unique_valid_suggestions)
        
    else:
        # With replication: cumulative valid suggestions from both non-replication and replication sessions
        # Get all valid suggestions from non-replication sessions up to max_iteration
        non_replication_suggestions = get_suggestions_up_to_iteration(conn, benchmark_id, file_path, max_iteration, False)
        non_replication_valid = [s for s in non_replication_suggestions if s['is_valid']]
        
        # Get all valid suggestions from replication sessions up to max_iteration
        replication_suggestions = get_suggestions_up_to_iteration(conn, benchmark_id, file_path, max_iteration, True)
        replication_valid = [s for s in replication_suggestions if s['is_valid']]
        
        # Combine and deduplicate all valid suggestions
        all_valid_suggestions = non_replication_valid + replication_valid
        unique_valid_suggestions = []
        seen_suggestions = set()
        
        for suggestion in all_valid_suggestions:
            key = (suggestion['old_name'], suggestion['line_num'])
            if key not in seen_suggestions:
                unique_valid_suggestions.append(suggestion)
                seen_suggestions.add(key)
        
        found_oracle_count = len(unique_valid_suggestions)
        
        # For precision calculation, use current iteration suggestions
        current_iteration_suggestions = get_suggestions_up_to_iteration(conn, benchmark_id, file_path, max_iteration, replication_enabled)
        iteration_suggestions = [s for s in current_iteration_suggestions if s['llm_iteration'] == max_iteration]
        
        total_suggestions = len(iteration_suggestions)
        valid_suggestions = sum(1 for s in iteration_suggestions if s['is_valid'])
        invalid_suggestions = total_suggestions - valid_suggestions
    
    oracle_count = len(oracle_refactorings) - 1 # TODO: Make it not hard coded
    recall = found_oracle_count / oracle_count if oracle_count > 0 else 0.0
    precision = valid_suggestions / total_suggestions if total_suggestions > 0 else 0.0
    
    return MemoryStats(
        benchmark_id=benchmark_id,
        llm_iteration=max_iteration,
        total_suggestions=total_suggestions,
        valid_suggestions=valid_suggestions,
        invalid_suggestions=invalid_suggestions,
        recall=recall,
        precision=precision,
        oracle_count=oracle_count,
        found_oracle_count=found_oracle_count
    )


def analyze_memory_database(db_path: str, 
                           benchmark_file_path: str,
                           output_path: Optional[str] = None,
                           replication_enabled: Optional[bool] = None) -> pd.DataFrame:
    """Analyze the memory database and calculate Recall@k for all benchmarks."""
    
    print(f"Connecting to database: {db_path}")
    conn = connect_to_memory_db(db_path)
    
    print(f"Loading oracle data from: {benchmark_file_path}")
    oracle_data = load_oracle_data(benchmark_file_path)
    
    # Get all benchmarks in the database
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT benchmark_id 
        FROM refactoring_suggestions 
        ORDER BY benchmark_id
    """)
    
    benchmark_ids = [row[0] for row in cursor.fetchall()]
    
    if replication_enabled is None:
        print("Calculating Recall@k WITHOUT replication (cumulative across iterations)")
    elif replication_enabled:
        print("Calculating Recall@k WITH replication (cumulative: non-replication + replication across iterations)")
    else:
        print("Calculating Recall@k for all sessions")
    
    print(f"Found {len(benchmark_ids)} benchmarks in database")
    
    results = []
    
    for benchmark_id in benchmark_ids:
        print(f"\nAnalyzing benchmark {benchmark_id}...")
        
        # Get all iterations for this benchmark
        iterations = get_benchmark_iterations(conn, benchmark_id, replication_enabled)
        
        if not iterations:
            print(f"  No iterations found for benchmark {benchmark_id}")
            continue
        
        print(f"  Found {len(iterations)} LLM iterations: {iterations}")
        
        # Calculate Recall@k for iterations 1, 2, and 3 (ensure symmetry)
        for iteration in [1, 2, 3]:
            # Check if this benchmark has data for this iteration
            if iteration in iterations:
                # Calculate recall@k for this iteration
                stats = calculate_recall_at_k(conn, benchmark_id, oracle_data, iteration, replication_enabled)
                
                if stats:
                    results.append({
                        'benchmark_id': stats.benchmark_id,
                        'llm_iteration': stats.llm_iteration,
                        'total_suggestions': stats.total_suggestions,
                        'valid_suggestions': stats.valid_suggestions,
                        'invalid_suggestions': stats.invalid_suggestions,
                        'recall_at_k': stats.recall,
                        'precision_at_k': stats.precision,
                        'oracle_count': stats.oracle_count,
                        'found_oracle_count': stats.found_oracle_count,
                        'success_rate': stats.valid_suggestions / stats.total_suggestions if stats.total_suggestions > 0 else 0.0
                    })
                    
                    print(f"    Iteration {iteration}: Recall@{iteration}={stats.recall:.3f}, "
                          f"Found {stats.found_oracle_count}/{stats.oracle_count} oracles")
                else:
                    print(f"    Iteration {iteration}: No data available")
            else:
                # This benchmark didn't reach this iteration - calculate recall@k up to the last available iteration
                last_available_iteration = max(iterations) if iterations else 0
                if last_available_iteration > 0:
                    stats = calculate_recall_at_k(conn, benchmark_id, oracle_data, last_available_iteration, replication_enabled)
                    
                    if stats:
                        results.append({
                            'benchmark_id': stats.benchmark_id,
                            'llm_iteration': iteration,  # Use the requested iteration number
                            'total_suggestions': 0,  # No new suggestions in this iteration
                            'valid_suggestions': 0,
                            'invalid_suggestions': 0,
                            'recall_at_k': stats.recall,  # Same recall as last available iteration
                            'precision_at_k': 0.0,  # No precision since no new suggestions
                            'oracle_count': stats.oracle_count,
                            'found_oracle_count': stats.found_oracle_count,
                            'success_rate': 0.0
                        })
                        
                        print(f"    Iteration {iteration}: Recall@{iteration}={stats.recall:.3f}, "
                              f"Found {stats.found_oracle_count}/{stats.oracle_count} oracles")
                    else:
                        print(f"    Iteration {iteration}: No data available")
                else:
                    print(f"    Iteration {iteration}: No data available")
    
    conn.close()
    
    # Create DataFrame
    df = pd.DataFrame(results)
    
    if not df.empty:
        # Save results
        if output_path:
            df.to_csv(output_path, index=False)
            print(f"\nResults saved to: {output_path}")
    
    return df


def main():
    parser = argparse.ArgumentParser(description='Calculate Recall@k from memory database')
    parser.add_argument('memory_db_path', type=str, 
                       help='Path to the memory database file (.db)')
    parser.add_argument('--benchmark_file_path', type=str, 
                       help='Path to benchmark JSON file',
                       default='data/ref_miner/benchmark_full.json')
    parser.add_argument('--output', type=str,
                       help='Output CSV file path (optional)')
    parser.add_argument('--benchmark_id', type=int,
                       help='Analyze specific benchmark ID only (optional)')
    parser.add_argument('--replication_mode', type=str, choices=['without', 'with', 'all'],
                       default='all', help='Recall calculation mode: without replication, with replication (cumulative), or all (default)')
    
    args = parser.parse_args()
    
    # Validate inputs
    if not Path(args.memory_db_path).exists():
        print(f"Error: Memory database not found: {args.memory_db_path}")
        return 1
    
    if not Path(args.benchmark_file_path).exists():
        print(f"Error: Benchmark file not found: {args.benchmark_file_path}")
        return 1
    
    # Parse replication mode
    replication_mode = None
    if args.replication_mode == 'without':
        replication_mode = None  # Without replication
    elif args.replication_mode == 'with':
        replication_mode = True   # With replication (cumulative)
    # 'all' means analyze both modes
    
    # Analyze database
    try:
        if args.replication_mode == 'all':
            # Analyze both modes
            print("\n=== ANALYZING WITHOUT REPLICATION ===")
            df_without = analyze_memory_database(
                db_path=args.memory_db_path,
                benchmark_file_path=args.benchmark_file_path,
                output_path=args.output.replace('.csv', '_without_replication.csv') if args.output else None,
                replication_enabled=None
            )
            
            print("\n=== ANALYZING WITH REPLICATION (CUMULATIVE) ===")
            df_with = analyze_memory_database(
                db_path=args.memory_db_path,
                benchmark_file_path=args.benchmark_file_path,
                output_path=args.output.replace('.csv', '_with_replication.csv') if args.output else None,
                replication_enabled=True
            )
            
            # Combine results
            if not df_without.empty:
                df_without['mode'] = 'without_replication'
            if not df_with.empty:
                df_with['mode'] = 'with_replication'
            
            df = pd.concat([df_without, df_with], ignore_index=True)
            
        else:
            # Analyze single mode
            df = analyze_memory_database(
                db_path=args.memory_db_path,
                benchmark_file_path=args.benchmark_file_path,
                output_path=args.output,
                replication_enabled=replication_mode
            )
        
        if df.empty:
            print("No data found in memory database!")
            return 1
        
        return 0
        
    except Exception as e:
        print(f"Error analyzing database: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())