from flask import Blueprint, render_template, Response, redirect, url_for, session
from models.esp32_manager import ESP32Manager
from models.database import get_db, Book, User, Borrowing
import cv2 # type: ignore
import time
import numpy as np
from functools import wraps

# Inisialisasi Blueprint
main_bp = Blueprint('main', __name__)

# Inisialisasi ESP32Manager
esp32_manager = ESP32Manager()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('user.login'))
        return f(*args, **kwargs)
    return decorated_function

@main_bp.route('/')
def index():
    """
    Route untuk halaman utama
    """
    return render_template('index.html', 
                         esp32_setting_url=esp32_manager.get_control_url(),
                         user_name=session.get('user_name'))

@main_bp.route('/video_feed')
def video_feed():
    """
    Route untuk menampilkan video streaming
    """
    return Response(generate_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

def generate_frames():
    """
    Generator untuk streaming video
    """
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
        
        frame = esp32_manager.get_frame_from_stream()
        
        if frame is None:
            # Tampilkan frame error
            error_frame = create_error_frame("Menyambungkan Ulang...")
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

def create_error_frame(message):
    """
    Membuat frame dengan pesan error
    """
    frame = cv2.imread('views/static/img/error.jpg') if cv2.imread('views/static/img/error.jpg') is not None else create_blank_frame()
    cv2.putText(frame, message, (int(frame.shape[1]/2) - 150, int(frame.shape[0]/2)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    return frame

def create_blank_frame():
    """
    Membuat frame kosong dengan pesan error
    """
    frame = cv2.imread('views/static/img/error.jpg')
    if frame is None:
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
    return frame

@main_bp.route('/health')
def health_check():
    """
    Route untuk memeriksa status aplikasi
    """
    from models.face_recognition_model import FaceRecognitionModel
    import json
    
    face_model = FaceRecognitionModel()
    
    status = {
        "status": "healthy" if esp32_manager.check_connection() else "error",
        "camera_connected": esp32_manager.camera is not None and esp32_manager.camera.isOpened(),
        "known_faces_count": len(face_model.known_names),
        "esp32_config": esp32_manager.get_config()
    }
    
    return json.dumps(status) 

@main_bp.route('/peminjaman')
def peminjaman():
    """
    Route untuk halaman peminjaman buku
    """
    return render_template('peminjaman.html')

@main_bp.route('/book_detail')
def book_detail():
    # Halaman detail buku setelah pemindaian berhasil
    return render_template('book_detail.html')

@main_bp.route('/scan_timeout')
def scan_timeout():
    # Halaman timeout ketika pemindaian gagal
    return render_template('scan_timeout.html')

@main_bp.route('/borrowings')
def list_borrowings():
    """Halaman daftar transaksi peminjaman"""
    db = next(get_db())
    try:
        # Join dengan user dan book untuk mendapatkan detail lengkap
        borrowings = db.query(Borrowing)\
            .join(User, Borrowing.id_user == User.id)\
            .join(Book, Borrowing.id_buku == Book.id_buku)\
            .add_columns(
                User.nama_lengkap,
                Book.judul,
                Book.rfid_tag
            )\
            .order_by(Borrowing.created_at.desc())\
            .all()
        return render_template('borrowings.html', borrowings=borrowings)
    except Exception as e:
        return render_template('borrowings.html', borrowings=[], error=f"Error loading borrowings: {str(e)}")
    finally:
        db.close()

