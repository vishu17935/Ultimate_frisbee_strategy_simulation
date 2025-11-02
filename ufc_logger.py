import os
import json
import time
from datetime import datetime

class UFCLogger:
    def __init__(self):
        self.log_data = {
            'session_start': datetime.now().isoformat(),
            'events': [],
            'user_actions': [],
            'system_events': [],
            'errors': [],
            'playback_events': [],
            'recording_events': []
        }
        self.last_save = time.time()
        self.changed = False
        
    def _add_event(self, category, event_type, details):
        """Add an event to the specified category"""
        if category not in self.log_data:
            self.log_data[category] = []
            
        self.log_data[category].append({
            'timestamp': datetime.now().isoformat(),
            'type': event_type,
            'details': details
        })
        self.changed = True
        
    def log_event(self, event_type, details):
        """Log a general event"""
        self._add_event('events', event_type, details)

    def log_user_action(self, action, details):
        """Log a user action"""
        self._add_event('user_actions', action, details)

    def log_system_event(self, event, details):
        """Log a system event"""
        self._add_event('system_events', event, details)

    def log_error(self, error_type, error_msg, traceback=None):
        """Log an error with optional traceback
        
        Args:
            error_type: Type/category of the error
            error_msg: Error message or description
            traceback: Optional stack trace
        """
        details = {
            'message': error_msg,
            'traceback': traceback
        }
        self._add_event('errors', error_type, details)
        
    def log_playback_event(self, event_type, step, details):
        """Log a playback-related event with step information
        
        Args:
            event_type: Type of playback event
            step: Current playback step
            details: Additional event details
        """
        details = details or {}
        details['step'] = step
        self._add_event('playback_events', event_type, details)
        
    def log_recording_event(self, event, details):
        """Log a recording-related event"""
        self._add_event('recording_events', event, details)
        
    def save_log(self, force=False):
        """Save log data if changed or forced
        
        Returns:
            str: Path to saved log file if successful, otherwise raises an exception
        """
        if not (self.changed or force):
            # If no changes and not forced, create a new save anyway
            force = True
            
        # Create logs directory if it doesn't exist
        log_dir = os.path.join("logs")
        os.makedirs(log_dir, exist_ok=True)
        
        # Save with timestamp
        filename = f"ufc_log_{time.strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(log_dir, filename)
        
        try:
            # Add session end time
            self.log_data['session_end'] = datetime.now().isoformat()
            
            # Add statistics
            self.log_data['stats'] = {
                'total_events': len(self.log_data['events']),
                'total_actions': len(self.log_data['user_actions']),
                'total_system_events': len(self.log_data['system_events']),
                'total_errors': len(self.log_data['errors']),
                'total_playback': len(self.log_data['playback_events']),
                'total_recording': len(self.log_data['recording_events'])
            }
            
            # Save to file
            with open(filepath, 'w') as f:
                json.dump(self.log_data, f, indent=2)
            
            self.changed = False
            self.last_save = time.time()
            print(f"[Log] Saved to {filepath}")
            return filepath
        except Exception as e:
            print(f"[Log] Error saving: {e}")
            return None
