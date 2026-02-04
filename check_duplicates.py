import json
from collections import Counter

def check_data():
    try:
        with open('data.json', 'r') as f:
            data = json.load(f)
        
        candidates = data.get('candidates', [])
        print(f"Total candidates: {len(candidates)}")
        
        names = [c.get('name', 'Unknown') for c in candidates]
        counts = Counter(names)
        
        print("\nCandidate Counts:")
        for name, count in counts.items():
            print(f"- {name}: {count}")
            
        duplicates = [name for name, count in counts.items() if count > 1]
        
        if duplicates:
            print("\nWARNING: Duplicates detected!")
            for name in duplicates:
                print(f"  {name} appears {counts[name]} times.")
        else:
            print("\nNo duplicates found.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_data()
