import json
import os
import uuid
from typing import List, Dict, Optional

DATA_FILE = "data.json"

def _load_data() -> Dict:
    if not os.path.exists(DATA_FILE):
        return {"positions": [], "candidates": [], "users": []}
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
            # Migration: ensure keys exist
            if "positions" not in data:
                data["positions"] = []
            if "users" not in data:
                data["users"] = []
            return data
    except json.JSONDecodeError:
         return {"positions": [], "candidates": [], "users": []}

def _save_data(data: Dict):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

# ============ Position Functions ============

def save_position(title: str, description: str) -> str:
    """Creates a new position and returns its ID"""
    data = _load_data()
    position_id = str(uuid.uuid4())
    position = {
        "id": position_id,
        "title": title,
        "description": description
    }
    data["positions"].append(position)
    _save_data(data)
    return position_id

def get_all_positions() -> List[Dict]:
    """Returns all positions"""
    data = _load_data()
    return data.get("positions", [])

def get_position(position_id: str) -> Optional[Dict]:
    """Returns a single position by ID"""
    data = _load_data()
    positions = data.get("positions", [])
    return next((p for p in positions if p["id"] == position_id), None)

def update_position(position_id: str, title: str, description: str):
    """Updates an existing position"""
    data = _load_data()
    for p in data["positions"]:
        if p["id"] == position_id:
            p["title"] = title
            p["description"] = description
            break
    _save_data(data)

def delete_position(position_id: str):
    """Deletes a position and all its associated candidates"""
    data = _load_data()
    # Remove position
    data["positions"] = [p for p in data["positions"] if p["id"] != position_id]
    # Cascade delete candidates
    data["candidates"] = [c for c in data["candidates"] if c.get("position_id") != position_id]
    _save_data(data)

def get_candidates_by_position(position_id: str) -> List[Dict]:
    """Returns all candidates for a specific position"""
    data = _load_data()
    return [c for c in data.get("candidates", []) if c.get("position_id") == position_id]

# ============ Legacy Job Description (for migration) ============

def save_job_description(text: str):
    data = _load_data()
    data["job_description_text"] = text
    _save_data(data)

def get_job_description() -> str:
    data = _load_data()
    return data.get("job_description_text", "")

# ============ Candidate Functions ============

def save_candidate(candidate_data: Dict) -> str:
    """Saves a candidate and returns their ID"""
    from datetime import datetime
    
    data = _load_data()
    
    # Generate ID if not present
    if "id" not in candidate_data:
        candidate_data["id"] = str(uuid.uuid4())
    
    # Add created_at timestamp for new candidates
    if "created_at" not in candidate_data:
        candidate_data["created_at"] = datetime.now().isoformat()
    
    # Default status to pending if not set
    if "status" not in candidate_data:
        candidate_data["status"] = "pending"
        
    # Check if candidate already exists (update)
    candidates = data.get("candidates", [])
    existing_index = next((index for (index, d) in enumerate(candidates) if d["id"] == candidate_data["id"]), None)
    
    if existing_index is not None:
        candidates[existing_index] = candidate_data
    else:
        candidates.append(candidate_data)
    
    data["candidates"] = candidates
    _save_data(data)
    return candidate_data["id"]

def get_all_candidates() -> List[Dict]:
    data = _load_data()
    return data.get("candidates", [])

def get_candidate(candidate_id: str) -> Optional[Dict]:
    data = _load_data()
    candidates = data.get("candidates", [])
    return next((c for c in candidates if c["id"] == candidate_id), None)

def delete_candidate(candidate_id: str):
    """Deletes a candidate by ID"""
    data = _load_data()
    candidates = data.get("candidates", [])
    data["candidates"] = [c for c in candidates if c["id"] != candidate_id]
    _save_data(data)

def update_candidate_status(candidate_id: str, status: str):
    """Updates the status of a candidate"""
    data = _load_data()
    candidates = data.get("candidates", [])
    for c in candidates:
        if c["id"] == candidate_id:
            c["status"] = status
            break
    _save_data(data)

def get_overview_stats() -> Dict:
    """Returns aggregated stats for the Overview Dashboard"""
    from datetime import datetime, timedelta
    
    data = _load_data()
    candidates = data.get("candidates", [])
    positions = data.get("positions", [])
    
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Count stats
    total_candidates = len(candidates)
    total_positions = len(positions)
    
    # Status counts
    pending_count = 0
    accepted_count = 0
    rejected_count = 0
    today_applicants = 0
    hires_this_month = 0
    
    for c in candidates:
        status = c.get("status", "pending")
        
        if status == "pending" or status == "":
            pending_count += 1
        elif status == "accepted":
            accepted_count += 1
        elif status == "rejected":
            rejected_count += 1
        
        # Check created_at for today's applicants
        created_at_str = c.get("created_at")
        if created_at_str:
            try:
                created_at = datetime.fromisoformat(created_at_str)
                if created_at >= today_start:
                    today_applicants += 1
                if status == "accepted" and created_at >= month_start:
                    hires_this_month += 1
            except (ValueError, TypeError):
                pass
    
    return {
        "total_candidates": total_candidates,
        "total_positions": total_positions,
        "today_applicants": today_applicants,
        "hires_this_month": hires_this_month,
        "pending_count": pending_count,
        "accepted_count": accepted_count,
        "rejected_count": rejected_count
    }

# ============ User Functions ============

def create_user(username, password, name, email):
    """Creates a new user"""
    from datetime import datetime
    data = _load_data()
    # Check if username exists
    if any(u['username'] == username for u in data.get('users', [])):
        return None
    
    user_id = str(uuid.uuid4())
    user = {
        "id": user_id,
        "username": username,
        "password": password, # In production, hash this!
        "name": name,
        "email": email,
        "created_at": datetime.now().isoformat()
    }
    data["users"].append(user)
    _save_data(data)
    return user_id

def get_user_by_username(username):
    """Returns user by username"""
    data = _load_data()
    return next((u for u in data.get('users', []) if u['username'] == username), None)

def get_user_by_id(user_id):
    """Returns user by ID"""
    data = _load_data()
    return next((u for u in data.get('users', []) if u['id'] == user_id), None)

def get_candidates_by_user(user_id):
    """Returns all candidates/applications for a specific user"""
    data = _load_data()
    return [c for c in data.get('candidates', []) if c.get('user_id') == user_id]
