# models/database.py - UPDATE: Tambahkan laravel_id fields
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Enum, Text, ForeignKey, Boolean # type: ignore
from sqlalchemy.ext.declarative import declarative_base # type: ignore
from sqlalchemy.orm import relationship, sessionmaker # type: ignore
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database configuration
DB_USER = os.getenv('DB_USER', 'root')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_NAME = os.getenv('DB_NAME', 'perpustakaan_iot')

# Create database URL
DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"

# Create engine
engine = create_engine(DATABASE_URL, echo=True)

# Create declarative base
Base = declarative_base()

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Models
class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    laravel_id = Column(Integer, nullable=True)  # NEW: ID dari Laravel setelah sync
    nama_lengkap = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    face_image_path = Column(String(255))
    role = Column(Enum('admin', 'member'), default='member')
    synced_to_server = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationship
    borrowings = relationship("Borrowing", back_populates="user")

class Book(Base):
    __tablename__ = 'books'
    
    id_buku = Column(Integer, primary_key=True, autoincrement=True)
    laravel_id = Column(Integer, nullable=True)  # NEW: ID dari Laravel (untuk buku yang datang via webhook)
    judul = Column(String(255), nullable=False)
    penulis = Column(String(255))
    penerbit = Column(String(255))
    tahun_terbit = Column(Integer)
    stok = Column(Integer, default=1)
    rfid_tag = Column(String(20), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationship
    borrowings = relationship("Borrowing", back_populates="book")

class Borrowing(Base):
    __tablename__ = 'borrowings'
    
    id_peminjaman = Column(Integer, primary_key=True, autoincrement=True)
    laravel_id = Column(Integer, nullable=True)  # NEW: ID dari Laravel setelah sync
    id_user = Column(Integer, ForeignKey('users.id'))
    id_buku = Column(Integer, ForeignKey('books.id_buku'))
    tanggal_pinjam = Column(DateTime, default=datetime.now)
    tanggal_kembali = Column(DateTime)
    status = Column(Enum('dipinjam', 'dikembalikan'), default='dipinjam')
    synced_to_server = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    user = relationship("User", back_populates="borrowings")
    book = relationship("Book", back_populates="borrowings")

class SyncQueue(Base):
    __tablename__ = 'sync_queue'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    table_name = Column(String(50), nullable=False)
    record_id = Column(Integer, nullable=False)
    action = Column(String(20), nullable=False)  # create, update, delete
    data = Column(Text)  # JSON data
    synced = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    synced_at = Column(DateTime, nullable=True)

# NEW: Webhook log untuk tracking
class WebhookLog(Base):
    __tablename__ = 'webhook_logs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    webhook_type = Column(String(50), nullable=False)  # 'incoming' or 'outgoing'
    endpoint = Column(String(255), nullable=False)
    method = Column(String(10), nullable=False)
    payload = Column(Text)  # JSON payload
    response = Column(Text)  # Response JSON
    status_code = Column(Integer)
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

# Function untuk create database dan tables
def init_db():
    """Create database tables"""
    Base.metadata.create_all(bind=engine)
    print("Database tables created!")

# Function untuk get session
def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Initial data seeder - UPDATED dengan laravel_id
def seed_initial_data():
    """Seed initial books data"""
    db = SessionLocal()
    
    # Check if books already exist
    existing_books = db.query(Book).count()
    if existing_books > 0:
        print("Books already seeded")
        return
    
    # Initial books data dengan RFID hex format (LOCAL books, bukan dari Laravel)
    books_data = [
        {
            "laravel_id": None,  # Local book, belum ada di Laravel
            "judul": "Pemrograman Python untuk Pemula",
            "penulis": "John Doe",
            "penerbit": "Tech Press",
            "tahun_terbit": 2022,
            "stok": 3,
            "rfid_tag": "53A0A434"
        },
        {
            "laravel_id": None,
            "judul": "Internet of Things: Konsep dan Aplikasi",
            "penulis": "Jane Smith",
            "penerbit": "IoT Publisher",
            "tahun_terbit": 2021,
            "stok": 2,
            "rfid_tag": "43991C03"
        },
        {
            "laravel_id": None,
            "judul": "Database Design 101",
            "penulis": "Robert Johnson",
            "penerbit": "Data Press",
            "tahun_terbit": 2020,
            "stok": 4,
            "rfid_tag": "9C5D3E7B"
        },
        {
            "laravel_id": None,
            "judul": "Machine Learning untuk Bisnis",
            "penulis": "Sarah Williams",
            "penerbit": "AI Books",
            "tahun_terbit": 2023,
            "stok": 2,
            "rfid_tag": "2F6B8A1C"
        },
        {
            "laravel_id": None,
            "judul": "Membangun Aplikasi Web dengan Flask",
            "penulis": "Michael Brown",
            "penerbit": "Web Dev Press",
            "tahun_terbit": 2022,
            "stok": 3,
            "rfid_tag": "7D9E4F6B"
        }
    ]
    
    # Insert books
    for book_data in books_data:
        book = Book(**book_data)
        db.add(book)
    
    db.commit()
    print(f"Seeded {len(books_data)} books")
    db.close()