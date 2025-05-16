import cv2 # type: ignore
import numpy as np
import face_recognition # type: ignore
import os
import time
import requests
from flask import Flask, render_template, Response, jsonify, request, session, redirect, url_for
import threading
import base64
from datetime import datetime
import pickle
import gc
import json

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Secret key untuk session management

# Variabel global
known_encodings = []
known_names = []
processing_lock = threading.Lock()
is_processing = False
camera = None
processing_result = {"status": None, "message": None, "face_data": None}
process_timeout = 5  # detik
app_start_time = time.time()  # Untuk monitoring

# Config file
CONFIG_FILE = "config.json"

# Default ESP32 config
DEFAULT_ESP32_CONFIG = {
    "ip": "192.168.68.104",
    "stream_port": "81",
    "capture_path": "/capture"
}

# Folder untuk menyimpan gambar tangkapan dan encoding wajah
CAPTURES_FOLDER = "captures"
ENCODINGS_FOLDER = "encodings"
KNOWN_FACES_DIR = "known_faces"
KNOWN_FACES_ENCODING_FILE = "known_faces_encodings.pkl"

# Buat folder jika belum ada
for folder in [CAPTURES_FOLDER, ENCODINGS_FOLDER, KNOWN_FACES_DIR]:
    if not os.path.exists(folder):
        os.makedirs(folder)
        print(f"Folder {folder} dibuat")

# --------------------------------------------------
# Fungsi untuk load dan simpan konfigurasi
# --------------------------------------------------
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                print(f"Konfigurasi berhasil dimuat dari {CONFIG_FILE}")
                return config
        except Exception as e:
            print(f"Error memuat konfigurasi: {str(e)}")
    
    # Jika tidak ada file konfigurasi atau terjadi error, gunakan default
    print("Menggunakan konfigurasi default")
    save_config(DEFAULT_ESP32_CONFIG)
    return DEFAULT_ESP32_CONFIG

def save_config(config):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        print(f"Konfigurasi tersimpan ke {CONFIG_FILE}")
        return True
    except Exception as e:
        print(f"Error menyimpan konfigurasi: {str(e)}")
        return False

# --------------------------------------------------
# Fungsi untuk mendapatkan URL ESP32-CAM
# --------------------------------------------------
def get_esp32_urls():
    config = load_config()
    ip = config.get("ip", DEFAULT_ESP32_CONFIG["ip"])
    stream_port = config.get("stream_port", DEFAULT_ESP32_CONFIG["stream_port"])
    capture_path = config.get("capture_path", DEFAULT_ESP32_CONFIG["capture_path"])
    
    stream_url = f"http://{ip}:{stream_port}/stream"
    capture_url = f"http://{ip}{capture_path}"
    
    return stream_url, capture_url

# --------------------------------------------------
# Fungsi untuk konversi gambar JPEG ke encoding pickle
# --------------------------------------------------
def convert_image_to_encoding(image_path):
    try:
        # Baca gambar
        img = cv2.imread(image_path)
        if img is None:
            print(f"Error membaca gambar: {image_path}")
            return None
            
        # Konversi ke RGB untuk face_recognition
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        # Deteksi wajah dan dapatkan encoding
        face_locations = face_recognition.face_locations(rgb)
        if len(face_locations) == 0:
            print(f"Tidak ada wajah ditemukan di {image_path}")
            return None
            
        # Ambil encoding wajah pertama yang ditemukan
        face_encoding = face_recognition.face_encodings(rgb, face_locations)[0]
        
        # Dapatkan nama dari nama file
        name = os.path.splitext(os.path.basename(image_path))[0]
        
        # Buat path untuk file pickle
        pickle_path = os.path.join(ENCODINGS_FOLDER, f"{name}.pkl")
        
        # Simpan encoding dalam format pickle
        with open(pickle_path, 'wb') as f:
            pickle.dump(face_encoding, f)
            
        print(f"Encoding wajah disimpan: {pickle_path}")
        return pickle_path
    except Exception as e:
        print(f"Error saat konversi gambar ke encoding: {str(e)}")
        return None

