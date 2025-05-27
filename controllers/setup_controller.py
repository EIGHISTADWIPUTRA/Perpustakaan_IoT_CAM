from flask import Blueprint, render_template, request, redirect, url_for
from models.esp32_manager import ESP32Manager
import os

# Inisialisasi Blueprint
setup_bp = Blueprint('setup', __name__)

# Inisialisasi ESP32Manager
esp32_manager = ESP32Manager()

@setup_bp.route('/setup', methods=['GET', 'POST'])
def setup_page():
    """
    Route untuk halaman pengaturan ESP32-CAM
    """
    if request.method == 'POST':
        # Ambil nilai dari form
        esp32_ip = request.form.get('esp32_ip')
        stream_port = request.form.get('stream_port')
        capture_path = request.form.get('capture_path')
        
        # Validasi input
        if not esp32_ip:
            return render_template('setup.html', error="IP ESP32-CAM tidak boleh kosong", config=esp32_manager.get_config())
        
        # Update konfigurasi ESP32
        new_config = {
            "ip": esp32_ip,
            "stream_port": stream_port,
            "capture_path": capture_path
        }
        
        # Update environment variables
        update_env_file(new_config)
        
        # Update ESP32 manager
        esp32_manager.update_config(new_config)
        
        # Redirect ke halaman utama
        return redirect(url_for('main.index'))
    
    # Untuk metode GET, tampilkan form dengan konfigurasi saat ini
    return render_template('setup.html', config=esp32_manager.get_config())

def update_env_file(config):
    """
    Update file .env dengan konfigurasi baru
    """
    if os.path.exists('.env'):
        # Baca file .env
        with open('.env', 'r') as f:
            lines = f.readlines()
        
        # Update konfigurasi
        new_lines = []
        updated = {
            'ESP32_IP': False,
            'ESP32_STREAM_PORT': False,
            'ESP32_CAPTURE_PATH': False
        }
        
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                key, value = line.split('=', 1)
                key = key.strip()
                
                if key == 'ESP32_IP':
                    new_lines.append(f"ESP32_IP={config['ip']}")
                    updated['ESP32_IP'] = True
                elif key == 'ESP32_STREAM_PORT':
                    new_lines.append(f"ESP32_STREAM_PORT={config['stream_port']}")
                    updated['ESP32_STREAM_PORT'] = True
                elif key == 'ESP32_CAPTURE_PATH':
                    new_lines.append(f"ESP32_CAPTURE_PATH={config['capture_path']}")
                    updated['ESP32_CAPTURE_PATH'] = True
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        
        # Tambahkan variabel yang belum ada
        for key, value in updated.items():
            if not value:
                if key == 'ESP32_IP':
                    new_lines.append(f"ESP32_IP={config['ip']}")
                elif key == 'ESP32_STREAM_PORT':
                    new_lines.append(f"ESP32_STREAM_PORT={config['stream_port']}")
                elif key == 'ESP32_CAPTURE_PATH':
                    new_lines.append(f"ESP32_CAPTURE_PATH={config['capture_path']}")
        
        # Tulis kembali file .env
        with open('.env', 'w') as f:
            f.write('\n'.join(new_lines))
    else:
        # Buat file .env baru
        with open('.env', 'w') as f:
            f.write(f"# Konfigurasi ESP32-CAM\n")
            f.write(f"ESP32_IP={config['ip']}\n")
            f.write(f"ESP32_STREAM_PORT={config['stream_port']}\n")
            f.write(f"ESP32_CAPTURE_PATH={config['capture_path']}\n")
            f.write("\n# Konfigurasi Flask\n")
            f.write("SECRET_KEY=secret_key_yang_sangat_rahasia\n") 