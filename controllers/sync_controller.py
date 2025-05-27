# controllers/sync_controller.py
from flask import Blueprint, jsonify, request
from models.sync_service import sync_service
from models.database import get_db, User, Borrowing
import threading
import logging

# Inisialisasi Blueprint
sync_bp = Blueprint('sync', __name__)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@sync_bp.route('/sync/users/manual', methods=['POST'])
def manual_sync_users():
    """
    Manual sync semua user yang belum ter-sync ke Laravel
    """
    try:
        # Jalankan sync di background thread agar tidak blocking
        def sync_in_background():
            result = sync_service.sync_all_pending_users()
            logger.info(f"Manual user sync completed: {result}")
        
        sync_thread = threading.Thread(target=sync_in_background)
        sync_thread.daemon = True
        sync_thread.start()
        
        return jsonify({
            "status": "success",
            "message": "User sync started in background"
        }), 202
        
    except Exception as e:
        logger.error(f"Error starting manual user sync: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Failed to start sync: {str(e)}"
        }), 500

@sync_bp.route('/sync/borrowings/manual', methods=['POST'])
def manual_sync_borrowings():
    """
    Manual sync semua borrowing yang belum ter-sync ke Laravel
    """
    try:
        # Jalankan sync di background thread
        def sync_in_background():
            result = sync_service.sync_all_pending_borrowings()
            logger.info(f"Manual borrowing sync completed: {result}")
        
        sync_thread = threading.Thread(target=sync_in_background)
        sync_thread.daemon = True
        sync_thread.start()
        
        return jsonify({
            "status": "success",
            "message": "Borrowing sync started in background"
        }), 202
        
    except Exception as e:
        logger.error(f"Error starting manual borrowing sync: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Failed to start sync: {str(e)}"
        }), 500

@sync_bp.route('/sync/test_connection', methods=['POST'])
def test_laravel_connection():
    """
    Test koneksi ke Laravel
    """
    try:
        result = sync_service.test_connection()
        
        if result['success']:
            return jsonify({
                "status": "success",
                "message": "Connection to Laravel successful",
                "laravel_response": result.get('response', {})
            }), 200
        else:
            return jsonify({
                "status": "error",
                "message": f"Connection failed: {result['error']}"
            }), 503
            
    except Exception as e:
        logger.error(f"Error testing Laravel connection: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Connection test failed: {str(e)}"
        }), 500

@sync_bp.route('/sync/status', methods=['GET'])
def sync_status():
    """
    Cek status sync - berapa data yang belum ter-sync
    """
    try:
        db = next(get_db())
        
        # Hitung user yang belum sync
        pending_users = db.query(User).filter(User.synced_to_server == False).count()
        total_users = db.query(User).count()
        
        # Hitung borrowing yang belum sync
        pending_borrowings = db.query(Borrowing).filter(Borrowing.synced_to_server == False).count()
        total_borrowings = db.query(Borrowing).count()
        
        db.close()
        
        return jsonify({
            "status": "success",
            "sync_status": {
                "users": {
                    "total": total_users,
                    "synced": total_users - pending_users,
                    "pending": pending_users
                },
                "borrowings": {
                    "total": total_borrowings,
                    "synced": total_borrowings - pending_borrowings,
                    "pending": pending_borrowings
                }
            },
            "overall_sync_percentage": round(
                ((total_users - pending_users + total_borrowings - pending_borrowings) / 
                 max(total_users + total_borrowings, 1)) * 100, 2
            )
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting sync status: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Failed to get sync status: {str(e)}"
        }), 500

@sync_bp.route('/sync/user/<int:user_id>', methods=['POST'])
def sync_single_user(user_id):
    """
    Sync user tertentu ke Laravel
    """
    try:
        result = sync_service.sync_user_to_laravel(user_id)
        
        if result['success']:
            return jsonify({
                "status": "success",
                "message": f"User {user_id} synced successfully",
                "laravel_user_id": result.get('laravel_user_id')
            }), 200
        else:
            return jsonify({
                "status": "error",
                "message": f"Failed to sync user {user_id}: {result['error']}"
            }), 400
            
    except Exception as e:
        logger.error(f"Error syncing single user {user_id}: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Sync failed: {str(e)}"
        }), 500

@sync_bp.route('/sync/borrowing/<int:borrowing_id>', methods=['POST'])
def sync_single_borrowing(borrowing_id):
    """
    Sync borrowing tertentu ke Laravel
    """
    try:
        result = sync_service.sync_borrowing_to_laravel(borrowing_id)
        
        if result['success']:
            return jsonify({
                "status": "success",
                "message": f"Borrowing {borrowing_id} synced successfully",
                "laravel_borrowing_id": result.get('laravel_borrowing_id')
            }), 200
        else:
            return jsonify({
                "status": "error",
                "message": f"Failed to sync borrowing {borrowing_id}: {result['error']}"
            }), 400
            
    except Exception as e:
        logger.error(f"Error syncing single borrowing {borrowing_id}: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Sync failed: {str(e)}"
        }), 500