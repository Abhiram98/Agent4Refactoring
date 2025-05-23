import json
import os
import sys

def get_project_root():
    current_file = os.path.abspath(__file__)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
    return project_root

def filter_data_by_id_range(input_file, output_file, min_id, max_id):
    try:
        if not os.path.exists(input_file):
            print(f"Error: Input file not found: {input_file}")
            return False

        with open(input_file, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                print(f"Error: Invalid JSON format in input file: {e}")
                return False
        
        if not isinstance(data, list):
            print("Error: Input JSON must be a list of objects")
            return False

        filtered_data = [item for item in data if min_id <= item.get('id', 0) <= max_id]
        
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(filtered_data, f, indent=4)
        
        print(f"Successfully filtered {len(filtered_data)} items out of {len(data)} total items")
        return True

    except Exception as e:
        print(f"Error: An unexpected error occurred: {e}")
        return False

if __name__ == "__main__":
    # Get project root
    project_root = get_project_root()
    print(f"Project root directory: {project_root}")
    
    input_file = os.path.join(project_root, "data", "renas", "ratpack.json")
    output_file = os.path.join(project_root, "data", "renas", "ratpack-600-650-temp.json")
    
    print(f"Input file: {input_file}")
    print(f"Output file: {output_file}")
    
    success = filter_data_by_id_range(input_file, output_file, 600, 650)
    sys.exit(0 if success else 1)