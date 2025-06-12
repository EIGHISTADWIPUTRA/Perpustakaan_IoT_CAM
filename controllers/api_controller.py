from flask import Blueprint, jsonify, request, url_for, Response
from models.face_recognition_model import FaceRecognitionModel
from models.esp32_manager import ESP32Manager
from models.book_model import BookModel
from models.database import get_db, Book, User, Borrowing
import threading
import time
import json
import random
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Inisialisasi Blueprint
api_bp = Blueprint('api', __name__)

# Inisialisasi model dan manajer
face_model = FaceRecognitionModel()
esp32_manager = ESP32Manager()
book_model = BookModel()

# Variabel global untuk proses pengenalan
processing_lock = threading.Lock()
is_processing = False
processing_result = {"status": None, "message": None, "face_data": None}

# Variabel global untuk menyimpan last scanned RFID dan buku terkait
last_rfid_data = {"rfid_id": None, "book_data": None}

# Variabel global untuk proses scanning RFID
scan_lock = threading.Lock()
is_scanning = False
scan_result = {"status": "idle", "rfid_id": None}

# Variabel untuk kontrol permintaan scan dari web ke ESP32
scan_command = {"status": "idle"}

@api_bp.route('/start_recognition', methods=['POST'])
def start_recognition():
    """
    Memulai proses pengenalan wajah
    """
    global is_processing
    
    with processing_lock:
        if is_processing:
            return jsonify({"status": "error", "message": "Proses pengenalan sedang berlangsung"})
        is_processing = True
    
    # Mulai pengenalan wajah di thread terpisah
    threading.Thread(target=process_face_recognition).start()
    return jsonify({"status": "processing"})

@api_bp.route('/check_result')
def check_result():
    """
    Memeriksa hasil pengenalan wajah
    """
    global processing_result
    
    # Tambahkan redirect URL jika pengenalan berhasil
    if processing_result.get('status') == 'success':
        recognized_name = processing_result.get('message', '').replace('Selamat datang ', '')
        processing_result['redirect_url'] = url_for('main.peminjaman', name=recognized_name)
        
    return jsonify(processing_result)

@api_bp.route('/rfid_scan', methods=['POST', 'GET'])
def rfid_scan():
    """
    POST  → dipanggil ESP32 untuk mengirim ID kartu
    GET   → dipanggil Front-end untuk mengambil ID kartu & detail buku terakhir
    """
    global last_rfid_data, scan_result, is_scanning, scan_command

    print(f"[DEBUG] /api/rfid_scan endpoint dipanggil dengan metode {request.method}")
    
    # Jika metode GET, cukup kembalikan data terakhir
    if request.method == 'GET':
        if last_rfid_data.get('rfid_id') is None:
            return jsonify({"status": "empty"})
        return jsonify({"status": "success", **last_rfid_data})

    # Metode POST – ESP32 mengirimkan RFID
    if not request.is_json:
        return jsonify({"status": "error", "message": "Format request tidak valid, JSON diharapkan"})
    
    data = request.get_json()
    print(f"[DEBUG] Data dari ESP32: {data}")
    
    # Periksa apakah ini adalah timeout atau hasil pemindaian sukses
    if data.get('status') == 'timeout':
        # Update scan_result untuk endpoint scan_result
        with scan_lock:
            scan_result = {"status": "timeout", "message": "Tidak ada RFID yang terdeteksi"}
            is_scanning = False
            scan_command = {"status": "idle"}  # Reset scan command
        print(f"[DEBUG] Status scan diubah menjadi: timeout")
        return jsonify({"status": "success", "message": "Timeout berhasil dicatat"})
    
    rfid_id = data.get('rfid_id')
    
    if not rfid_id:
        return jsonify({"status": "error", "message": "RFID ID tidak ditemukan dalam request"})
    
    # Dapatkan data buku
    result = book_model.get_book_by_rfid(rfid_id)
    print(f"[DEBUG] Hasil query buku: {result}")

    # Update scan_result untuk endpoint scan_result
    with scan_lock:
        scan_result = {"status": "success", "rfid_id": rfid_id}
        is_scanning = False
        scan_command = {"status": "idle"}  # Reset scan command
    
    print(f"[DEBUG] Status scan diubah menjadi: success dengan RFID {rfid_id}")
    
    # Simpan hanya jika sukses
    if result["status"] == "success":
        last_rfid_data = {
            "rfid_id": rfid_id,
            "book_data": result["book_data"],
            "peminjaman": result["peminjaman"]
        }
    
    return jsonify(result)

@api_bp.route('/get_last_rfid')
def get_last_rfid():
    """
    Mendapatkan data RFID terakhir yang dipindai
    """
    global last_rfid_data
    
    if last_rfid_data["rfid_id"] is None:
        return jsonify({"status": "error", "message": "Belum ada RFID yang dipindai"})
    
    return jsonify({
        "status": "success",
        "rfid_id": last_rfid_data["rfid_id"],
        "book_data": last_rfid_data["book_data"],
        "peminjaman": last_rfid_data["peminjaman"]
    })