# --------------------------------------------------
# Konversi semua gambar di folder known_faces ke pickle
# --------------------------------------------------
def convert_all_known_faces():
    if not os.path.exists(KNOWN_FACES_DIR):
        print(f"Direktori {KNOWN_FACES_DIR} tidak ditemukan.")
        return
        
    for filename in os.listdir(KNOWN_FACES_DIR):
        if filename.lower().endswith(('.jpg', '.png', '.jpeg')):
            path = os.path.join(KNOWN_FACES_DIR, filename)
            convert_image_to_encoding(path)

# --------------------------------------------------
# Memuat wajah referensi dari file pickle
# --------------------------------------------------
def load_known_faces():
    global known_encodings, known_names
    known_encodings = []
    known_names = []
    
    # Cek apakah file encoding utama ada
    if os.path.exists(KNOWN_FACES_ENCODING_FILE):
        try:
            with open(KNOWN_FACES_ENCODING_FILE, 'rb') as f:
                known_data = pickle.load(f)
                known_encodings = known_data['encodings']
                known_names = known_data['names']
            print(f"Memuat {len(known_names)} wajah dari file encoding utama: {known_names}")
            return
        except Exception as e:
            print(f"Error saat memuat file encoding utama: {str(e)}")
    
    # Jika tidak ada file encoding utama, muat dari folder encodings
    if os.path.exists(ENCODINGS_FOLDER):
        for filename in os.listdir(ENCODINGS_FOLDER):
            if filename.endswith('.pkl'):
                path = os.path.join(ENCODINGS_FOLDER, filename)
                try:
                    with open(path, 'rb') as f:
                        face_encoding = pickle.load(f)
                        
                    # Ambil nama dari nama file, misal "john.pkl" → "john"
                    name = os.path.splitext(filename)[0]
                    
                    known_encodings.append(face_encoding)
                    known_names.append(name)
                    print(f"Memuat encoding wajah: {name}")
                except Exception as e:
                    print(f"Error memproses {filename}: {str(e)}")
    
    # Jika tidak ada file pickle, konversi dari gambar
    if len(known_encodings) == 0:
        print("Tidak ada file encoding ditemukan, memuat dari gambar...")
        convert_all_known_faces()
        load_known_faces()  # Panggil kembali untuk memuat hasil konversi
    else:
        # Simpan encoding ke file utama untuk mempercepat pemuatan
        try:
            with open(KNOWN_FACES_ENCODING_FILE, 'wb') as f:
                pickle.dump({'encodings': known_encodings, 'names': known_names}, f)
            print(f"Menyimpan {len(known_names)} encoding ke file utama")
        except Exception as e:
            print(f"Error saat menyimpan file encoding utama: {str(e)}")
    
    print(f"Total memuat {len(known_names)} wajah: {known_names}")

