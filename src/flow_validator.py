import time
from datetime import datetime

class FlowValidator:
    def __init__(self, max_flow_rate=100.0, min_time_diff=1):
        self.max_flow_rate = max_flow_rate
        self.min_time_diff = min_time_diff
    
    def validate_and_correct(self, current_reading, last_reading, 
                            last_timestamp, current_timestamp):
        
        if last_reading is None or last_timestamp is None:
            return current_reading, 0.0
        
        time_diff = (current_timestamp - last_timestamp) / 60.0
        
        if time_diff < self.min_time_diff:
            time_diff = self.min_time_diff
        
        current_int = int(''.join(str(current_reading).split('.')))
        last_int = int(''.join(str(last_reading).split('.')))
        
        corrected_val = self._hamming_correction(
            current_int, last_int, time_diff
        )
        
        corrected_reading = corrected_val / 10.0
        
        flow_rate = (corrected_reading - last_reading) / time_diff
        
        if flow_rate < 0 or flow_rate > self.max_flow_rate:
            return None, 0.0
        
        return corrected_reading, round(flow_rate, 2)
    
    def _hamming_correction(self, current, last, time_diff):
        min_distance = 10
        corrected = current
        
        search_range = int(1 * time_diff) + 10
        
        for candidate in range(last, last + search_range + 1):
            current_str = str(current).zfill(10)
            candidate_str = str(candidate).zfill(10)
            
            distance = sum(c1 != c2 for c1, c2 in zip(current_str, candidate_str))
            
            if distance < min_distance:
                corrected = candidate
                min_distance = distance
        
        return corrected
