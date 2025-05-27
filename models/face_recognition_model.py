import cv2 # type: ignore
import numpy as np
import face_recognition # type: ignore
import os
import time
import pickle
import base64
from datetime import datetime
from models.database import User, get_db

class FaceRecognitionModel:
    def __init__(self, known_faces_dir="known_faces", encodings_folder="encodings", 
                 captures_folder="captures", encoding_file="known_faces_encodings.pkl"):
        """
        Inisialisasi model pengenalan wajah
        """
        self.known_encodings = []
        self.known_names = []
        self.known_faces_dir = known_faces_dir
        self.encodings_folder = encodings_folder
        self.captures_folder = captures_folder
        self.known_faces_encoding_file = encoding_file
        
        # Pastikan folder tersedia
        self._ensure_directories()
        
        # Muat wajah yang diketahui saat inisialisasi
        self.load_known_faces_from_database()
        
    def _ensure_directories(self):
        """Memastikan direktori yang diperlukan tersedia"""
        for directory in [self.known_faces_dir, self.encodings_folder, self.captures_folder]:
            if not os.path.exists(directory):
                os.makedirs(directory)
                print(f"Folder {directory} dibuat")
    
    def load_known_faces_from_database(self):
        """Memuat wajah yang diketahui dari database"""
        self.known_encodings = []
        self.known_names = []
        
        db = next(get_db())
        
        try:
            # Ambil semua user yang memiliki face_image_path
            users = db.query(User).filter(User.face_image_path.isnot(None)).all()
            
            for user in users:
                if user.face_image_path and os.path.exists(user.face_image_path):
                    # Load encoding dari file pickle jika ada
                    encoding_file = os.path.join(self.encodings_folder, f"{user.nama_lengkap.lower().replace(' ', '_')}.pkl")
                    
                    if os.path.exists(encoding_file):
                        try:
                            with open(encoding_file, 'rb') as f:
                                face_encoding = pickle.load(f)
                                self.known_encodings.append(face_encoding)
                                self.known_names.append(user.nama_lengkap)
                                print(f"Loaded encoding untuk: {user.nama_lengkap}")
                        except Exception as e:
                            print(f"Error loading encoding untuk {user.nama_lengkap}: {str(e)}")
                            # Jika gagal load encoding, buat ulang dari gambar
                            self._create_encoding_from_image(user.face_image_path, user.nama_lengkap)
                    else:
                        # Buat encoding dari gambar jika belum ada
                        self._create_encoding_from_image(user.face_image_path, user.nama_lengkap)
            
            print(f"Total loaded {len(self.known_names)} wajah dari database: {self.known_names}")
            
        except Exception as e:
            print(f"Error loading faces from database: {str(e)}")
        finally:
            db.close()
    
    def _create_encoding_from_image(self, image_path, user_name):
        """Buat encoding dari gambar dan simpan ke file pickle"""
        try:
            # Baca gambar
            img = cv2.imread(image_path)
            if img is None:
                print(f"Error membaca gambar: {image_path}")
                return False
                
            # Konversi ke RGB untuk face_recognition
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            
            # Deteksi wajah dan dapatkan encoding
            face_locations = face_recognition.face_locations(rgb)
            if len(face_locations) == 0:
                print(f"Tidak ada wajah ditemukan di {image_path}")
                return False
                
            # Ambil encoding wajah pertama yang ditemukan
            face_encoding = face_recognition.face_encodings(rgb, face_locations)[0]
            
            # Simpan encoding dalam format pickle
            encoding_filename = f"{user_name.lower().replace(' ', '_')}.pkl"
            pickle_path = os.path.join(self.encodings_folder, encoding_filename)
            
            with open(pickle_path, 'wb') as f:
                pickle.dump(face_encoding, f)
            
            # Tambahkan ke known faces
            self.known_encodings.append(face_encoding)
            self.known_names.append(user_name)
            
            print(f"Encoding berhasil dibuat untuk: {user_name}")
            return True
            
        except Exception as e:
            print(f"Error saat membuat encoding untuk {user_name}: {str(e)}")
            return False
    
    def register_new_face(self, frame, user_name):
        """Registrasi wajah baru untuk user"""
        try:
            # Cek apakah frame memiliki format yang benar
            if frame is None or len(frame.shape) != 3 or frame.shape[2] != 3:
                return {
                    "status": "error",
                    "message": f"Format gambar tidak valid: {frame.shape if frame is not None else 'None'}"
                }
            
            # Konversi ke RGB untuk face_recognition
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Deteksi lokasi wajah
            face_locations = face_recognition.face_locations(rgb_frame)
            
            # Cek apakah wajah terdeteksi
            if len(face_locations) == 0:
                return {
                    "status": "error",
                    "message": "Tidak ada wajah terdeteksi dalam gambar"
                }
            
            # Ambil wajah terbesar (yang paling dekat)
            if len(face_locations) > 1:
                areas = [(right-left)*(bottom-top) for (top, right, bottom, left) in face_locations]
                max_area_idx = areas.index(max(areas))
                face_locations = [face_locations[max_area_idx]]
            
            # Dapatkan encoding wajah
            face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
            
            if len(face_encodings) == 0:
                return {
                    "status": "error",
                    "message": "Wajah terdeteksi tetapi tidak dapat diproses"
                }
            
            # Cek apakah wajah sudah terdaftar (similarity check)
            face_encoding = face_encodings[0]
            if len(self.known_encodings) > 0:
                matches = face_recognition.compare_faces(self.known_encodings, face_encoding, tolerance=0.5)
                if True in matches:
                    matched_idx = matches.index(True)
                    return {
                        "status": "error",
                        "message": f"Wajah sudah terdaftar atas nama {self.known_names[matched_idx]}"
                    }
            
            # Simpan gambar wajah
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{user_name.lower().replace(' ', '_')}_{timestamp}.jpg"
            face_image_path = os.path.join(self.known_faces_dir, filename)
            
            # Crop wajah dari frame
            top, right, bottom, left = face_locations[0]
            face_image = frame[top:bottom, left:right]
            
            # Resize face image untuk konsistensi
            face_image = cv2.resize(face_image, (150, 150))
            
            # Simpan gambar wajah
            cv2.imwrite(face_image_path, face_image)
            
            # Simpan encoding
            encoding_filename = f"{user_name.lower().replace(' ', '_')}.pkl"
            encoding_path = os.path.join(self.encodings_folder, encoding_filename)
            
            with open(encoding_path, 'wb') as f:
                pickle.dump(face_encoding, f)
            
            # Tambahkan ke known faces
            self.known_encodings.append(face_encoding)
            self.known_names.append(user_name)
            
            # Buat gambar hasil dengan kotak hijau
            result_frame = frame.copy()
            cv2.rectangle(result_frame, (left, top), (right, bottom), (0, 255, 0), 2)
            cv2.putText(result_frame, f"Registered: {user_name}", (left, top - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
            
            # Konversi ke base64 untuk response
            _, buffer = cv2.imencode('.jpg', result_frame)
            result_base64 = base64.b64encode(buffer).decode('utf-8')
            
            return {
                "status": "success",
                "message": f"Wajah {user_name} berhasil didaftarkan",
                "face_image_path": face_image_path,
                "face_image_base64": result_base64
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error dalam registrasi wajah: {str(e)}"
            }
    
    def capture_face_for_registration(self, frame):
        """Capture dan analisis wajah untuk registrasi (tanpa menyimpan)"""
        try:
            # Cek apakah frame memiliki format yang benar
            if frame is None or len(frame.shape) != 3 or frame.shape[2] != 3:
                return {
                    "status": "error",
                    "message": f"Format gambar tidak valid: {frame.shape if frame is not None else 'None'}"
                }
            
            # Konversi ke RGB untuk face_recognition
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Deteksi lokasi wajah
            face_locations = face_recognition.face_locations(rgb_frame)
            
            # Cek apakah wajah terdeteksi
            if len(face_locations) == 0:
                return {
                    "status": "error",
                    "message": "Tidak ada wajah terdeteksi dalam gambar"
                }
            
            # Ambil wajah terbesar (yang paling dekat)
            if len(face_locations) > 1:
                areas = [(right-left)*(bottom-top) for (top, right, bottom, left) in face_locations]
                max_area_idx = areas.index(max(areas))
                face_locations = [face_locations[max_area_idx]]
            
            # Dapatkan encoding wajah
            face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
            
            if len(face_encodings) == 0:
                return {
                    "status": "error",
                    "message": "Wajah terdeteksi tetapi tidak dapat diproses"
                }
            
            # Cek apakah wajah sudah terdaftar
            face_encoding = face_encodings[0]
            if len(self.known_encodings) > 0:
                matches = face_recognition.compare_faces(self.known_encodings, face_encoding, tolerance=0.5)
                if True in matches:
                    matched_idx = matches.index(True)
                    return {
                        "status": "duplicate",
                        "message": f"Wajah sudah terdaftar atas nama {self.known_names[matched_idx]}"
                    }
            
            # Buat gambar hasil dengan kotak hijau
            result_frame = frame.copy()
            top, right, bottom, left = face_locations[0]
            cv2.rectangle(result_frame, (left, top), (right, bottom), (0, 255, 0), 2)
            cv2.putText(result_frame, "Wajah Terdeteksi", (left, top - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
            
            # Konversi ke base64 untuk response
            _, buffer = cv2.imencode('.jpg', result_frame)
            result_base64 = base64.b64encode(buffer).decode('utf-8')
            
            # Crop wajah untuk preview
            face_crop = frame[top:bottom, left:right]
            face_crop = cv2.resize(face_crop, (150, 150))
            _, face_buffer = cv2.imencode('.jpg', face_crop)
            face_base64 = base64.b64encode(face_buffer).decode('utf-8')
            
            return {
                "status": "success",
                "message": "Wajah berhasil terdeteksi dan siap untuk didaftarkan",
                "face_image_base64": result_base64,
                "face_crop_base64": face_base64,
                "face_location": {
                    "top": top,
                    "right": right,
                    "bottom": bottom,
                    "left": left
                }
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error dalam capture wajah: {str(e)}"
            }
    
    def process_face_recognition(self, frame):
        """
        Memproses pengenalan wajah (method existing yang sudah ada)
        """
        result = {
            "status": None,
            "message": None,
            "face_data": None
        }
        
        try:
            # Cek apakah frame memiliki format yang benar
            if frame is None or len(frame.shape) != 3 or frame.shape[2] != 3:
                result["status"] = "error"
                result["message"] = f"Format gambar tidak valid: {frame.shape if frame is not None else 'None'}"
                return result
                
            # Buat nama file dengan timestamp untuk menyimpan hasil
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            orig_filepath = os.path.join(self.captures_folder, f"{timestamp}_capture.jpg")
            
            # Simpan gambar original
            cv2.imwrite(orig_filepath, frame)
            
            # Konversi ke RGB untuk face_recognition
            try:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            except Exception as e:
                result["status"] = "error"
                result["message"] = f"Gagal mengkonversi gambar: {str(e)}"
                return result
            
            # Deteksi lokasi wajah
            face_locations = face_recognition.face_locations(rgb_frame)
            
            # Cek apakah wajah terdeteksi
            if len(face_locations) == 0:
                result["status"] = "error"
                result["message"] = "Tidak ada wajah terdeteksi dalam gambar"
                # Hapus file gambar yang tidak ada wajah
                if os.path.exists(orig_filepath):
                    os.remove(orig_filepath)
                return result
            
            # Ambil maksimal 3 wajah terbesar dalam frame untuk efisiensi
            if len(face_locations) > 3:
                areas = [(right-left)*(bottom-top) for (top, right, bottom, left) in face_locations]
                # Ambil 3 wajah dengan area terbesar
                face_locations = [loc for _, loc in sorted(zip(areas, face_locations), reverse=True)[:3]]
            
            # Dapatkan encoding wajah
            face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
            
            if len(face_encodings) == 0:
                result["status"] = "error"
                result["message"] = "Wajah terdeteksi tetapi tidak dapat diproses"
                return result
            
            # Untuk setiap wajah terdeteksi
            result_frame = frame.copy()
            recognized = False
            recognized_name = ""
            tolerance = 0.5  # Toleransi untuk pengenalan wajah (nilai lebih rendah = lebih ketat)
            
            for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
                # Periksa apakah wajah cocok dengan wajah yang dikenal
                matches = face_recognition.compare_faces(self.known_encodings, face_encoding, tolerance=tolerance)
                name = "Unknown"
                
                if True in matches:
                    idx = matches.index(True)
                    name = self.known_names[idx]
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
                
            new_filepath = os.path.join(self.captures_folder, new_filename)
            
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
                result["status"] = "success"
                result["message"] = f"Selamat datang {recognized_name}"
                result["face_data"] = result_base64
            else:
                result["status"] = "unknown"
                result["message"] = "Anda tidak terdaftar dalam sistem"
                result["face_data"] = result_base64
                
        except Exception as e:
            result["status"] = "error"
            result["message"] = f"Error dalam pemrosesan: {str(e)}"
            
        return result
    
    def add_face(self, image_data, name):
        """
        Menambahkan wajah baru ke database (method existing yang sudah ada)
        """
        try:
            # Buat nama file dari nama yang diberikan
            filename = f"{name}.jpg"
            filepath = os.path.join(self.known_faces_dir, filename)
            
            # Simpan file
            with open(filepath, 'wb') as f:
                f.write(image_data)
            
            # Konversi ke encoding dan simpan
            success = self._create_encoding_from_image(filepath, name)
            
            if success:
                # Reload known faces
                self.load_known_faces_from_database()
                return {"status": "success", "message": f"Wajah {name} berhasil ditambahkan"}
            else:
                return {"status": "error", "message": "Gagal mengkonversi gambar ke encoding"}
        except Exception as e:
            return {"status": "error", "message": f"Error saat menambahkan wajah: {str(e)}"}
    
    def clean_old_captures(self, max_age_days=7):
        """
        Membersihkan file capture lama
        """
        try:
            now = time.time()
            count = 0
            for f in os.listdir(self.captures_folder):
                path = os.path.join(self.captures_folder, f)
                if os.path.isfile(path) and now - os.path.getmtime(path) > max_age_days * 24 * 3600:
                    os.remove(path)
                    count += 1
            if count > 0:
                print(f"Membersihkan {count} file capture lama")
        except Exception as e:
            print(f"Error saat membersihkan file lama: {str(e)}")
    
    def reload_known_faces(self):
        """Reload semua wajah yang dikenal dari database"""
        self.load_known_faces_from_database()
        return {
            "status": "success", 
            "message": f"Berhasil memuat {len(self.known_names)} wajah",
            "known_faces": self.known_names
        }