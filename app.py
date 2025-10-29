import os
import sys
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import traceback
import importlib

# === IMPORT CẤU HÌNH CHUNG ===
import config

# === IMPORT "BỘ NÃO" BÓC TÁCH (read_cv4.py) ===
#
from read_cv4 import extract_text_from_pdf, extract_key_info, get_cv_vector_mbert

# === IMPORT "BỘ NÃO" CHẤM ĐIỂM (thebrain.py) ===
#
try:
    from thebrain import (
        CVScoringModel,
        CVScoringRules,
        CVFeatureExtractor,  # THÊM này để pickle load được
        convert_read_cv4_to_dataframe,
        calculate_job_match_adjustment
    )
    THE_BRAIN_LOADED = True
except ImportError as e:
    print(f"❌ Lỗi: Không thể import từ thebrain.py: {e}")
    print("   API sẽ chỉ chạy chức năng 'read_cv4' (bóc tách).")
    THE_BRAIN_LOADED = False

# --- Cấu hình từ config.py ---
UPLOAD_FOLDER = config.UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
CORS(app) 

# === Biến toàn cục để giữ model ===
g_brain_model = None

# === TẠO API "ĐỌC VÀ CHẤM ĐIỂM CV" ===
@app.route('/read_cv', methods=['POST'])
def handle_cv_upload():
    # Force reload config để đảm bảo đồng bộ
    importlib.reload(config)

    print("\n" + "="*60, flush=True)
    print("--- Nhận được yêu cầu /read_cv (phiên bản CHẤM ĐIỂM) ---", flush=True)
    print(f"⚙️  config.ENABLE_VECTOR = {config.ENABLE_VECTOR}", flush=True)
    print(f"⚙️  THE_BRAIN_LOADED = {THE_BRAIN_LOADED}", flush=True)
    print("="*60, flush=True)

    if 'cv_file' not in request.files:
        print("❌ Lỗi: Không tìm thấy 'cv_file' trong request.files")
        return jsonify({"error": "Không tìm thấy file"}), 400
    
    file = request.files['cv_file']
    
    # LẤY VỊ TRÍ ỨNG TUYỂN TỪ WEB (HTML)
    #
    target_job_level = request.form.get('job_level', config.DEFAULT_JOB_LEVEL)
    print(f"🎯 Vị trí ứng tuyển mục tiêu: {target_job_level}")

    if file.filename == '':
        print("❌ Lỗi: Tên file trống")
        return jsonify({"error": "Chưa chọn file"}), 400

    if file and file.filename.lower().endswith('.pdf'):
        pdf_path = None 
        try:
            # 1. Lưu file PDF tạm thời
            filename = secure_filename(file.filename)
            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(pdf_path)
            print(f"📄 Đã lưu file tạm tại: {pdf_path}")

            # === BƯỚC 1: ĐỌC TEXT (TỪ read_cv4) ===
            print("\n🧠 Bước 1: Trích xuất text (read_cv4)...", flush=True)
            cv_text = extract_text_from_pdf(pdf_path) #

            if not cv_text:
                print("❌ Lỗi từ extract_text_from_pdf - cv_text là None hoặc empty", flush=True)
                if os.path.exists(pdf_path): os.remove(pdf_path)
                return jsonify({"error": "Không thể đọc text từ PDF."}), 500

            # === BƯỚC 2: BÓC TÁCH THÔNG TIN (TỪ read_cv4) ===
            print("🧠 Bước 2: Bóc tách thông tin (read_cv4)...", flush=True)
            human_results = extract_key_info(cv_text) #
            
            # --- Đây là logic mới để tích hợp THE BRAIN ---
            if not THE_BRAIN_LOADED:
                print("⚠️  Cảnh báo: 'thebrain.py' chưa được load. Chỉ trả về kết quả bóc tách.")
                if os.path.exists(pdf_path): os.remove(pdf_path)
                return jsonify({
                    "success": True,
                    "extracted_info": human_results,
                    "scoring_results": {"error": "Scoring engine (thebrain.py) not loaded."}
                })

            # === BƯỚC 3: CHUYỂN ĐỔI DỮ LIỆU SANG FORMAT "THE BRAIN" ===
            print("🧠 Bước 3: Chuyển đổi dữ liệu (thebrain)...", flush=True)
            cv_data_row = convert_read_cv4_to_dataframe(human_results) #

            # === BƯỚC 4: CHẤM ĐIỂM BẰNG LUẬT (TỪ thebrain) ===
            print("🧠 Bước 4: Chấm điểm bằng Luật (thebrain)...", flush=True)
            rule_score, score_breakdown = CVScoringRules.calculate_total_score(cv_data_row) #
            
            # Lấy thông tin AI vừa phát hiện
            detected_industry = score_breakdown.get('detected_industry', 'Unknown')
            candidate_seniority = score_breakdown.get('seniority', 'Unknown')
            red_flag_penalty = score_breakdown.get('red_flag_penalty', 0)

            # === BƯỚC 5: CHẤM ĐIỂM BẰNG AI (ML Model) ===
            base_ml_score = None
            if g_brain_model:
                print("🧠 Bước 5: Chấm điểm bằng AI (thebrain ML)...", flush=True)
                base_ml_score = g_brain_model.predict(cv_data_row) #
            else:
                print("🧠 Bước 5: Bỏ qua chấm điểm AI (model .pkl chưa load).")
                base_ml_score = rule_score # Dùng tạm điểm của Luật nếu ko có model

            # === BƯỚC 6: TÍNH ĐIỂM PHÙ HỢP CÔNG VIỆC (TỪ thebrain) ===
            print("🧠 Bước 6: Tính điểm phù hợp (thebrain)...", flush=True)
            match_adjustment = calculate_job_match_adjustment(
                candidate_seniority, 
                target_job_level, 
                base_ml_score
            ) #
            
            final_score = base_ml_score + match_adjustment
            final_score = min(max(final_score, 0), 100) # Đảm bảo điểm từ 0-100

            # (Tùy chọn) BƯỚC 7: Vector hóa
            ai_vector_list = "Tắt (để tập trung chấm điểm)"
            if config.ENABLE_VECTOR:
                print("🧠 Bước 7: Vector hóa (read_cv4)...", flush=True)
                ai_vector = get_cv_vector_mbert(cv_text) #
                if ai_vector is not None:
                    ai_vector_list = ai_vector[0, :10].numpy().tolist()
            
            # === BƯỚC 8: TRẢ KẾT QUẢ TỔNG HỢP VỀ WEB ===
            print("✅ Hoàn tất! Đang gửi kết quả chấm điểm về web...", flush=True)
            
            response_data = {
                "success": True,
                # Phần 1: Thông tin bóc tách (từ read_cv4)
                "extracted_info": human_results,
                
                # Phần 2: Kết quả chấm điểm (từ thebrain)
                "scoring_results": {
                    "target_job_level": target_job_level,
                    "detected_industry": detected_industry,
                    "candidate_seniority": candidate_seniority,
                    "red_flag_penalty": red_flag_penalty,
                    "base_ml_score": float(base_ml_score), # Chuyển sang float
                    "match_adjustment": float(match_adjustment),
                    "final_score": float(final_score),
                    "score_breakdown_details": score_breakdown # Gửi toàn bộ chi tiết điểm
                },

                # Phần 3: Vector (tùy chọn)
                "results_ai_vector_preview": ai_vector_list
            }

            # 3. Dọn dẹp file tạm
            print(f"🗑️ Dọn dẹp file tạm: {pdf_path}")
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
            
            # 4. Trả kết quả về cho web
            return jsonify(response_data)

        except Exception as e:
            print(f"❌ LỖI NGHIÊM TRỌNG TRONG QUÁ TRÌNH XỬ LÝ:")
            traceback.print_exc() 
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
    if not os.path.exists(html_path):
        return "Lỗi: Không tìm thấy file index.html"
    return send_file(html_path)

