from flask import Flask
from controllers.main_controller import main_bp
from controllers.api_controller import api_bp
from controllers.setup_controller import setup_bp
from controllers.webhook_controller import webhook_bp
from controllers.sync_controller import sync_bp
from controllers.user_controller import user_bp
from controllers.admin_controller import admin_bp
from dotenv import load_dotenv
from models.database import init_db
import os

# Load variabel lingkungan dari .env jika ada
load_dotenv()

# Inisialisasi aplikasi Flask
app = Flask(__name__, 
            template_folder='views/templates',
            static_folder='views/static')

# Set secret key untuk session
app.secret_key = os.environ.get('SECRET_KEY')

# Register blueprint
app.register_blueprint(main_bp)
app.register_blueprint(api_bp, url_prefix='/api')
app.register_blueprint(setup_bp)
app.register_blueprint(webhook_bp, url_prefix='/api')  # Webhook endpoints
app.register_blueprint(sync_bp, url_prefix='/api')    # Sync endpoints  
app.register_blueprint(user_bp, url_prefix='/user')   # User management
app.register_blueprint(admin_bp)                      # Admin endpoints

# Fungsi untuk memastikan folder yang diperlukan tersedia
def ensure_directories():
    """Memastikan semua direktori yang diperlukan tersedia."""
    for folder in ['captures', 'encodings', 'known_faces']:
        if not os.path.exists(folder):
            os.makedirs(folder)
            print(f"Folder {folder} dibuat")

if __name__ == '__main__':
    
    init_db()
    # Memastikan direktori yang diperlukan tersedia
    ensure_directories()
    
    # Jalankan aplikasi Flask
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)