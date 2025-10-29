"""
Cấu hình chung cho hệ thống Bộ Não AI Đọc CV (V8)
File này được import bởi cả app.py và read_cv4.py để đảm bảo đồng bộ
"""

# ============================================
# CẤU HÌNH VECTOR HÓA (mBERT)
# ============================================

# Bật/tắt vector hóa bằng mBERT
# - True: Chậm hơn (~15-30s lần đầu) nhưng có vector cho ML
# - False: Nhanh (~1-2s), chỉ trích xuất thông tin cho người xem
ENABLE_VECTOR = True

# Tên model mBERT
MBERT_MODEL_NAME = "bert-base-multilingual-cased"

# Max length cho tokenizer (512 tokens)
MAX_TOKEN_LENGTH = 512


# ============================================
# CẤU HÌNH FLASK SERVER
# ============================================

# Thư mục lưu file upload tạm thời
UPLOAD_FOLDER = 'uploads'

# Host và Port
FLASK_HOST = '127.0.0.1'
FLASK_PORT = 5000

# Debug mode
FLASK_DEBUG = True


# ============================================
# CẤU HÌNH PDF PROCESSING
# ============================================

# Tự động sửa lỗi PDF header (newline thừa)
AUTO_FIX_PDF_HEADER = True


# ============================================
# CẤU HÌNH LOGGING
# ============================================

# In log chi tiết
VERBOSE_LOGGING = True


# Đường dẫn đến file model đã huấn luyện
BRAIN_MODEL_PATH = 'thebrain_model.pkl'

# Vị trí ứng tuyển mặc định nếu web không gửi lên
DEFAULT_JOB_LEVEL = 'Mid'