# === API Test Connectivity ===
@app.route('/api/test')
def test():
    """Test endpoint để kiểm tra kết nối"""
    return jsonify({
        "status": "ok",
        "message": "Flask server đang hoạt động!",
        "enable_vector": config.ENABLE_VECTOR,
        "the_brain_loaded": THE_BRAIN_LOADED,
        "brain_model_loaded": (g_brain_model is not None)
    })

# --- Pre-load mBERT model nếu ENABLE_VECTOR = True ---
def preload_model():
    """Load mBERT model trước khi Flask nhận requests"""
    if config.ENABLE_VECTOR:
        print("\n🔄 Đang pre-load mBERT model (để tránh timeout lần đầu)...", flush=True)
        try:
            get_cv_vector_mbert("Test CV text") #
            print("✅ mBERT model đã sẵn sàng!\n", flush=True)
        except Exception as e:
            print(f"⚠️  Lỗi khi pre-load mBERT model: {e}", flush=True)
    else:
        print("⚡ Vector hóa mBERT đã TẮT, không cần load model.\n", flush=True)

# --- Pre-load "THE BRAIN" model ---
def preload_brain_model():
    """Load model chấm điểm AI (.pkl) của "THE BRAIN" """
    global g_brain_model
    if not THE_BRAIN_LOADED:
        print("⚠️  'THE BRAIN' (thebrain.py) chưa được import, không thể load model AI.", flush=True)
        return
        
    model_path = config.BRAIN_MODEL_PATH #
    if os.path.exists(model_path):
        print(f"\n🔄 Đang pre-load 'THE BRAIN' model ({model_path})...", flush=True)
        g_brain_model = CVScoringModel.load_model(model_path) #
        if g_brain_model:
            print("✅ 'THE BRAIN' model (.pkl) đã sẵn sàng!\n", flush=True)
        else:
            print(f"❌ Lỗi: Không thể load 'THE BRAIN' model từ {model_path}.", flush=True)
    else:
        print(f"⚠️  Cảnh báo: Không tìm thấy file model '{model_path}'.", flush=True)
        print("   API sẽ chỉ có thể chấm điểm bằng Luật (Rules), không có ML.", flush=True)

# --- Pre-load models khi Flask reloader khởi động ---
if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    print("\n" + "="*60, flush=True)
    print(f"🚀 Flask Server đã sẵn sàng!", flush=True)
    print(f"   URL: http://{config.FLASK_HOST}:{config.FLASK_PORT}", flush=True)
    print(f"   ⚙️  ENABLE_VECTOR = {config.ENABLE_VECTOR}", flush=True)
    print(f"   🧠 THE_BRAIN_LOADED = {THE_BRAIN_LOADED}", flush=True)
    print("="*60, flush=True)

    # Pre-load cả 2 model nếu cần
    preload_model()
    preload_brain_model()

    print("✅ Server đang chạy. Hãy mở index.html trong browser!", flush=True)
    print("   (Nhấn Ctrl+C để dừng)\n", flush=True)

# --- Chạy server ---
if __name__ == '__main__':
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=config.FLASK_DEBUG)