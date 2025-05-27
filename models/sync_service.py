# models/sync_service.py
import requests
import json
import base64
import os
from datetime import datetime
from models.database import get_db, User, Book, Borrowing, WebhookLog
from dotenv import load_dotenv
import logging
import time

load_dotenv()

# Configuration
LARAVEL_URL = os.getenv('LARAVEL_URL')  # No default to ensure explicit configuration
SYNC_API_KEY = os.getenv('LARAVEL_API_KEY')  # No default
SYNC_TIMEOUT = int(os.getenv('SYNC_TIMEOUT', '10'))  # 10 seconds timeout
MAX_RETRIES = int(os.getenv('MAX_RETRIES', '3'))

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SyncService:
    def __init__(self):
        if not LARAVEL_URL:
            raise ValueError("LARAVEL_URL environment variable is not configured")
        if not SYNC_API_KEY:
            raise ValueError("LARAVEL_API_KEY environment variable is not configured")
            
        self.base_url = LARAVEL_URL.rstrip('/')
        self.api_key = SYNC_API_KEY
        self.timeout = SYNC_TIMEOUT
        self.max_retries = MAX_RETRIES
        
    def _make_request(self, method, endpoint, data=None, retry_count=0):
        """Make HTTP request TANPA webhook logging untuk avoid database issue"""
        url = f"{self.base_url}{endpoint}"
        headers = {
            'Content-Type': 'application/json',
            'X-API-Key': self.api_key,
            'User-Agent': 'Flask-IoT-Device/1.0'
        }
        
        logger.info(f"Making {method} request to: {url}")
        logger.info(f"Headers: {list(headers.keys())}")
        
        if data:
            payload_size = len(json.dumps(data))
            logger.info(f"Payload size: {payload_size} bytes")
        
        try:
            if method.upper() == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=self.timeout)
            elif method.upper() == 'GET':
                response = requests.get(url, headers=headers, timeout=self.timeout)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            logger.info(f"Response status: {response.status_code}")
            
            # Log response (max 1000 chars untuk avoid spam)
            response_text = response.text
            if len(response_text) > 1000:
                logger.info(f"Response content (truncated): {response_text[:1000]}...")
            else:
                logger.info(f"Response content: {response_text}")
            
            # SKIP WEBHOOK LOGGING UNTUK AVOID DATABASE ISSUE
            # self._log_webhook_request(endpoint, method, data, response)
            
            return {
                'success': True,
                'status_code': response.status_code,
                'data': response.json() if response.content else {},
                'response': response
            }
            
        except requests.exceptions.Timeout:
            logger.warning(f"Request timeout to {url}")
            if retry_count < self.max_retries:
                time.sleep(2 ** retry_count)  # Exponential backoff
                return self._make_request(method, endpoint, data, retry_count + 1)
            return {'success': False, 'error': 'Request timeout', 'retry_count': retry_count}
            
        except requests.exceptions.ConnectionError:
            logger.warning(f"Connection error to {url}")
            if retry_count < self.max_retries:
                time.sleep(2 ** retry_count)
                return self._make_request(method, endpoint, data, retry_count + 1)
            return {'success': False, 'error': 'Connection error', 'retry_count': retry_count}
            
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _log_webhook_request(self, endpoint, method, payload, response):
        """Log webhook request untuk debugging"""
        db = next(get_db())
        try:
            webhook_log = WebhookLog(
                webhook_type='outgoing',
                endpoint=endpoint,
                method=method.upper(),
                payload=json.dumps(payload) if payload else None,
                response=response.text if response else None,
                status_code=response.status_code if response else None,
                success=response.status_code < 400 if response else False,
                error_message=None if response and response.status_code < 400 else 'Request failed'
            )
            db.add(webhook_log)
            db.commit()
        except Exception as e:
            logger.error(f"Failed to log webhook request: {str(e)}")
        finally:
            db.close()
    
    # QUICK FIX - Update sync_service.py

    def sync_user_to_laravel(self, user_id):
        """
        Sync user data ke Laravel - KIRIM STRING KOSONG UNTUK FACE_IMAGE_PATH_BASE64
        """
        db = next(get_db())
        
        try:
            # Ambil data user
            user = db.query(User).get(user_id)
            if not user:
                logger.error(f"User {user_id} tidak ditemukan di database")
                return {'success': False, 'error': 'User not found'}
            
            logger.info(f"Syncing user: {user.nama_lengkap} ({user.email})")
            
            # Cek apakah ada face image
            has_face_image = bool(user.face_image_path and os.path.exists(user.face_image_path))
            
            if has_face_image:
                logger.info(f"User has face image: {user.face_image_path}")
            else:
                logger.info("User has no face image")
            
            # Siapkan payload SESUAI DENGAN LARAVEL API YANG ADA
            payload = {
                'local_user_id': user.id,
                'nama_lengkap': user.nama_lengkap,
                'email': user.email,
                'role': user.role,
                'face_image_path_base64': "NULL",  # KIRIM STRING KOSONG (required field)
                'created_at': user.created_at.isoformat() if user.created_at else None,
                'updated_at': user.updated_at.isoformat() if user.updated_at else None,
                # TAMBAHAN FIELD UNTUK INFO (jika Laravel mau terima)
                'has_face_image': has_face_image,
                'face_image_path': user.face_image_path or ""
            }
            
            payload_size = len(json.dumps(payload))
            logger.info(f"Payload size: {payload_size} bytes (with empty base64 field)")
            
            # Kirim ke Laravel
            result = self._make_request('POST', '/api/sync/users/from-flask', payload)
            
            if result['success'] and result['status_code'] in [200, 201]:
                # Update user sebagai synced
                user.synced_to_server = True
                
                # Simpan Laravel ID jika ada
                response_data = result['data']
                if 'laravel_user_id' in response_data:
                    user.laravel_id = response_data['laravel_user_id']
                    logger.info(f"Laravel user ID saved: {user.laravel_id}")
                
                user.updated_at = datetime.now()
                db.commit()
                
                logger.info(f"✅ User {user_id} synced successfully to Laravel")
                return {
                    'success': True, 
                    'message': 'User synced successfully (without image)',
                    'laravel_user_id': response_data.get('laravel_user_id')
                }
            
            elif result['success'] and result['status_code'] == 409:
                # User sudah ada di Laravel
                user.synced_to_server = True
                db.commit()
                logger.warning(f"User {user_id} already exists in Laravel")
                return {'success': True, 'message': 'User already exists in Laravel'}
            
            else:
                error_msg = result.get('error', 'Unknown error')
                logger.error(f"❌ Failed to sync user {user_id}: {error_msg}")
                return {'success': False, 'error': error_msg}
                
        except Exception as e:
            db.rollback()
            logger.error(f"Exception syncing user {user_id}: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {'success': False, 'error': str(e)}
        finally:
            db.close()
    def sync_borrowing_to_laravel(self, borrowing_id):
        """
        Sync borrowing transaction ke Laravel
        """
        db = next(get_db())
        
        try:
            # Ambil data borrowing dengan join
            borrowing = db.query(Borrowing).filter(Borrowing.id_peminjaman == borrowing_id).first()
            if not borrowing:
                return {'success': False, 'error': 'Borrowing not found'}
            
            # Ambil data user dan book
            user = db.query(User).get(borrowing.id_user)
            book = db.query(Book).get(borrowing.id_buku)
            
            if not user or not book:
                return {'success': False, 'error': 'User or book not found'}
            
            # Siapkan payload
            payload = {
                'local_borrowing_id': borrowing.id_peminjaman,
                'local_user_id': borrowing.id_user,
                'local_book_id': borrowing.id_buku,
                'user_email': user.email,
                'book_rfid': book.rfid_tag,
                'book_title': book.judul,
                'tanggal_pinjam': borrowing.tanggal_pinjam.isoformat() if borrowing.tanggal_pinjam else None,
                'tanggal_kembali': borrowing.tanggal_kembali.isoformat() if borrowing.tanggal_kembali else None,
                'status': borrowing.status,
                'created_at': borrowing.created_at.isoformat() if borrowing.created_at else None
            }
            
            # Kirim ke Laravel
            result = self._make_request('POST', '/api/sync/borrowings/from-flask', payload)
            
            if result['success'] and result['status_code'] in [200, 201]:
                # Update borrowing sebagai synced
                borrowing.synced_to_server = True
                
                # Simpan Laravel ID jika ada
                response_data = result['data']
                if 'laravel_borrowing_id' in response_data:
                    borrowing.laravel_id = response_data['laravel_borrowing_id']
                
                borrowing.updated_at = datetime.now()
                db.commit()
                
                logger.info(f"Borrowing {borrowing_id} synced successfully to Laravel")
                return {
                    'success': True, 
                    'message': 'Borrowing synced successfully',
                    'laravel_borrowing_id': response_data.get('laravel_borrowing_id')
                }
            
            else:
                error_msg = result.get('error', 'Unknown error')
                logger.error(f"Failed to sync borrowing {borrowing_id}: {error_msg}")
                return {'success': False, 'error': error_msg}
                
        except Exception as e:
            db.rollback()
            logger.error(f"Exception syncing borrowing {borrowing_id}: {str(e)}")
            return {'success': False, 'error': str(e)}
        finally:
            db.close()
    
    def sync_all_pending_users(self):
        """Sync semua user yang belum di-sync"""
        db = next(get_db())
        
        try:
            # Ambil semua user yang belum synced
            pending_users = db.query(User).filter(User.synced_to_server == False).all()
            
            results = {
                'total': len(pending_users),
                'success': 0,
                'failed': 0,
                'errors': []
            }
            
            for user in pending_users:
                result = self.sync_user_to_laravel(user.id)
                if result['success']:
                    results['success'] += 1
                else:
                    results['failed'] += 1
                    results['errors'].append({
                        'user_id': user.id,
                        'error': result['error']
                    })
                
                # Jeda kecil untuk tidak overload server
                time.sleep(0.5)
            
            logger.info(f"Bulk user sync completed: {results['success']} success, {results['failed']} failed")
            return results
            
        except Exception as e:
            logger.error(f"Exception in bulk user sync: {str(e)}")
            return {'success': False, 'error': str(e)}
        finally:
            db.close()
    
    def sync_all_pending_borrowings(self):
        """Sync semua borrowing yang belum di-sync"""
        db = next(get_db())
        
        try:
            # Ambil semua borrowing yang belum synced
            pending_borrowings = db.query(Borrowing).filter(Borrowing.synced_to_server == False).all()
            
            results = {
                'total': len(pending_borrowings),
                'success': 0,
                'failed': 0,
                'errors': []
            }
            
            for borrowing in pending_borrowings:
                result = self.sync_borrowing_to_laravel(borrowing.id_peminjaman)
                if result['success']:
                    results['success'] += 1
                else:
                    results['failed'] += 1
                    results['errors'].append({
                        'borrowing_id': borrowing.id_peminjaman,
                        'error': result['error']
                    })
                
                # Jeda kecil untuk tidak overload server
                time.sleep(0.5)
            
            logger.info(f"Bulk borrowing sync completed: {results['success']} success, {results['failed']} failed")
            return results
            
        except Exception as e:
            logger.error(f"Exception in bulk borrowing sync: {str(e)}")
            return {'success': False, 'error': str(e)}
        finally:
            db.close()
    
    def test_connection(self):
        """Test koneksi ke Laravel"""
        test_payload = {
            'test_message': 'Hello from Flask IoT Device',
            'timestamp': datetime.now().isoformat() + 'Z',
            'test_id': f'flask_test_{int(time.time())}'
        }
        
        result = self._make_request('POST', '/api/webhook/test', test_payload)
        
        if result['success'] and result['status_code'] == 200:
            logger.info("Connection test to Laravel successful")
            return {'success': True, 'message': 'Connection successful', 'response': result['data']}
        else:
            error_msg = result.get('error', 'Connection failed')
            logger.error(f"Connection test to Laravel failed: {error_msg}")
            return {'success': False, 'error': error_msg}

# Global instance
sync_service = SyncService()