@api_bp.route('/process_peminjaman', methods=['POST'])
def process_peminjaman():
    """
    Memproses peminjaman buku
    """
    # Pastikan format request benar
    if not request.is_json:
        return jsonify({"status": "error", "message": "Format request tidak valid, JSON diharapkan"})
    
    # Dapatkan data peminjaman
    data = request.get_json()
    rfid_id = data.get('rfid_id')
    username = data.get('username')
    
    if not rfid_id or not username:
        return jsonify({"status": "error", "message": "Data peminjaman tidak lengkap"})
    
    # Proses peminjaman
    result = book_model.proses_peminjaman(rfid_id, username)
    
    # Reset data RFID terakhir jika berhasil
    global last_rfid_data
    if result["status"] == "success":
        last_rfid_data = {"rfid_id": None, "book_data": None}
    
    return jsonify(result)

@api_bp.route('/return_book', methods=['POST'])
def return_book():
    """
    Memproses pengembalian buku oleh pengguna
    """
    # Pastikan format request benar
    if not request.is_json:
        return jsonify({"status": "error", "message": "Format request tidak valid, JSON diharapkan"})
    
    # Dapatkan data pengembalian
    data = request.get_json()
    username = data.get('username')
    
    if not username:
        return jsonify({"status": "error", "message": "Username tidak ditemukan dalam request"})
    
    # Proses pengembalian
    result = book_model.kembalikan_buku(username)
    
    return jsonify(result)

@api_bp.route('/add_face', methods=['POST'])
def add_face():
    """
    Menambahkan wajah baru
    """
    # Cek apakah ada file yang dikirim
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "Tidak ada file yang dikirim"})
        
    file = request.files['file']
    name = request.form.get('name', '')
    
    if file.filename == '':
        return jsonify({"status": "error", "message": "Tidak ada file yang dipilih"})
        
    if name == '':
        return jsonify({"status": "error", "message": "Nama wajah tidak boleh kosong"})
    
    try:
        # Baca file
        image_data = file.read()
        
        # Tambahkan wajah menggunakan model
        result = face_model.add_face(image_data, name)
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error saat menambahkan wajah: {str(e)}"})

@api_bp.route('/rfid_events')
def rfid_events():
    """
    Endpoint untuk Server-Sent Events (SSE)
    Browser akan menerima notifikasi saat ada RFID baru terdeteksi
    """
    def event_stream():
        # Keep track of the last RFID ID seen
        last_seen_rfid = None
        
        while True:
            # Check if there's new RFID data
            if last_rfid_data.get('rfid_id') and last_rfid_data.get('rfid_id') != last_seen_rfid:
                # New RFID detected
                last_seen_rfid = last_rfid_data.get('rfid_id')
                
                # Send event with RFID data
                data = {
                    "status": "success",
                    "rfid_id": last_rfid_data.get('rfid_id'),
                    "book_data": last_rfid_data.get('book_data'),
                    "peminjaman": last_rfid_data.get('peminjaman')
                }
                
                yield f"data: {json.dumps(data)}\n\n"
            
            # Wait a bit before checking again
            time.sleep(0.5)
    
    return Response(event_stream(), mimetype="text/event-stream")

@api_bp.route('/start_scan', methods=['POST'])
def start_scan():
    """
    Memulai pemindaian RFID oleh ESP32
    """
    global is_scanning, scan_result, scan_command
    
    # Reset status
    with scan_lock:
        if is_scanning:
            return jsonify({"status": "error", "message": "Sudah ada proses scanning yang sedang berjalan"})
        is_scanning = True
        scan_result = {"status": "scanning", "rfid_id": None}
        # Set perintah scan untuk ESP32
        scan_command = {"status": "scan", "timestamp": time.time()}
    
    return jsonify({"status": "scanning", "message": "Pemindaian sedang berlangsung"})

@api_bp.route('/check_scan_command', methods=['GET'])
def check_scan_command():
    """
    Endpoint untuk ESP32 melakukan polling perintah scan
    """
    global scan_command
    
    print(f"[DEBUG] /api/check_scan_command dipanggil, status: {scan_command['status']}")
    
    # Jika ada perintah scanning yang baru (dalam 30 detik terakhir)
    if scan_command["status"] == "scan" and time.time() - scan_command.get("timestamp", 0) < 30:
        return jsonify(scan_command)
    
    # Default: tidak ada perintah
    return jsonify({"status": "idle"})

@api_bp.route('/scan_result', methods=['GET'])
def get_scan_result():
    """
    Mendapatkan hasil pemindaian RFID terbaru
    """
    global scan_result, is_scanning
    
    print(f"[DEBUG] /api/scan_result dipanggil, status: {scan_result['status']}")
    
    # Reset is_scanning jika status sudah success atau timeout
    if scan_result["status"] in ["success", "timeout"]:
        is_scanning = False
    
    return jsonify(scan_result)

