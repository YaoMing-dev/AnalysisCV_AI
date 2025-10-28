import os
import sys
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import traceback
import importlib

# === IMPORT CẤU HÌNH CHUNG ===
import config

# === IMPORT "BỘ NÃO" CỦA BẠN TỪ FILE read_cv4.py ===
from read_cv4 import extract_text_from_pdf, extract_key_info, get_cv_vector_mbert

# --- Cấu hình từ config.py ---
UPLOAD_FOLDER = config.UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
CORS(app) 

# === TẠO API "ĐỌC CV" ===
@app.route('/read_cv', methods=['POST'])
def handle_cv_upload():
    # Force reload config để đảm bảo đồng bộ
    importlib.reload(config)

    print("\n" + "="*60, flush=True)
    print("--- Nhận được yêu cầu /read_cv ---", flush=True)
    print(f"⚙️  config.ENABLE_VECTOR = {config.ENABLE_VECTOR}", flush=True)
    print("="*60, flush=True)

    if 'cv_file' not in request.files:
        print("❌ Lỗi: Không tìm thấy 'cv_file' trong request.files")
        return jsonify({"error": "Không tìm thấy file"}), 400
    
    file = request.files['cv_file']
    
    if file.filename == '':
        print("❌ Lỗi: Tên file trống")
        return jsonify({"error": "Chưa chọn file"}), 400

    if file and file.filename.lower().endswith('.pdf'): # Dùng lower() cho chắc
        pdf_path = None # Khởi tạo để đảm bảo luôn có biến này
        try:
            # 1. Lưu file PDF tạm thời
            filename = secure_filename(file.filename)
            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(pdf_path)
            print(f"📄 Đã lưu file tạm tại: {pdf_path}")

            # === GỌI "BỘ NÃO" V8 ĐỂ XỬ LÝ ===
            # Lưu ý: read_cv4.extract_text_from_pdf() đã tự động xử lý PDF header
            
            # B1: Đọc text từ PDF
            print("\n🧠 Gọi Bộ Não V8 - Bước 1: Trích xuất text...", flush=True)
            cv_text = extract_text_from_pdf(pdf_path)

            print(f"   DEBUG: cv_text = {cv_text[:100] if cv_text else 'None'}...", flush=True)

            if not cv_text:
                print("❌ Lỗi từ extract_text_from_pdf - cv_text là None hoặc empty", flush=True)
                # Dọn dẹp file tạm
                if os.path.exists(pdf_path): os.remove(pdf_path)
                error_response = jsonify({"error": "Không thể đọc text từ PDF. File có thể bị lỗi hoặc header không hợp lệ."})
                print(f"   DEBUG: Trả về error response: {error_response.get_json()}", flush=True)
                return error_response, 500

            # B2A: Trích xuất thông tin (cho Người xem)
            print("🧠 Gọi Bộ Não V8 - Bước 2A: Trích xuất thông tin (Regex V7)...")
            human_results = extract_key_info(cv_text)

            # B2B: Vector hóa (cho Máy học) - Đọc từ config.py
            if config.ENABLE_VECTOR:
                print("🧠 Gọi Bộ Não V8 - Bước 2B: Vector hóa (mBERT)...")
                ai_vector = get_cv_vector_mbert(cv_text)

                if ai_vector is not None:
                    ai_vector_list = ai_vector[0, :10].numpy().tolist()
                    print("   ✅ Vector hóa thành công (lấy 10 số đầu)")
                else:
                    ai_vector_list = "Không thể tạo vector"
                    print("   ❌ Vector hóa thất bại")
            else:
                ai_vector_list = "⚡ Vector hóa đã TẮT (để tăng tốc xử lý)"
                print(f"   ⚡ Bỏ qua vector hóa (config.ENABLE_VECTOR={config.ENABLE_VECTOR})")

            # 3. Dọn dẹp file tạm (Luôn chạy)
            print(f"🗑️ Dọn dẹp file tạm: {pdf_path}")
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
            
            # 4. Trả kết quả về cho web
            print("✅ Hoàn tất! Đang gửi kết quả về web...", flush=True)
            response_data = {
                "success": True,
                "results_human": human_results,
                "results_ai_vector_preview": ai_vector_list
            }
            print(f"   DEBUG: Response keys: {list(response_data.keys())}", flush=True)
            print(f"   DEBUG: results_human has {len(human_results)} fields", flush=True)
            return jsonify(response_data)

        except Exception as e:
            print(f"❌ LỖI NGHIÊM TRỌNG TRONG QUÁ TRÌNH XỬ LÝ:")
            traceback.print_exc() # In chi tiết lỗi ra terminal Flask
            # Dọn dẹp file tạm nếu có lỗi
            if pdf_path and os.path.exists(pdf_path):
                print(f"🗑️ Dọn dẹp file tạm (do lỗi): {pdf_path}")
                os.remove(pdf_path)
            return jsonify({"error": f"Lỗi server: {e}"}), 500
    else:
        print("❌ Lỗi: File không phải là PDF")
        return jsonify({"error": "Chỉ chấp nhận file .pdf"}), 400

# === SERVE INDEX.HTML QUA FLASK (TRÁNH CORS) ===
@app.route('/')
def index():
    """Serve index.html để tránh CORS issue"""
    from flask import send_file
    import os
    html_path = os.path.join(os.path.dirname(__file__), 'index.html')
    return send_file(html_path)

# === API Test Connectivity ===
@app.route('/api/test')
def test():
    """Test endpoint để kiểm tra kết nối"""
    return jsonify({
        "status": "ok",
        "message": "Flask server đang hoạt động!",
        "enable_vector": config.ENABLE_VECTOR
    })

# --- Pre-load mBERT model nếu ENABLE_VECTOR = True ---
def preload_model():
    """Load mBERT model trước khi Flask nhận requests"""
    if config.ENABLE_VECTOR:
        print("\n🔄 Đang pre-load mBERT model (để tránh timeout lần đầu)...", flush=True)
        try:
            # Tạo dummy text để trigger model loading
            dummy_text = "Test CV text"
            get_cv_vector_mbert(dummy_text)
            print("✅ mBERT model đã sẵn sàng!\n", flush=True)
        except Exception as e:
            print(f"⚠️  Lỗi khi pre-load model: {e}", flush=True)
            print("   Model sẽ được load khi xử lý request đầu tiên.\n", flush=True)
    else:
        print("⚡ Vector hóa đã TẮT, không cần load model.\n", flush=True)

# --- Pre-load model khi Flask reloader khởi động lần thứ 2 ---
# Flask debug mode chạy 2 lần: parent process và child process (reloader)
# Chỉ pre-load ở child process (khi WERKZEUG_RUN_MAIN=true)
if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    print("\n" + "="*60, flush=True)
    print(f"🚀 Flask Server đã sẵn sàng!", flush=True)
    print(f"   URL: http://{config.FLASK_HOST}:{config.FLASK_PORT}", flush=True)
    print(f"   ⚙️  ENABLE_VECTOR = {config.ENABLE_VECTOR}", flush=True)
    print("="*60, flush=True)

    # Pre-load model nếu cần
    preload_model()

    print("✅ Server đang chạy. Hãy mở index.html trong browser!", flush=True)
    print("   (Nhấn Ctrl+C để dừng)\n", flush=True)

# --- Chạy server ---
if __name__ == '__main__':
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=config.FLASK_DEBUG)