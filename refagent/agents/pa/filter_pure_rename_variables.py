import csv
import re
from pathlib import Path
from github import Github
from datetime import datetime
import os


def is_pure_rename_variable(description):
    """
    Determine if a rename variable refactoring is 'pure' (type not changed)
    
    A pure rename means only the variable name changed, not its type.
    For example:
    - 'Rename Variable highestAccomodationIndex : int to highestAccommodationIndex : int' - Pure
    - 'Rename Variable myInstanceNotifiable : MyInstanceNotifiable to myInstanceListener : MyInstanceListener' - Not pure
    """
    if not description:
        return False
    
    # Try to extract the type pattern: "varname : Type to newvarname : Type"
    pattern = r'(\w+)\s*:\s*(\S+)\s+to\s+(\w+)\s*:\s*(\S+)'
    match = re.search(pattern, description)
    
    if match:
        _, type_before, _, type_after = match.groups()
        return type_before == type_after

def filter_pure_rename_variables(input_csv, output_csv):
    """
    Filter the rename variable refactorings to keep only pure renames
    """
    total_renames = 0
    pure_renames = 0
    
    # Create output directory if it doesn't exist
    output_path = Path(output_csv)
    output_path.parent.mkdir(exist_ok=True)
    
    with open(input_csv, 'r', newline='') as infile, open(output_csv, 'w', newline='') as outfile:
        reader = csv.DictReader(infile)
        writer = csv.DictWriter(outfile, fieldnames=reader.fieldnames + ['is_pure_rename'])
        writer.writeheader()
        
        for row in reader:
            total_renames += 1
            description = row['Description']
            
            # Check if this is a pure rename
            is_pure = is_pure_rename_variable(description)
            
            # Add the is_pure_rename column and write to output
            row['is_pure_rename'] = 'Yes' if is_pure else 'No'
            writer.writerow(row)
            
            if is_pure:
                pure_renames += 1
    
    # Return statistics
    return {
        'total_renames': total_renames,
        'pure_renames': pure_renames,
        'pure_percentage': (pure_renames / total_renames * 100) if total_renames > 0 else 0
    }

def main():
    base_dir = Path.cwd()
    input_file = base_dir / "rename_analysis_results" / "rename_variable_details.csv"
    output_file = base_dir / "rename_analysis_results" / "pure_rename_variables.csv"
    
    print(f"Analyzing Rename Variable refactorings from {input_file}...")
    stats = filter_pure_rename_variables(input_file, output_file)
    
    # Print statistics
    print("\nAnalysis complete!")
    print(f"Total Rename Variable refactorings: {stats['total_renames']}")
    print(f"Pure Rename Variable refactorings: {stats['pure_renames']} ({stats['pure_percentage']:.1f}%)")
    print(f"Results saved to: {output_file}")    

if __name__ == "__main__":
    main() 