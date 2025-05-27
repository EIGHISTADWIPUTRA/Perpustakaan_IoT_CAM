# controllers/webhook_controller.py
from flask import Blueprint, request, jsonify
from models.book_model import BookModel
from models.database import get_db, Book
from datetime import datetime
import logging
import json

# Inisialisasi Blueprint
webhook_bp = Blueprint('webhook', __name__)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API Key untuk autentikasi (bisa diatur di .env)
WEBHOOK_API_KEY = "password"

def validate_api_key():
    """Validasi API key dari header request"""
    api_key = request.headers.get('X-API-Key')
    # if not api_key or api_key != WEBHOOK_API_KEY:
    #     return False
    return True

@webhook_bp.route('/webhook/books', methods=['POST'])
def receive_book_webhook():
    """
    Endpoint untuk menerima webhook buku dari Laravel
    
    Expected payload:
    {
        "event": "book_created|book_updated|book_deleted",
        "timestamp": "2024-05-27T10:30:00Z",
        "data": {
            "id": 123,
            "judul": "Python Programming",
            "penulis": "John Doe",
            "penerbit": "Tech Press", 
            "tahun_terbit": 2024,
            "stok": 5,
            "rfid_tag": "ABC123"
        }
    }
    """
    try:
        # Validasi API key
        if not validate_api_key():
            logger.warning("Unauthorized webhook attempt from IP: %s", request.remote_addr)
            return jsonify({
                "status": "error",
                "message": "Unauthorized: Invalid API key"
            }), 401

        # Validasi content type
        if not request.is_json:
            return jsonify({
                "status": "error",
                "message": "Invalid content type. JSON expected"
            }), 400

        payload = request.get_json()
        logger.info("Received book webhook payload: %s", json.dumps(payload, indent=2))

        # Validasi struktur payload
        required_fields = ['event', 'timestamp', 'data']
        if not all(field in payload for field in required_fields):
            missing_fields = [field for field in required_fields if field not in payload]
            return jsonify({
                "status": "error",
                "message": f"Missing required fields: {', '.join(missing_fields)}"
            }), 400

        # Validasi data buku
        book_data = payload['data']
        required_book_fields = ['id', 'judul', 'penulis', 'tahun_terbit', 'stok', 'rfid_tag']
        
        if not all(field in book_data for field in required_book_fields):
            missing_fields = [field for field in required_book_fields if field not in book_data]
            return jsonify({
                "status": "error",
                "message": f"Missing book data fields: {', '.join(missing_fields)}"
            }), 400

        # Process berdasarkan event type
        event_type = payload['event']
        result = None
        
        if event_type in ['book_created', 'book_updated']:
            result = process_book_create_or_update(book_data)
        elif event_type == 'book_deleted':
            result = process_book_delete(book_data)
        else:
            return jsonify({
                "status": "error",
                "message": f"Unsupported event type: {event_type}"
            }), 400

        if result['status'] == 'success':
            logger.info("Book webhook processed successfully. Event: %s, Book ID: %s", 
                       event_type, book_data['id'])
            return jsonify(result), 200
        else:
            logger.error("Book webhook processing failed: %s", result['message'])
            return jsonify(result), 500

    except json.JSONDecodeError:
        return jsonify({
            "status": "error",
            "message": "Invalid JSON format"
        }), 400
    except Exception as e:
        logger.error("Unexpected error processing book webhook: %s", str(e))
        return jsonify({
            "status": "error",
            "message": f"Internal server error: {str(e)}"
        }), 500