@api_bp.route('/get_book_detail', methods=['GET'])
def get_book_detail():
    """
    Mendapatkan detail buku berdasarkan RFID dan memproses peminjaman
    """
    # Ambil ID RFID dari parameter
    rfid_id = request.args.get('rfid_id')
    if not rfid_id:
        return jsonify({"status": "error", "message": "ID RFID tidak ditemukan"})
    
    # Log info untuk debugging
    logger.info(f"GET /api/get_book_detail - RFID: {rfid_id}, Username: {request.args.get('username')}")
    
    try:
        # Dapatkan informasi buku
        book_info = book_model.get_book_by_rfid(rfid_id)
        
        # Jika berhasil, proses peminjaman secara otomatis
        if book_info["status"] == "success":
            # Anggap username dari parameter atau pakai default
            username = request.args.get('username') or 'Pengguna'
            
            # Proses peminjaman
            result = book_model.proses_peminjaman(rfid_id, username)
            logger.info(f"Hasil peminjaman: {result}")
            return jsonify(result)
        
        return jsonify(book_info)
    except Exception as e:
        logger.error(f"Error dalam get_book_detail: {str(e)}")
        return jsonify({"status": "error", "message": f"Terjadi kesalahan: {str(e)}"})

@api_bp.route('/reset_scanning', methods=['POST'])
def reset_scanning():
    """
    Mereset status pemindaian jika terjadi kesalahan atau timeout di sisi klien
    """
    global is_scanning, scan_result, scan_command
    
    with scan_lock:
        is_scanning = False
        scan_result = {"status": "idle", "rfid_id": None}
        scan_command = {"status": "idle"}
    
    return jsonify({"status": "success", "message": "Status scanning direset"})

@api_bp.route('/reload_faces', methods=['POST'])
def reload_faces():
    result = face_model.reload_known_faces()
    return jsonify(result)

@api_bp.route('/borrowing/<int:borrowing_id>')
def get_borrowing_detail(borrowing_id):
    """
    Mendapatkan detail peminjaman
    """
    db = next(get_db())
    try:
        # Query peminjaman dengan join ke user dan buku
        borrowing = db.query(Borrowing)\
            .join(User, Borrowing.id_user == User.id)\
            .join(Book, Borrowing.id_buku == Book.id_buku)\
            .filter(Borrowing.id_peminjaman == borrowing_id)\
            .first()

        if not borrowing:
            return jsonify({
                "status": "error",
                "message": "Peminjaman tidak ditemukan"
            }), 404

        return jsonify({
            "status": "success",
            "data": {
                "id_peminjaman": borrowing.id_peminjaman,
                "tanggal_pinjam": borrowing.tanggal_pinjam.strftime("%Y-%m-%d %H:%M:%S"),
                "tanggal_kembali": borrowing.tanggal_kembali.strftime("%Y-%m-%d %H:%M:%S") if borrowing.tanggal_kembali else None,
                "status": borrowing.status,
                "synced_to_server": borrowing.synced_to_server,
                "user": {
                    "id": borrowing.user.id,
                    "nama_lengkap": borrowing.user.nama_lengkap,
                    "email": borrowing.user.email
                },
                "book": {
                    "id": borrowing.book.id_buku,
                    "judul": borrowing.book.judul,
                    "rfid_tag": borrowing.book.rfid_tag
                }
            }
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Error: {str(e)}"
        }), 500
    finally:
        db.close()

def process_face_recognition():
    """
    Proses pengenalan wajah
    """
    global is_processing, processing_result
    
    try:
        # Set timeout
        start_time = time.time()
        process_timeout = 5  # detik
        
        # Reset hasil proses
        processing_result = {"status": None, "message": None, "face_data": None}
        
        # Dapatkan frame dari ESP32
        frame = esp32_manager.get_frame_from_capture()
        
        # Jika tidak bisa mendapatkan frame, coba dari stream
        if frame is None:
            frame = esp32_manager.get_frame_from_stream()
        
        # Jika masih tidak bisa mendapatkan frame
        if frame is None:
            processing_result = {
                "status": "error",
                "message": "Gagal mendapatkan gambar dari kamera ESP32"
            }
            return
        
        # Proses pengenalan wajah
        processing_result = face_model.process_face_recognition(frame)
        
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
        
        is_processing = False 

def simulate_rfid_scan():
    """
    Simulasi pemindaian RFID oleh ESP32
    """
    global is_scanning, scan_result
    
    try:
        # Tunggu beberapa detik (simulasi scanning)
        time.sleep(3)
        
        # Simulasi berhasil mendapatkan RFID dengan probabilitas 80%
        if random.random() < 0.8:
            # Pilih RFID secara acak dari daftar yang tersedia
            available_rfids = list(book_model.rfid_to_book.keys())
            rfid = random.choice(available_rfids)
            
            # Simulasi sukses
            with scan_lock:
                scan_result = {"status": "success", "rfid_id": rfid}
        else:
            # Simulasi timeout
            with scan_lock:
                scan_result = {"status": "timeout", "message": "Tidak ada RFID yang terdeteksi"}
    finally:
        # Pastikan status scanning di-reset
        is_scanning = False