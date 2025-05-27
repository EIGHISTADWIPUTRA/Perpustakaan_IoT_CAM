from flask import Blueprint, render_template, jsonify, request
from models.database import get_db, Borrowing, User
from functools import wraps
from flask import session, redirect, url_for
import logging

# Inisialisasi Blueprint
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('main.index'))
        
        db = next(get_db())
        try:
            user = db.query(User).get(session['user_id'])
            if not user or user.role != 'admin':
                return redirect(url_for('main.index'))
        finally:
            db.close()
            
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/borrowings')
@admin_required
def list_borrowings():
    """Halaman daftar peminjaman untuk admin"""
    db = next(get_db())
    try:
        # Get all borrowings with related user and book data
        borrowings = db.query(Borrowing)\
            .order_by(Borrowing.created_at.desc())\
            .all()
        return render_template('admin/borrowings.html', borrowings=borrowings)
    except Exception as e:
        logger.error(f"Error loading borrowings: {str(e)}")
        return render_template('admin/borrowings.html', borrowings=[], 
                             error=f"Error loading borrowings: {str(e)}")
    finally:
        db.close()

@admin_bp.route('/api/borrowings/<int:borrowing_id>')
@admin_required
def get_borrowing_detail(borrowing_id):
    """Get detail peminjaman"""
    db = next(get_db())
    try:
        borrowing = db.query(Borrowing).get(borrowing_id)
        if not borrowing:
            return jsonify({
                "status": "error",
                "message": "Peminjaman tidak ditemukan"
            }), 404
            
        return jsonify({
            "status": "success",
            "data": {
                "id_peminjaman": borrowing.id_peminjaman,
                "user_name": borrowing.user.nama_lengkap,
                "book_title": borrowing.book.judul,
                "tanggal_pinjam": borrowing.tanggal_pinjam.strftime("%Y-%m-%d %H:%M"),
                "tanggal_kembali": borrowing.tanggal_kembali.strftime("%Y-%m-%d %H:%M") if borrowing.tanggal_kembali else None,
                "status": borrowing.status,
                "synced": borrowing.synced_to_server
            }
        })
    except Exception as e:
        logger.error(f"Error getting borrowing details: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Error: {str(e)}"
        }), 500
    finally:
        db.close()
