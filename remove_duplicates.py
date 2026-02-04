import json
from collections import OrderedDict

def remove_duplicates():
    input_file = 'data.json'
    try:
        with open(input_file, 'r') as f:
            data = json.load(f)
        
        candidates = data.get('candidates', [])
        print(f"Initial count: {len(candidates)}")
        
        # Use a dict to keep only the last occurrence of each name
        # This effectively dedupes by name, keeping the most recent (appended last)
        unique_candidates_map = OrderedDict()
        for c in candidates:
            name = c.get('name')
            if name:
                unique_candidates_map[name] = c
        
        unique_candidates = list(unique_candidates_map.values())
        print(f"Final count: {len(unique_candidates)}")
        
        data['candidates'] = unique_candidates
        
        with open(input_file, 'w') as f:
            json.dump(data, f, indent=2)
            
        print("Duplicates removed successfully.")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    remove_duplicates()
