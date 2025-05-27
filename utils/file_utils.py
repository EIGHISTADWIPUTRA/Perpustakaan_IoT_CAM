import os
import time
from datetime import datetime

def ensure_directories(dirs):
    """
    Memastikan direktori yang diperlukan tersedia
    """
    for directory in dirs:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"Folder {directory} dibuat")

def save_image(image_data, folder, filename=None):
    """
    Menyimpan gambar ke folder tertentu
    """
    if not os.path.exists(folder):
        os.makedirs(folder)
    
    if filename is None:
        # Buat nama file dengan timestamp jika tidak ada nama file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}.jpg"
    
    filepath = os.path.join(folder, filename)
    
    try:
        with open(filepath, 'wb') as f:
            f.write(image_data)
        print(f"Gambar tersimpan: {filepath}")
        return filepath
    except Exception as e:
        print(f"Error menyimpan gambar: {str(e)}")
        return None

def clean_old_files(directory, max_age_days=7):
    """
    Membersihkan file lama dalam direktori
    """
    try:
        if not os.path.exists(directory):
            return 0
            
        now = time.time()
        count = 0
        
        for filename in os.listdir(directory):
            filepath = os.path.join(directory, filename)
            if os.path.isfile(filepath) and now - os.path.getmtime(filepath) > max_age_days * 24 * 3600:
                os.remove(filepath)
                count += 1
                
        if count > 0:
            print(f"Membersihkan {count} file lama dari {directory}")
        return count
    except Exception as e:
        print(f"Error saat membersihkan file lama: {str(e)}")
        return 0 