import json
import os
import numpy as np
from datetime import datetime

class StateManager:
    def __init__(self, state_file='meter_state.json'):
        self.state_file = state_file
        self.state = self._load_state()
    
    def _load_state(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        
        return {
            'last_reading': None,
            'last_timestamp': None,
            'last_flow_rate': 0.0,
            'transform_matrix': None
        }
    
    def save_state(self, reading=None, timestamp=None, flow_rate=None, matrix=None):
        if reading is not None:
            self.state['last_reading'] = reading
        
        if timestamp is not None:
            self.state['last_timestamp'] = timestamp
        
        if flow_rate is not None:
            self.state['last_flow_rate'] = flow_rate
        
        if matrix is not None:
            self.state['transform_matrix'] = matrix.tolist()
        
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f)
        except Exception as e:
            self._log_error(f"State save error: {str(e)}")
    
    def get_last_reading(self):
        return self.state.get('last_reading')
    
    def get_last_timestamp(self):
        return self.state.get('last_timestamp')
    
    def get_last_flow_rate(self):
        return self.state.get('last_flow_rate', 0.0)
    
    def get_transform_matrix(self):
        matrix_list = self.state.get('transform_matrix')
        if matrix_list:
            return np.array(matrix_list)
        return None
    
    def _log_error(self, message):
        try:
            with open('error.log', 'a') as f:
                f.write(f"{datetime.now()} - {message}\n")
        except:
            pass
