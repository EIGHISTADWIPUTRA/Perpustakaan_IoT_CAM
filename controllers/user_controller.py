# controllers/user_controller.py
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from models.database import get_db, User
from models.esp32_manager import ESP32Manager
from models.face_recognition_model import FaceRecognitionModel
from datetime import datetime
import base64
import os
import threading
import logging

# Inisialisasi Blueprint
user_bp = Blueprint('user', __name__)

# Inisialisasi models
esp32_manager = ESP32Manager()
face_model = FaceRecognitionModel()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@user_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Halaman login"""
    if request.method == 'POST':
        email = request.form.get('email')
        role = request.form.get('role')
        
        if not email or not role:
            return render_template('login.html', error='Email dan role harus diisi')
        
        db = next(get_db())
        try:
            # Find user by email
            user = db.query(User).filter(User.email == email, User.role == role).first()
            
            if not user:
                return render_template('login.html', error='User tidak ditemukan atau role tidak sesuai')
            
            # Set session
            session['user_id'] = user.id
            session['user_role'] = user.role
            session['user_name'] = user.nama_lengkap
            
            if user.role == 'admin':
                return redirect(url_for('admin.list_borrowings'))
            else:
                return redirect(url_for('main.index'))
            
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            return render_template('login.html', error=f'Error: {str(e)}')
        finally:
            db.close()
    
    return render_template('login.html')

@user_bp.route('/logout')
def logout():
    """Logout user"""
    session.clear()
    return redirect(url_for('user.login'))

@user_bp.route('/users')
def list_users():
    """Halaman daftar user"""
    db = next(get_db())
    try:
        users = db.query(User).order_by(User.created_at.desc()).all()
        return render_template('users.html', users=users)
    except Exception as e:
        return render_template('users.html', users=[], error=f"Error loading users: {str(e)}")
    finally:
        db.close()

@user_bp.route('/register')
def register_page():
    """Halaman registrasi user"""
    return render_template('register.html')

@user_bp.route('/capture_face', methods=['POST'])
def capture_face():
    """
    Capture wajah dari ESP32-CAM untuk registrasi
    """
    try:
        logger.info("Checking ESP32 connection...")
        if not esp32_manager.check_connection():
            logger.error("ESP32 camera is not accessible")
            return jsonify({
                "status": "error",
                "message": "Kamera ESP32 tidak dapat diakses. Periksa koneksi dan IP address."
            }), 500

        logger.info("Attempting to capture face from ESP32...")
        # Dapatkan frame dari ESP32
        frame = esp32_manager.get_frame_from_capture()
        
        if frame is None:
            logger.warning("Failed to get frame from capture, trying stream...")
            frame = esp32_manager.get_frame_from_stream()
        
        if frame is None:
            logger.error("Failed to get frame from both capture and stream")
            return jsonify({
                "status": "error",
                "message": "Gagal mendapatkan gambar dari kamera ESP32"
            }), 500
            
        logger.info(f"Got frame with shape: {frame.shape}")
          # Proses deteksi wajah
        try:
            result = face_model.process_face_recognition(frame)
            logger.info(f"Face recognition result: {result['status']}")
            
            if result["status"] == "error":
                logger.error(f"Face recognition error: {result['message']}")
                return jsonify(result), 400
                
            # Log hasil yang berhasil
            if result["status"] in ["success", "unknown"]:
                logger.info(f"Successfully processed image. Face data length: {len(result['face_data']) if result['face_data'] else 0}")
        except Exception as face_error:
            logger.error(f"Exception during face recognition: {str(face_error)}")
            return jsonify({
                "status": "error",
                "message": f"Error dalam proses pengenalan wajah: {str(face_error)}"
            }), 500
        
        # Jika wajah terdeteksi tapi sudah dikenal
        if result["status"] == "success":
            return jsonify({
                "status": "duplicate",
                "message": f"Wajah sudah terdaftar sebagai: {result['message'].replace('Selamat datang ', '')}"
            }), 409
        
        # Jika wajah terdeteksi tapi belum dikenal (ini yang kita inginkan untuk registrasi)
        if result["status"] == "unknown":
            # Extract face crop dari gambar untuk registrasi
            face_crop_base64 = result["face_data"]  # Sudah dalam format base64
            
            return jsonify({
                "status": "success",
                "message": "Wajah berhasil ditangkap untuk registrasi",
                "face_crop_base64": face_crop_base64
            }), 200
        
        return jsonify({
            "status": "error",
            "message": "Status tidak dikenali dari face recognition"
        }), 500
        
    except Exception as e:
        logger.error(f"Error capturing face: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Error saat capture wajah: {str(e)}"
        }), 500

@user_bp.route('/save_registration', methods=['POST'])
def save_registration():
    """
    Simpan registrasi user baru
    """
    try:
        if not request.is_json:
            return jsonify({
                "status": "error",
                "message": "Invalid content type. JSON expected"
            }), 400
        
        data = request.get_json()
        
        # Validasi data
        required_fields = ['nama_lengkap', 'email', 'face_image_data']
        missing_fields = [field for field in required_fields if not data.get(field)]
        
        if missing_fields:
            return jsonify({
                "status": "error",
                "message": f"Missing required fields: {', '.join(missing_fields)}"
            }), 400
        
        # Validasi email format
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, data['email']):
            return jsonify({
                "status": "error",
                "message": "Invalid email format"
            }), 400
        
        db = next(get_db())
        
        try:
            # Cek apakah email sudah ada
            existing_user = db.query(User).filter(User.email == data['email']).first()
            if existing_user:
                return jsonify({
                    "status": "error",
                    "message": "Email sudah terdaftar dalam sistem"
                }), 409
            
            # Simpan gambar wajah
            face_image_path = save_face_image(data['face_image_data'], data['nama_lengkap'])
            if not face_image_path:
                return jsonify({
                    "status": "error",
                    "message": "Gagal menyimpan gambar wajah"
                }), 500
            
            # Buat user baru
            new_user = User(
                nama_lengkap=data['nama_lengkap'],
                email=data['email'],
                role=data.get('role', 'member'),
                face_image_path=face_image_path,
                synced_to_server=False,  # Akan di-sync ke Laravel
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            
            db.add(new_user)
            db.commit()
            
            # Generate face encoding untuk recognition
            try:
                face_model.convert_image_to_encoding(face_image_path)
                face_model.load_known_faces()  # Reload faces
            except Exception as e:
                logger.warning(f"Failed to generate face encoding: {str(e)}")
            
            logger.info(f"New user registered: {new_user.nama_lengkap} (ID: {new_user.id})")
            
            # AUTO-SYNC: Langsung sync ke Laravel di background
            try:
                from models.sync_service import sync_service
                
                def sync_in_background():
                    result = sync_service.sync_user_to_laravel(new_user.id)
                    if result['success']:
                        logger.info(f"User {new_user.id} auto-synced to Laravel successfully")
                    else:
                        logger.warning(f"Failed to auto-sync user {new_user.id}: {result['error']}")
                
                sync_thread = threading.Thread(target=sync_in_background)
                sync_thread.daemon = True
                sync_thread.start()
            except Exception as e:
                logger.warning(f"Auto-sync user failed: {str(e)}")
            
            return jsonify({
                "status": "success",
                "message": f"User {data['nama_lengkap']} berhasil didaftarkan",
                "user_id": new_user.id
            }), 201
            
        except Exception as e:
            db.rollback()
            logger.error(f"Database error during user registration: {str(e)}")
            return jsonify({
                "status": "error",
                "message": f"Database error: {str(e)}"
            }), 500
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error in user registration: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Registration failed: {str(e)}"
        }), 500

def save_face_image(face_image_base64, user_name):
    """
    Simpan gambar wajah dari base64 ke file
    """
    try:
        # Pastikan folder known_faces ada
        known_faces_dir = "known_faces"
        if not os.path.exists(known_faces_dir):
            os.makedirs(known_faces_dir)
        
        # Decode base64
        image_data = base64.b64decode(face_image_base64)
        
        # Buat nama file (sanitize nama user)
        safe_name = "".join(c for c in user_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_name = safe_name.replace(' ', '_')
        filename = f"{safe_name}_{int(datetime.now().timestamp())}.jpg"
        filepath = os.path.join(known_faces_dir, filename)
        
        # Simpan file
        with open(filepath, 'wb') as f:
            f.write(image_data)
        
        logger.info(f"Face image saved: {filepath}")
        return filepath
        
    except Exception as e:
        logger.error(f"Error saving face image: {str(e)}")
        return None

@user_bp.route('/sync_manual', methods=['POST'])
def sync_manual():
    """Manual sync semua user yang pending"""
    try:
        from models.sync_service import sync_service
        
        def sync_in_background():
            result = sync_service.sync_all_pending_users()
            logger.info(f"Manual user sync result: {result}")
        
        sync_thread = threading.Thread(target=sync_in_background)
        sync_thread.daemon = True
        sync_thread.start()
        
        return jsonify({
            "status": "success",
            "message": "Manual sync started"
        }), 202
        
    except Exception as e:
        logger.error(f"Manual sync error: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Sync failed: {str(e)}"
        }), 500