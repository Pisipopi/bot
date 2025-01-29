import json
from datetime import datetime
import logging
from typing import Dict, List

def setup_logging():
    """Configure logging settings"""
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )

def log_command(user_id: int, username: str, command: str, message: str):
    """Log bot commands to JSON file"""
    try:
        try:
            with open('bot_logs.json', 'r') as f:
                logs = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logs = []

        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'username': username,
            'command': command,
            'message': message
        }
        
        logs.append(log_entry)

        with open('bot_logs.json', 'w') as f:
            json.dump(logs, f, indent=2)
            
    except Exception as e:
        logging.error(f"Error logging command: {e}")

def get_logs() -> List[Dict]:
    """Retrieve logs from JSON file"""
    try:
        with open('bot_logs.json', 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []
