# debug_sync.py
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models.sync_service import sync_service
from models.database import get_db, Borrowing
import logging

# Setup logging untuk debugging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    print("🔍 Debug Sync Borrowings")
    print("=" * 50)
    
    # 1. Test koneksi ke Laravel
    print("\n1. Testing connection to Laravel...")
    conn_result = sync_service.test_connection()
    if conn_result['success']:
        print("✅ Connection to Laravel successful")
    else:
        print(f"❌ Connection failed: {conn_result['error']}")
        return
    
    # 2. Cek borrowings yang pending
    print("\n2. Checking pending borrowings...")
    pending_result = sync_service.check_pending_borrowings()
    
    if 'total_pending' in pending_result:
        total_pending = pending_result['total_pending']
        print(f"📊 Total pending borrowings: {total_pending}")
        
        if total_pending > 0:
            print("\nPending borrowings:")
            for borrowing in pending_result['borrowings']:
                print(f"  ID: {borrowing['id']}")
                print(f"  User: {borrowing['user_email']}")
                print(f"  Book: {borrowing['book_title']}")
                print(f"  Status: {borrowing['status']}")
                print(f"  Synced: {borrowing['synced']}")
                print(f"  Laravel ID: {borrowing['laravel_id']}")
                print("  ---")
        
        # 3. Force sync borrowings yang pending
        if total_pending > 0:
            print("\n3. Force syncing pending borrowings...")
            choice = input("Do you want to force sync all pending borrowings? (y/n): ")
            
            if choice.lower() == 'y':
                for borrowing in pending_result['borrowings']:
                    borrowing_id = borrowing['id']
                    print(f"\n🔄 Force syncing borrowing {borrowing_id}...")
                    result = sync_service.force_sync_borrowing(borrowing_id)
                    
                    if result['success']:
                        print(f"✅ Borrowing {borrowing_id} synced successfully")
                    else:
                        print(f"❌ Failed to sync borrowing {borrowing_id}: {result['error']}")
                
                # Cek ulang status setelah sync
                print("\n4. Checking status after sync...")
                new_pending_result = sync_service.check_pending_borrowings()
                new_total = new_pending_result.get('total_pending', 0)
                print(f"📊 Remaining pending borrowings: {new_total}")
        
    else:
        print(f"❌ Error checking pending borrowings: {pending_result['error']}")

if __name__ == "__main__":
    main()