def process_book_create_or_update(book_data):
    """Proses pembuatan atau update buku"""
    db = next(get_db())
    
    try:
        # Cek apakah buku sudah ada berdasarkan Laravel ID
        existing_book = db.query(Book).filter(Book.laravel_id == book_data['id']).first()
        
        if existing_book:
            # Update buku yang sudah ada
            existing_book.judul = book_data['judul']
            existing_book.penulis = book_data['penulis']
            existing_book.penerbit = book_data.get('penerbit', '')
            existing_book.tahun_terbit = book_data['tahun_terbit']
            existing_book.stok = book_data['stok']
            existing_book.rfid_tag = book_data['rfid_tag']
            existing_book.updated_at = datetime.now()
            
            db.commit()
            
            return {
                "status": "success",
                "message": "Book updated in Flask catalog",
                "local_book_id": existing_book.id_buku,
                "action": "updated"
            }
        else:
            # Cek apakah RFID tag sudah digunakan
            rfid_exists = db.query(Book).filter(Book.rfid_tag == book_data['rfid_tag']).first()
            if rfid_exists:
                return {
                    "status": "error",
                    "message": f"RFID tag {book_data['rfid_tag']} already exists in Flask database"
                }
            
            # Buat buku baru
            new_book = Book(
                laravel_id=book_data['id'],  # ID dari Laravel
                judul=book_data['judul'],
                penulis=book_data['penulis'],
                penerbit=book_data.get('penerbit', ''),
                tahun_terbit=book_data['tahun_terbit'],
                stok=book_data['stok'],
                rfid_tag=book_data['rfid_tag'],
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            
            db.add(new_book)
            db.commit()
            
            return {
                "status": "success",
                "message": "Book created in Flask catalog",
                "local_book_id": new_book.id_buku,
                "action": "created"
            }
            
    except Exception as e:
        db.rollback()
        return {
            "status": "error",
            "message": f"Database error: {str(e)}"
        }
    finally:
        db.close()

def process_book_delete(book_data):
    """Proses penghapusan buku"""
    db = next(get_db())
    
    try:
        # Cari buku berdasarkan Laravel ID
        book_to_delete = db.query(Book).filter(Book.laravel_id == book_data['id']).first()
        
        if not book_to_delete:
            return {
                "status": "error",
                "message": f"Book with Laravel ID {book_data['id']} not found in Flask database"
            }
        
        # Hapus buku
        db.delete(book_to_delete)
        db.commit()
        
        return {
            "status": "success",
            "message": "Book deleted from Flask catalog",
            "local_book_id": book_to_delete.id_buku,
            "action": "deleted"
        }
        
    except Exception as e:
        db.rollback()
        return {
            "status": "error",
            "message": f"Database error: {str(e)}"
        }
    finally:
        db.close()

@webhook_bp.route('/webhook/test', methods=['POST'])
def test_webhook():
    """
    Endpoint untuk testing webhook connectivity dari Laravel
    
    Expected payload:
    {
        "test_message": "Hello from Laravel",
        "timestamp": "2024-05-27T10:30:00Z",
        "test_id": "test_001"
    }
    """
    try:
        # Validasi API key
        if not validate_api_key():
            logger.warning("Unauthorized test webhook attempt from IP: %s", request.remote_addr)
            return jsonify({
                "status": "error",
                "message": "Unauthorized: Invalid API key"
            }), 401

        # Validasi content type
        if not request.is_json:
            return jsonify({
                "status": "error",
                "message": "Invalid content type. JSON expected"
            }), 400

        payload = request.get_json()
        logger.info("Received test webhook payload: %s", json.dumps(payload, indent=2))

        # Validasi payload
        if 'test_message' not in payload:
            return jsonify({
                "status": "error",
                "message": "Missing test_message field"
            }), 400

        # Response sukses dengan informasi sistem
        response_data = {
            "status": "received",
            "message": "Test webhook working perfectly",
            "received_at": datetime.now().isoformat() + "Z",
            "test_id": payload.get('test_id', 'unknown'),
            "original_message": payload['test_message'],
            "flask_system_info": {
                "version": "1.0.0",
                "status": "healthy",
                "local_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        }

        logger.info("Test webhook processed successfully. Test ID: %s", 
                   payload.get('test_id', 'unknown'))
        
        return jsonify(response_data), 200

    except json.JSONDecodeError:
        return jsonify({
            "status": "error",
            "message": "Invalid JSON format"
        }), 400
    except Exception as e:
        logger.error("Unexpected error processing test webhook: %s", str(e))
        return jsonify({
            "status": "error",
            "message": f"Flask webhook receiver error: {str(e)}"
        }), 500

@webhook_bp.route('/webhook/status', methods=['GET'])
def webhook_status():
    """
    Endpoint untuk checking status webhook system
    """
    try:
        # Basic health check
        db = next(get_db())
        db.execute("SELECT 1")  # Simple query to test DB connection
        db.close()
        
        return jsonify({
            "status": "healthy",
            "message": "Webhook system is running",
            "timestamp": datetime.now().isoformat() + "Z",
            "endpoints": {
                "books": "/api/webhook/books",
                "test": "/api/webhook/test",
                "status": "/api/webhook/status"
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "message": f"System error: {str(e)}",
            "timestamp": datetime.now().isoformat() + "Z"
        }), 500