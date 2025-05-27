# models/sync_manager.py
import requests
import json
import os
from datetime import datetime
from dotenv import load_dotenv
from models.database import SyncQueue, User, Book, Borrowing, get_db
from sqlalchemy.orm import Session # type: ignore
import base64

load_dotenv()

class SyncManager:    
    def __init__(self):
        self.laravel_url = os.getenv('LARAVEL_URL')
        self.api_key = os.getenv('LARAVEL_API_KEY')
        
        if not self.laravel_url:
            raise ValueError("LARAVEL_URL environment variable is not configured")
        if not self.api_key:
            raise ValueError("LARAVEL_API_KEY environment variable is not configured")
        
    def sync_to_laravel(self):
        """Sinkronisasi semua data yang belum ter-sync ke Laravel"""
        db = next(get_db())
        
        try:
            # Ambil semua data yang belum di-sync
            pending_syncs = db.query(SyncQueue).filter(SyncQueue.synced == False).all()
            
            sync_results = {
                'success': 0,
                'failed': 0,
                'errors': []
            }
            
            for sync_item in pending_syncs:
                try:
                    result = self._sync_single_item(sync_item, db)
                    if result:
                        # Mark as synced
                        sync_item.synced = True
                        sync_item.synced_at = datetime.now()
                        sync_results['success'] += 1
                    else:
                        sync_results['failed'] += 1
                        sync_results['errors'].append(f"Failed to sync {sync_item.table_name} ID {sync_item.record_id}")
                        
                except Exception as e:
                    sync_results['failed'] += 1
                    sync_results['errors'].append(f"Error syncing {sync_item.table_name} ID {sync_item.record_id}: {str(e)}")
            
            db.commit()
            return sync_results
            
        except Exception as e:
            db.rollback()
            return {
                'success': 0,
                'failed': len(pending_syncs) if 'pending_syncs' in locals() else 0,
                'errors': [f"Sync failed: {str(e)}"]
            }
        finally:
            db.close()
    
    def _sync_single_item(self, sync_item, db):
        """Sync single item berdasarkan table dan action"""
        
        if sync_item.table_name == 'users':
            return self._sync_user(sync_item, db)
        elif sync_item.table_name == 'borrowings':
            return self._sync_borrowing(sync_item, db)
        elif sync_item.table_name == 'books':
            return self._sync_book(sync_item, db)
        
        return False
    
    def _sync_user(self, sync_item, db):
        """Sync user data ke Laravel"""
        try:
            # Get user data
            user = db.query(User).get(sync_item.record_id)
            if not user:
                return False
            
            # Prepare user data
            user_data = {
                'nama_lengkap': user.nama_lengkap,
                'email': user.email,
                'role': user.role,
                'local_user_id': user.id
            }
            
            # Add face image if exists
            if user.face_image_path and os.path.exists(user.face_image_path):
                with open(user.face_image_path, 'rb') as img_file:
                    img_base64 = base64.b64encode(img_file.read()).decode('utf-8')
                    user_data['face_image'] = img_base64
                    user_data['face_image_name'] = os.path.basename(user.face_image_path)
            
            # Send to Laravel
            response = requests.post(
                f"{self.laravel_url}/api/sync/users",
                json=user_data,
                headers={
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json'
                },
                timeout=30
            )
            
            if response.status_code == 200:
                # Update user dengan server_user_id jika ada
                response_data = response.json()
                if 'user_id' in response_data:
                    user.synced_to_server = True
                return True
            
            return False
            
        except Exception as e:
            print(f"Error syncing user: {str(e)}")
            return False
    
    def _sync_borrowing(self, sync_item, db):
        """Sync borrowing data ke Laravel"""
        try:
            data = json.loads(sync_item.data)
            
            # Send to Laravel
            response = requests.post(
                f"{self.laravel_url}/api/sync/borrowings",
                json=data,
                headers={
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json'
                },
                timeout=30
            )
            
            return response.status_code == 200
            
        except Exception as e:
            print(f"Error syncing borrowing: {str(e)}")
            return False
    
    def _sync_book(self, sync_item, db):
        """Sync book data ke Laravel (jika ada update stok)"""
        try:
            data = json.loads(sync_item.data)
            
            response = requests.post(
                f"{self.laravel_url}/api/sync/books",
                json=data,
                headers={
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json'
                },
                timeout=30
            )
            
            return response.status_code == 200
            
        except Exception as e:
            print(f"Error syncing book: {str(e)}")
            return False
    
    def sync_from_laravel(self):
        """Ambil data terbaru dari Laravel"""
        try:
            # Get new users from Laravel
            self._sync_users_from_laravel()
            
            # Get new books from Laravel
            self._sync_books_from_laravel()
            
            return {"status": "success", "message": "Data berhasil di-sync dari Laravel"}
            
        except Exception as e:
            return {"status": "error", "message": f"Error syncing from Laravel: {str(e)}"}
    
    def _sync_users_from_laravel(self):
        """Ambil user baru dari Laravel"""
        db = next(get_db())
        
        try:
            response = requests.get(
                f"{self.laravel_url}/api/sync/users/new",
                headers={'Authorization': f'Bearer {self.api_key}'},
                timeout=30
            )
            
            if response.status_code == 200:
                users_data = response.json()
                
                for user_data in users_data:
                    # Check if user already exists
                    existing_user = db.query(User).filter(User.email == user_data['email']).first()
                    
                    if not existing_user:
                        # Create new user
                        new_user = User(
                            nama_lengkap=user_data['nama_lengkap'],
                            email=user_data['email'],
                            role=user_data.get('role', 'member'),
                            synced_to_server=True
                        )
                        
                        # Save face image if provided
                        if 'face_image' in user_data:
                            face_image_path = self._save_face_image(
                                user_data['face_image'], 
                                user_data['nama_lengkap']
                            )
                            new_user.face_image_path = face_image_path
                        
                        db.add(new_user)
                
                db.commit()
                
        except Exception as e:
            db.rollback()
            print(f"Error syncing users from Laravel: {str(e)}")
        finally:
            db.close()
    
    def _sync_books_from_laravel(self):
        """Ambil buku baru dari Laravel"""
        db = next(get_db())
        
        try:
            response = requests.get(
                f"{self.laravel_url}/api/sync/books/new",
                headers={'Authorization': f'Bearer {self.api_key}'},
                timeout=30
            )
            
            if response.status_code == 200:
                books_data = response.json()
                
                for book_data in books_data:
                    # Check if book already exists
                    existing_book = db.query(Book).filter(Book.rfid_tag == book_data['rfid_tag']).first()
                    
                    if not existing_book:
                        # Create new book
                        new_book = Book(
                            judul=book_data['judul'],
                            penulis=book_data['penulis'],
                            penerbit=book_data.get('penerbit', ''),
                            tahun_terbit=book_data.get('tahun_terbit', 2024),
                            stok=book_data.get('stok', 1),
                            rfid_tag=book_data['rfid_tag']
                        )
                        
                        db.add(new_book)
                
                db.commit()
                
        except Exception as e:
            db.rollback()
            print(f"Error syncing books from Laravel: {str(e)}")
        finally:
            db.close()
    
    def _save_face_image(self, base64_image, user_name):
        """Simpan gambar wajah dari base64"""
        try:
            # Decode base64 image
            image_data = base64.b64decode(base64_image)
            
            # Create filename
            filename = f"{user_name.lower().replace(' ', '_')}.jpg"
            filepath = os.path.join('known_faces', filename)
            
            # Ensure directory exists
            os.makedirs('known_faces', exist_ok=True)
            
            # Save image
            with open(filepath, 'wb') as f:
                f.write(image_data)
            
            return filepath
            
        except Exception as e:
            print(f"Error saving face image: {str(e)}")
            return None
    
    def manual_sync(self):
        """Manual trigger untuk sync"""
        print("Starting manual sync...")
        
        # Sync to Laravel
        to_laravel_result = self.sync_to_laravel()
        print(f"Sync to Laravel - Success: {to_laravel_result['success']}, Failed: {to_laravel_result['failed']}")
        
        # Sync from Laravel
        from_laravel_result = self.sync_from_laravel()
        print(f"Sync from Laravel: {from_laravel_result['message']}")
        
        return {
            'to_laravel': to_laravel_result,
            'from_laravel': from_laravel_result
        }