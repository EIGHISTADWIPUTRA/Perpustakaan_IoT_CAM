import cv2 # type: ignore
import requests
import numpy as np
import os
from dotenv import load_dotenv
import threading
import time

class ESP32Manager:
    def __init__(self):
        """
        Inisialisasi manajer ESP32-CAM
        """
        load_dotenv()
        self.ip = os.environ.get('ESP32_IP')
        self.stream_port = os.environ.get('ESP32_STREAM_PORT')
        self.capture_path = os.environ.get('ESP32_CAPTURE_PATH')
        self.stream_url = f"http://{self.ip}:{self.stream_port}/stream"
        self.capture_url = f"http://{self.ip}{self.capture_path}"
        self.camera = None
        self.frame = None  # Frame terakhir yang diterima
        self._stream_thread = None
        self._running = False
    
    def get_stream_url(self):
        """
        Mendapatkan URL untuk streaming
        """
        return self.stream_url
        
    def get_capture_url(self):
        """
        Mendapatkan URL untuk mengambil gambar
        """
        return self.capture_url
    
    def update_config(self, config):
        """
        Memperbarui konfigurasi ESP32-CAM
        """
        self.ip = config.get('ip', self.ip)
        self.stream_port = config.get('stream_port', self.stream_port)
        self.capture_path = config.get('capture_path', self.capture_path)
        
        # Update URL
        self.stream_url = f"http://{self.ip}:{self.stream_port}/stream"
        self.capture_url = f"http://{self.ip}{self.capture_path}"
        
        # Hentikan thread streaming lama dan reset kamera
        self.stop_streaming()
        
        return {
            'ip': self.ip,
            'stream_port': self.stream_port,
            'capture_path': self.capture_path,
            'stream_url': self.stream_url,
            'capture_url': self.capture_url
        }
    
    def init_video_stream(self):
        """
        Inisialisasi kamera untuk streaming
        """
        if self.camera is None:
            # Gunakan FFMPEG backend untuk performa lebih baik
            self.camera = cv2.VideoCapture(self.stream_url, cv2.CAP_FFMPEG)
            # Kurangi buffer untuk menghindari lag
            self.camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return self.camera

    def _stream_worker(self):
        """Thread worker untuk terus mengambil frame dan menyimpannya di buffer"""
        cap = self.init_video_stream()
        while self._running:
            success, frame = cap.read()
            if success:
                self.frame = frame
            else:
                # Coba inisialisasi ulang jika gagal membaca frame
                try:
                    cap.release()
                except Exception:
                    pass
                self.camera = None
                time.sleep(0.1)
                cap = self.init_video_stream()

    def start_streaming(self):
        """Memulai thread streaming jika belum berjalan"""
        if self._stream_thread is None or not self._stream_thread.is_alive():
            self._running = True
            self._stream_thread = threading.Thread(target=self._stream_worker, daemon=True)
            self._stream_thread.start()

    def stop_streaming(self):
        """Menghentikan thread streaming"""
        self._running = False
        if self._stream_thread is not None:
            self._stream_thread.join(timeout=1)
            self._stream_thread = None
        self.release_camera()

    def get_frame_from_stream(self):
        """
        Mengambil frame terbaru dari buffer stream
        """
        # Pastikan thread streaming berjalan
        self.start_streaming()
        # Jika belum ada frame, coba ambil langsung satu kali
        if self.frame is None and self.camera is not None:
            success, frame = self.camera.read()
            if success:
                self.frame = frame
        return self.frame
    
    def get_frame_from_capture(self):
        """
        Mengambil frame langsung dari endpoint capture
        """
        try:
            img_resp = requests.get(self.capture_url, timeout=2)
            if img_resp.status_code != 200:
                print(f"Error mendapatkan gambar dari ESP32: {img_resp.status_code}")
                return None
                
            img_arr = np.array(bytearray(img_resp.content), dtype=np.uint8)
            frame = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
            
            if frame is None:
                print("Frame kosong dari kamera")
                return None
                
            # Pastikan frame memiliki 3 channel (BGR)
            if len(frame.shape) != 3 or frame.shape[2] != 3:
                print(f"Format frame tidak valid: {frame.shape}")
                return None
                
            return frame
        except Exception as e:
            print(f"Error saat mengambil gambar dari ESP32: {str(e)}")
            return None
    
    def get_config(self):
        """
        Mendapatkan konfigurasi ESP32 saat ini
        """
        return {
            'ip': self.ip,
            'stream_port': self.stream_port,
            'capture_path': self.capture_path,
            'stream_url': self.stream_url,
            'capture_url': self.capture_url
        }
    
    def check_connection(self):
        """
        Mengecek koneksi ke ESP32-CAM
        """
        try:
            response = requests.get(self.capture_url, timeout=1)
            return response.status_code == 200
        except Exception:
            return False

    def get_control_url(self):
        """Mendapatkan URL halaman pengaturan kamera bawaan ESP32-CAM"""
        return f"http://{self.ip}"  # Halaman kontrol biasanya di root ( / )

    def release_camera(self):
        """
        Melepaskan kamera
        """
        if self.camera is not None:
            self.camera.release()
            self.camera = None
    
    def _get_frame_from_stream_legacy(self):
        """
        Mengambil frame dari stream video
        """
        if self.camera is None:
            self.init_video_stream()
            
        success, frame = self.camera.read()
        if not success:
            # Coba sambungkan kembali
            self.camera.release()
            self.camera = None
            self.init_video_stream()
            success, frame = self.camera.read()
            
            if not success:
                return None
                
        return frame 