# --------------------------------------------------
# Fungsi untuk menghasilkan frame streaming (tetap menggunakan stream untuk tampilan)
# --------------------------------------------------
def generate_frames():
    global camera
    
    # Dapatkan URL streaming
    stream_url, _ = get_esp32_urls()
    
    if camera is None:
        # Inisialisasi kamera
        camera = cv2.VideoCapture(stream_url)
        camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    
    # Untuk efisiensi, kita bisa menambahkan interval waktu antara frame
    last_frame_time = 0
    frame_interval = 0.05  # 50ms antar frame
    
    while True:
        # Batasi frame rate untuk efisiensi
        now = time.time()
        if now - last_frame_time < frame_interval:
            time.sleep(0.01)
            continue
            
        last_frame_time = now
        
        with processing_lock:
            if is_processing:
                # Ketika pemrosesan sedang berlangsung, kirim frame status
                status_frame = np.ones((480, 640, 3), dtype=np.uint8) * 200  # Abu-abu muda
                cv2.putText(status_frame, "Memproses pengenalan wajah...", (120, 240),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                _, buffer = cv2.imencode('.jpg', status_frame)
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                continue
                
        success, frame = camera.read()
        if not success:
            print("Gagal membaca frame dari kamera")
            # Coba sambungkan kembali
            camera.release()
            time.sleep(0.5)
            camera = cv2.VideoCapture(stream_url)
            camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            # Tampilkan frame error
            error_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(error_frame, "Menyambungkan Ulang...", (150, 240),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            _, buffer = cv2.imencode('.jpg', error_frame)
            frame_bytes = buffer.tobytes()
            
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            
            time.sleep(1)
            continue
        
        # Encode frame
        _, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()
        
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

# --------------------------------------------------
# Dapatkan gambar langsung dari endpoint capture ESP32-CAM
# --------------------------------------------------
def get_capture_from_esp32():
    try:
        # Ambil URL capture
        _, capture_url = get_esp32_urls()
        
        # Ambil gambar dari URL capture (lebih real-time daripada stream)
        img_resp = requests.get(capture_url, timeout=2)
        if img_resp.status_code != 200:
            print(f"Error mendapatkan gambar dari ESP32: {img_resp.status_code}")
            return None
            
        img_arr = np.array(bytearray(img_resp.content), dtype=np.uint8)
        frame = cv2.imdecode(img_arr, -1)
        
        if frame is None:
            print("Frame kosong dari kamera")
            return None
            
        return frame
    except Exception as e:
        print(f"Error saat mengambil gambar dari ESP32: {str(e)}")
        return None

# --------------------------------------------------
# Simpan gambar tangkapan
# --------------------------------------------------
def save_capture():
    try:
        # Dapatkan frame dari endpoint capture
        frame = get_capture_from_esp32()
        
        if frame is None:
            print("Gagal mendapatkan gambar dari ESP32")
            return None
            
        # Buat nama file dengan timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_capture.jpg"
        filepath = os.path.join(CAPTURES_FOLDER, filename)
        
        # Simpan gambar
        cv2.imwrite(filepath, frame)
        print(f"Capture tersimpan: {filepath}")
        
        return filepath
    except Exception as e:
        print(f"Error menyimpan capture: {str(e)}")
        return None

# --------------------------------------------------
# Bersihkan file lama di folder captures
# --------------------------------------------------
def clean_old_captures(max_age_days=7):
    try:
        now = time.time()
        count = 0
        for f in os.listdir(CAPTURES_FOLDER):
            path = os.path.join(CAPTURES_FOLDER, f)
            if os.path.isfile(path) and now - os.path.getmtime(path) > max_age_days * 24 * 3600:
                os.remove(path)
                count += 1
        if count > 0:
            print(f"Membersihkan {count} file capture lama")
    except Exception as e:
        print(f"Error saat membersihkan file lama: {str(e)}")

# --------------------------------------------------
# Pemrosesan pengenalan wajah
# --------------------------------------------------
def process_face_recognition():
    global is_processing, processing_result
    processing_result = {"status": None, "message": None, "face_data": None}
    # Set timeout
    start_time = time.time()
    
    try:
        # Dapatkan gambar langsung dari ESP32 (endpoint capture untuk real-time)
        frame = get_capture_from_esp32()
        
        if frame is None:
            processing_result = {
                "status": "error",
                "message": "Gagal mendapatkan gambar dari kamera ESP32"
            }
            return
        
        # Buat nama file dengan timestamp untuk menyimpan hasil
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        orig_filepath = os.path.join(CAPTURES_FOLDER, f"{timestamp}_capture.jpg")
        
        # Simpan gambar original
        cv2.imwrite(orig_filepath, frame)
        
        # Konversi ke RGB untuk face_recognition
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Deteksi lokasi wajah
        face_locations = face_recognition.face_locations(rgb_frame)
        
        # Cek apakah wajah terdeteksi
        if len(face_locations) == 0:
            processing_result = {
                "status": "error",
                "message": "Tidak ada wajah terdeteksi dalam gambar"
            }
            # Hapus file gambar yang tidak ada wajah
            if os.path.exists(orig_filepath):
                os.remove(orig_filepath)
            return
        
        # Ambil maksimal 3 wajah terbesar dalam frame untuk efisiensi
        if len(face_locations) > 3:
            areas = [(right-left)*(bottom-top) for (top, right, bottom, left) in face_locations]
            # Ambil 3 wajah dengan area terbesar
            face_locations = [loc for _, loc in sorted(zip(areas, face_locations), reverse=True)[:3]]
        
        # Dapatkan encoding wajah
        face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
        
        if len(face_encodings) == 0:
            processing_result = {
                "status": "error",
                "message": "Wajah terdeteksi tetapi tidak dapat diproses"
            }
            return
        
        # Untuk setiap wajah terdeteksi
        result_frame = frame.copy()
        recognized = False
        recognized_name = ""
        tolerance = 0.4  # Toleransi untuk pengenalan wajah (nilai lebih rendah = lebih ketat)
        
        for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
            # Periksa apakah wajah cocok dengan wajah yang dikenal
            matches = face_recognition.compare_faces(known_encodings, face_encoding, tolerance=tolerance)
            name = "Unknown"
            
            if True in matches:
                idx = matches.index(True)
                name = known_names[idx]
                recognized = True
                recognized_name = name
                
                # Gambar kotak hijau dan nama
                cv2.rectangle(result_frame, (left, top), (right, bottom), (0, 255, 0), 2)
                cv2.putText(result_frame, name, (left, top - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
            else:
                # Gambar kotak merah untuk yang tidak dikenal
                cv2.rectangle(result_frame, (left, top), (right, bottom), (0, 0, 255), 2)
                cv2.putText(result_frame, "Unknown", (left, top - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
        
        # Ubah nama file dengan menambahkan nama yang terdeteksi
        if recognized:
            new_filename = f"{timestamp}_{recognized_name}.jpg"
        else:
            new_filename = f"{timestamp}_unknown.jpg"
            
        new_filepath = os.path.join(CAPTURES_FOLDER, new_filename)
        
        # Simpan gambar hasil dengan nama baru
        cv2.imwrite(new_filepath, result_frame)
        print(f"Hasil pengenalan tersimpan: {new_filepath}")
        
        # Hapus capture awal jika berhasil menyimpan hasil
        if os.path.exists(orig_filepath):
            os.remove(orig_filepath)
            print(f"File awal dihapus: {orig_filepath}")
        
        # Konversi gambar hasil ke base64 untuk tampilan web
        _, buffer = cv2.imencode('.jpg', result_frame)
        result_base64 = base64.b64encode(buffer).decode('utf-8')
        
        if recognized:
            processing_result = {
                "status": "success",
                "message": f"Selamat datang {recognized_name}",
                "face_data": result_base64
            }
        else:
            processing_result = {
                "status": "unknown",
                "message": "Anda tidak terdaftar dalam sistem",
                "face_data": result_base64
            }
            
    except Exception as e:
        processing_result = {
            "status": "error",
            "message": f"Error dalam pemrosesan: {str(e)}"
        }
    finally:
        # Periksa apakah proses melebihi timeout
        if time.time() - start_time > process_timeout:
            processing_result = {
                "status": "timeout",
                "message": "Pengenalan gagal: waktu habis"
            }
        
        # Bebaskan memori
        gc.collect()
        is_processing = False

# --------------------------------------------------
# Route Flask
# --------------------------------------------------
@app.route('/')
def index():
    # Cek apakah konfigurasi sudah diatur
    config = load_config()
    
    # Jika ini adalah pertama kali pengguna mengakses dan konfigurasi default digunakan
    if config == DEFAULT_ESP32_CONFIG:
        return redirect(url_for('setup'))
    
    return render_template('index.html')

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    if request.method == 'POST':
        # Ambil nilai dari form
        esp32_ip = request.form.get('esp32_ip', DEFAULT_ESP32_CONFIG['ip'])
        stream_port = request.form.get('stream_port', DEFAULT_ESP32_CONFIG['stream_port'])
        capture_path = request.form.get('capture_path', DEFAULT_ESP32_CONFIG['capture_path'])
        
        # Validasi input
        if not esp32_ip:
            return render_template('setup.html', error="IP ESP32-CAM tidak boleh kosong", config=DEFAULT_ESP32_CONFIG)
        
        # Simpan konfigurasi baru
        new_config = {
            "ip": esp32_ip,
            "stream_port": stream_port,
            "capture_path": capture_path
        }
        
        if save_config(new_config):
            # Reset kamera jika sudah terhubung
            global camera
            if camera is not None:
                camera.release()
                camera = None
            
            # Redirect ke halaman pengenalan ESP32-CAM
            return redirect(url_for('settings'))
        else:
            return render_template('setup.html', error="Gagal menyimpan konfigurasi", config=new_config)
    
    # Untuk metode GET, tampilkan form dengan konfigurasi saat ini
    config = load_config()
    return render_template('setup.html', config=config)

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/start_recognition', methods=['POST'])
def start_recognition():
    global is_processing
    
    with processing_lock:
        if is_processing:
            return jsonify({"status": "error", "message": "Proses pengenalan sedang berlangsung"})
        is_processing = True
    
    # Mulai pengenalan wajah di thread terpisah
    threading.Thread(target=process_face_recognition).start()
    return jsonify({"status": "processing"})

@app.route('/check_result')
def check_result():
    global processing_result
    return jsonify(processing_result)

@app.route('/health')
def health_check():
    # Dapatkan URL streaming
    stream_url, capture_url = get_esp32_urls()
    
    status = {
        "status": "healthy",
        "camera_connected": camera is not None and camera.isOpened(),
        "known_faces_count": len(known_names),
        "uptime": time.time() - app_start_time,
        "esp32_config": {
            "stream_url": stream_url,
            "capture_url": capture_url
        }
    }
    return jsonify(status)

@app.route('/add_face', methods=['POST'])
def add_face():
    # Cek apakah ada file yang dikirim
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "Tidak ada file yang dikirim"})
        
    file = request.files['file']
    name = request.form.get('name', '')
    
    if file.filename == '':
        return jsonify({"status": "error", "message": "Tidak ada file yang dipilih"})
        
    if name == '':
        return jsonify({"status": "error", "message": "Nama wajah tidak boleh kosong"})
    
    # Buat nama file dari nama yang diberikan
    filename = f"{name}.jpg"
    filepath = os.path.join(KNOWN_FACES_DIR, filename)
    
    try:
        # Simpan file
        file.save(filepath)
        
        # Konversi ke encoding dan simpan
        encoding_path = convert_image_to_encoding(filepath)
        
        if encoding_path:
            # Muat ulang wajah yang dikenal
            load_known_faces()
            return jsonify({"status": "success", "message": f"Wajah {name} berhasil ditambahkan"})
        else:
            return jsonify({"status": "error", "message": "Gagal mengkonversi gambar ke encoding"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error saat menambahkan wajah: {str(e)}"})

@app.route('/settings', methods=['GET'])
def settings():
    config = load_config()
    return render_template('setup.html', config=config)

# --------------------------------------------------
# Fungsi utama untuk menjalankan aplikasi
# --------------------------------------------------
if __name__ == '__main__':
    # Muat wajah yang dikenal saat startup
    load_known_faces()
    
    # Bersihkan file lama secara otomatis
    clean_old_captures()
    
    try:
        app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
    finally:
        # Lepaskan kamera saat aplikasi berhenti
        if camera is not None:
            camera.release()
        print("Aplikasi berhenti, membersihkan sumber daya...")
