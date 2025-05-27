# models/book_model.py
from datetime import datetime, timedelta
from models.database import Book, Borrowing, User, SyncQueue, get_db
from sqlalchemy.orm import Session # type: ignore
import json

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
            
            return {
                "status": "success",
                "message": f"Buku '{book.judul}' berhasil dipinjam oleh {username}",
                "book_data": {
                    "id": book.id_buku,
                    "judul": book.judul,
                    "penulis": book.penulis
                },
                "peminjaman": {
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
            db.close()
    
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
            
            return {
                "status": "success",
                "message": f"Buku '{book.judul}' berhasil dikembalikan",
                "book_data": {
                    "id": book.id_buku,
                    "judul": book.judul
                }
            }
            
        except Exception as e:
            db.rollback()
            return {
                "status": "error",
                "message": f"Error: {str(e)}"
            }
        finally:
            db.close()