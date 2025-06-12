# models/book_model.py
from datetime import datetime, timedelta
from models.database import Book, Borrowing, User, SyncQueue, get_db
from sqlalchemy.orm import Session # type: ignore
from models.sync_service import sync_service  # Impor sync_service untuk sinkronisasi langsung
import json
import logging

# Setup logging
logger = logging.getLogger(__name__)

class BookModel:
    def __init__(self):
        """Inisialisasi model buku dengan SQLAlchemy"""
        pass
    
    def get_book_by_rfid(self, rfid_id):
        """Mendapatkan data buku berdasarkan ID RFID"""
        # Get database session
        db = next(get_db())
        
        try:
            # Query buku berdasarkan RFID
            book = db.query(Book).filter(Book.rfid_tag == rfid_id).first()
            
            if not book:
                return {
                    "status": "error",
                    "message": "RFID tidak terdaftar di sistem"
                }
            
            # Cek apakah buku sedang dipinjam
            active_borrowing = db.query(Borrowing).filter(
                Borrowing.id_buku == book.id_buku,
                Borrowing.status == 'dipinjam'
            ).first()
            
            # Set tanggal peminjaman dan pengembalian
            today = datetime.now()
            return_date = today + timedelta(days=7)
            
            # Format response
            response = {
                "status": "success",
                "message": f"Buku '{book.judul}' berhasil diidentifikasi",
                "book_data": {
                    "id": book.id_buku,
                    "judul": book.judul,
                    "penulis": book.penulis,
                    "tahun": book.tahun_terbit,
                    "penerbit": book.penerbit,
                    "stok": book.stok,
                    "status": "dipinjam" if active_borrowing else "tersedia"
                },
                "peminjaman": {
                    "tanggal_pinjam": today.strftime("%Y-%m-%d"),
                    "tanggal_kembali": return_date.strftime("%Y-%m-%d")
                }
            }
            
            return response
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error database: {str(e)}"
            }
        finally:
            db.close()
    
    def proses_peminjaman(self, rfid_id, username):
        """Proses peminjaman buku"""
        db = next(get_db())
        
        try:
            # Cari user berdasarkan nama
            user = db.query(User).filter(User.nama_lengkap == username).first()
            if not user:
                return {
                    "status": "error",
                    "message": f"User {username} tidak terdaftar"
                }
            
            # Cek apakah user sudah pinjam buku lain
            active_borrowing = db.query(Borrowing).filter(
                Borrowing.id_user == user.id,
                Borrowing.status == 'dipinjam'
            ).first()
            
            if active_borrowing:
                borrowed_book = db.query(Book).get(active_borrowing.id_buku)
                return {
                    "status": "error",
                    "message": f"User {username} masih meminjam '{borrowed_book.judul}'. Kembalikan dulu."
                }
            
            # Cari buku berdasarkan RFID
            book = db.query(Book).filter(Book.rfid_tag == rfid_id).first()
            if not book:
                return {
                    "status": "error",
                    "message": "Buku tidak ditemukan"
                }
            
            # Cek stok
            if book.stok <= 0:
                return {
                    "status": "error",
                    "message": f"Stok buku '{book.judul}' habis"
                }
            
            # Proses peminjaman
            borrowing = Borrowing(
                id_user=user.id,
                id_buku=book.id_buku,
                tanggal_pinjam=datetime.now(),
                tanggal_kembali=datetime.now() + timedelta(days=7),
                status='dipinjam'
            )
            
            # Kurangi stok
            book.stok -= 1
            
            # Simpan ke database
            db.add(borrowing)
            db.commit()
            
            # Tambah ke sync queue
            sync_data = {
                "id_user": user.id,
                "id_buku": book.id_buku,
                "tanggal_pinjam": borrowing.tanggal_pinjam.isoformat(),
                "tanggal_kembali": borrowing.tanggal_kembali.isoformat(),
                "status": "dipinjam"
            }
            
            sync_queue = SyncQueue(
                table_name='borrowings',
                record_id=borrowing.id_peminjaman,
                action='create',
                data=json.dumps(sync_data)
            )
            db.add(sync_queue)
            db.commit()
            
            # Simpan ID peminjaman untuk digunakan dalam thread terpisah
            borrowing_id_for_sync = borrowing.id_peminjaman
            
            # Kirim data peminjaman langsung ke Laravel
            try:
                # Gunakan thread terpisah agar tidak menghambat respons ke user
                import threading
                
                def sync_in_background():
                    try:
                        # Gunakan session baru dalam thread ini untuk menghindari konflik
                        # Simpan hasil ke variabel lokal, bukan global
                        sync_result = sync_service.sync_borrowing_to_laravel(borrowing_id_for_sync)
                        if sync_result['success']:
                            logger.info(f"Peminjaman ID {borrowing_id_for_sync} berhasil disinkronkan ke Laravel")
                        else:
                            logger.warning(f"Gagal sinkronisasi peminjaman ID {borrowing_id_for_sync}: {sync_result.get('error', 'Unknown error')}")
                    except Exception as sync_err:
                        logger.error(f"Exception in sync thread: {str(sync_err)}")
                
                # Gunakan Timer untuk menjalankan sinkronisasi setelah response dikembalikan
                # Ini mencegah konflik session database
                threading.Timer(2.0, sync_in_background).start()
                
            except Exception as sync_error:
                # Jika gagal sinkronisasi, tidak menggagalkan proses peminjaman
                logger.error(f"Gagal mengirim data peminjaman ke Laravel: {str(sync_error)}")
            
            # Log data book untuk debugging
            logger.info(f"Book data: ID={book.id_buku}, Judul={book.judul}, Penulis={book.penulis}")
            logger.info(f"Borrowing data: ID={borrowing.id_peminjaman}, Status={borrowing.status}")
            
            return {
                "status": "success",
                "message": f"Buku '{book.judul}' berhasil dipinjam oleh {username}",
                "book_data": {
                    "id": book.id_buku,
                    "judul": book.judul,
                    "penulis": book.penulis
                },
                "peminjaman": {
                    "id_peminjaman": borrowing.id_peminjaman,
                    "tanggal_pinjam": borrowing.tanggal_pinjam.strftime("%Y-%m-%d"),
                    "tanggal_kembali": borrowing.tanggal_kembali.strftime("%Y-%m-%d")
                }
            }
            
        except Exception as e:
            db.rollback()
            return {
                "status": "error",
                "message": f"Error: {str(e)}"
            }
        finally:
            try:
                db.close()
            except Exception as close_err:
                logger.warning(f"Error closing database connection: {str(close_err)}")
    
    def kembalikan_buku(self, username):
        """Mengembalikan buku yang dipinjam oleh pengguna"""
        db = next(get_db())
        
        try:
            # Cari user
            user = db.query(User).filter(User.nama_lengkap == username).first()
            if not user:
                return {
                    "status": "error",
                    "message": f"User {username} tidak terdaftar"
                }
            
            # Cari peminjaman aktif
            borrowing = db.query(Borrowing).filter(
                Borrowing.id_user == user.id,
                Borrowing.status == 'dipinjam'
            ).first()
            
            if not borrowing:
                return {
                    "status": "error",
                    "message": f"User {username} tidak memiliki peminjaman aktif"
                }
            
            # Update status
            borrowing.status = 'dikembalikan'
            borrowing.updated_at = datetime.now()
            
            # Tambah stok buku
            book = db.query(Book).get(borrowing.id_buku)
            book.stok += 1
            
            db.commit()
            
            # Add to sync queue
            sync_data = {
                "id_peminjaman": borrowing.id_peminjaman,
                "status": "dikembalikan",
                "tanggal_kembali_aktual": datetime.now().isoformat()
            }
            
            sync_queue = SyncQueue(
                table_name='borrowings',
                record_id=borrowing.id_peminjaman,
                action='update',
                data=json.dumps(sync_data)
            )
            db.add(sync_queue)
            db.commit()
            
            # Simpan ID peminjaman untuk digunakan dalam thread terpisah
            borrowing_id_for_sync = borrowing.id_peminjaman
            book_title = book.judul
            book_id = book.id_buku
            
            # Kirim data pengembalian langsung ke Laravel
            try:
                # Gunakan thread terpisah agar tidak menghambat respons ke user
                import threading
                
                def sync_in_background():
                    try:
                        sync_result = sync_service.sync_borrowing_to_laravel(borrowing_id_for_sync)
                        if sync_result['success']:
                            logger.info(f"Pengembalian untuk peminjaman ID {borrowing_id_for_sync} berhasil disinkronkan ke Laravel")
                        else:
                            logger.warning(f"Gagal sinkronisasi pengembalian untuk peminjaman ID {borrowing_id_for_sync}: {sync_result.get('error', 'Unknown error')}")
                    except Exception as sync_err:
                        logger.error(f"Exception in sync thread: {str(sync_err)}")
                
                # Gunakan Timer untuk menjalankan sinkronisasi setelah response dikembalikan
                threading.Timer(2.0, sync_in_background).start()
                
            except Exception as sync_error:
                # Jika gagal sinkronisasi, tidak menggagalkan proses pengembalian
                logger.error(f"Gagal mengirim data pengembalian ke Laravel: {str(sync_error)}")
            
            return {
                "status": "success",
                "message": f"Buku '{book_title}' berhasil dikembalikan",
                "book_data": {
                    "id": book_id,
                    "judul": book_title
                }
            }
            
        except Exception as e:
            db.rollback()
            return {
                "status": "error",
                "message": f"Error: {str(e)}"
            }
        finally:
            try:
                db.close()
            except Exception as close_err:
                logger.warning(f"Error closing database connection: {str(close_err)}")