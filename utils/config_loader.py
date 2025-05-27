import os
from dotenv import load_dotenv

def load_config():
    """
    Memuat konfigurasi dari file .env
    """
    # Pastikan .env dimuat
    load_dotenv()
    
    # Konfigurasi ESP32-CAM
    config = {
        "esp32": {
            "ip": os.environ.get('ESP32_IP'),
            "stream_port": os.environ.get('ESP32_STREAM_PORT'),
            "capture_path": os.environ.get('ESP32_CAPTURE_PATH')
        },
        "app": {
            "debug": os.environ.get('DEBUG', 'True').lower() == 'true',
            "process_timeout": int(os.environ.get('PROCESS_TIMEOUT', '5')),
            "max_capture_age_days": int(os.environ.get('MAX_CAPTURE_AGE_DAYS', '7'))
        }
    }
    
    return config 