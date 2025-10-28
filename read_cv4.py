import sys
import re
import io
from pypdf import PdfReader, errors
import torch
from transformers import AutoModel, AutoTokenizer

# === IMPORT CẤU HÌNH CHUNG ===
try:
    import config
except ImportError:
    # Nếu chạy standalone không có config.py, dùng giá trị mặc định
    class config:
        ENABLE_VECTOR = True  # Khi chạy standalone, mặc định bật vector
        MBERT_MODEL_NAME = "bert-base-multilingual-cased"
        MAX_TOKEN_LENGTH = 512
        VERBOSE_LOGGING = True

# === BẢN VÁ CỦA BẠN: Fix encoding cho Windows console ===
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# === BƯỚC 1: "ĐỌC" FILE PDF LẤY CHỮ (*** NÂNG CẤP XỬ LÝ HEADER ***) ===
def extract_text_from_pdf(pdf_path):
    """
    Trích xuất toàn bộ text từ file PDF.
    Tự động thử sửa lỗi 'invalid pdf header' (do newline thừa).
    """
    full_text = ""
    try:
        # 1. Thử đọc bình thường trước
        print(f"   (extract_text) Thử đọc file: {pdf_path}", flush=True)
        reader = PdfReader(pdf_path)
        for page in reader.pages:
            full_text += page.extract_text() + "\n"
        print("   (extract_text) Đọc header chuẩn thành công.", flush=True)

    except errors.PdfReadError as e:
        # 2. Bắt lỗi PdfReadError (bao gồm cả lỗi header)
        error_msg = str(e).lower()
        print(f"   (extract_text) Gặp lỗi PdfReadError: {error_msg}", flush=True)

        if 'invalid pdf header' in error_msg:
            print("   (extract_text) Phát hiện lỗi header! Đang thử sửa...", flush=True)
            try:
                with open(pdf_path, 'rb') as f:
                    content = f.read()

                print(f"   (extract_text) DEBUG: File bắt đầu bằng: {content[:20]}", flush=True)

                # Loại bỏ TẤT CẢ whitespace ở đầu
                while content and content[0:1] in (b'\n', b'\r', b' ', b'\t'):
                    content = content[1:]

                if content.startswith(b'%PDF'):
                    print(f"   (extract_text) Đã loại bỏ ký tự thừa, bây giờ bắt đầu: {content[:10]}", flush=True)
                    # Tạo một "file ảo" trong bộ nhớ từ nội dung đã sửa
                    pdf_stream = io.BytesIO(content)
                    reader = PdfReader(pdf_stream) # Đọc từ "file ảo"
                    for page in reader.pages:
                        full_text += page.extract_text() + "\n"
                    print("   (extract_text) ✅ Sửa lỗi header và đọc lại thành công!", flush=True)
                else:
                    # Nếu không phải lỗi newline thừa, báo lỗi thực sự
                    print(f"   (extract_text) ❌ Lỗi header không phải do whitespace thừa: {content[:10]}", flush=True)
                    return None # Trả về None nếu không sửa được
            except Exception as inner_e:
                # Bắt lỗi nếu quá trình sửa cũng thất bại
                print(f"   (extract_text) ❌ Lỗi khi đang cố sửa header: {inner_e}", flush=True)
                import traceback
                traceback.print_exc()
                return None # Trả về None nếu sửa lỗi thất bại
        else:
            # Nếu là lỗi PdfReadError khác (không phải header)
             print(f"   (extract_text) ❌ Lỗi PdfReadError không xác định: {e}")
             return None # Trả về None

    except FileNotFoundError:
        print(f"❌ LỖI: Không tìm thấy file '{pdf_path}'.")
        print("💡 Gợi ý: Hãy chắc chắn file PDF và file read_cv4.py NẰM CHUNG 1 THƯ MỤC.")
        return None
    except Exception as e:
        # Bắt các lỗi chung khác
        print(f"   (extract_text) ❌ Lỗi không xác định khi đọc PDF: {e}")
        return None

    # Dọn dẹp text cuối cùng
    full_text = re.sub(r' +', ' ', full_text)
    full_text = re.sub(r'\n+', '\n', full_text).strip()
    return full_text

# === BƯỚC 2A: "BỘ NÃO" V7 (TRÍCH XUẤT CHO NGƯỜI XEM) ===
def create_flexible_pattern(keyword):
    """Tạo regex pattern 'thông minh', xử lý dãn chữ (H O Ạ T)"""
    pattern_chars = r'\s*'.join(re.escape(c) for c in keyword)
    return r"(?:^|\n)\s*" + pattern_chars + r"\s*(?:\n|$)"

def extract_key_info(cv_text):
    """Dùng Regex V7 để "tái cấu trúc" CV đa dạng (Anh/Việt, 1/2 cột)."""
    info = {
        "email": None, "phone": None, "links": [], "gpa": None,
        "education": None, "skills": None, "projects": None,
        "activities": None, "certificates": None, "experience": None,
        "objective": None, "info": None,
    }

    # === Phần 1: Trích xuất thông tin đơn lẻ (Đa dạng) ===
    email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", cv_text)
    if email_match: info["email"] = email_match.group(0)
    phone_match = re.search(r"(\(?\+?\d{1,4}\)?[\s.-]?)?(\d[\s.-]?){8,12}", cv_text)
    if phone_match: info["phone"] = phone_match.group(0).strip()
    link_matches = re.findall(r"(https?://[^ \t<>()]+|www\.[^ \t<>()]+)", cv_text)
    if link_matches: info["links"] = [re.sub(r'\n', '', link) for link in link_matches]
    gpa_match = re.search(r"(GPA|CGPA)\s*:?.*?([\d\.]+)", cv_text, re.IGNORECASE | re.DOTALL)
    if gpa_match: info["gpa"] = gpa_match.group(2).strip()

    # === Phần 2: "Bộ Não" V7 - Trích xuất Section (Đa Ngôn Ngữ) ===
    ALL_SECTION_DEFINITIONS = {
        "education":    ["Học vấn", "EDUCATION"],
        "experience":   ["Kinh nghiệm làm việc", "INTERNSHIPS", "INTERNSHIP", "EXPERIENCE"],
        "projects":     ["Dự án cá nhân", "PROJECTS", "DESIGN PROJECT"],
        "skills":       ["Kỹ năng", "SKILLS", "PROGRAMMING SKILLS"],
        "activities":   ["Hoạt động", "ACHIEVEMENTS & ACTIVITIES", "ACHIEVEMENTS"],
        "certificates": ["Chứng chỉ", "CERTIFICATES", "CERTIFICATIONS"],
        "objective":    ["Mục tiêu nghề nghiệp", "CAREER OBJECTIVE", "OBJECTIVE"],
        "info":         ["Thông tin thêm", "STRENGTHS", "HOBBIES", "LANGUAGE"]
    }
    section_matches = []
    for key, titles in ALL_SECTION_DEFINITIONS.items():
        for title in titles:
            pattern = create_flexible_pattern(title)
            match = re.search(pattern, cv_text, re.IGNORECASE)
            if match:
                section_matches.append((match.start(), key, match))
                break
    section_matches.sort(key=lambda x: x[0])

    for i in range(len(section_matches)):
        current_key = section_matches[i][1]
        current_match = section_matches[i][2]
        start_index = current_match.end()
        end_index = len(cv_text)
        if i < len(section_matches) - 1:
            end_index = section_matches[i+1][0]
        content = cv_text[start_index:end_index].strip()
        content = re.sub(r'^[\n\s]+|[\n\s]+$', '', content)
        content = re.sub(r'(\n\s*){2,}', '\n', content)
        if content:
            if info[current_key]: info[current_key] += "\n" + content
            else: info[current_key] = content
    return info

# === BƯỚC 2B: "CON MẮT" AI (VECTOR HÓA CHO MÁY HỌC) ===
g_model_mbert = None
g_tokenizer_mbert = None

def get_cv_vector_mbert(cv_text):
    """Dùng "Con Mắt" mBERT để biến CV thành vector."""
    global g_model_mbert, g_tokenizer_mbert
    try:
        if g_model_mbert is None:
            print(f"   (get_cv_vector) Đang tải 'Con Mắt' AI ({config.MBERT_MODEL_NAME})...")
            g_tokenizer_mbert = AutoTokenizer.from_pretrained(config.MBERT_MODEL_NAME)
            g_model_mbert = AutoModel.from_pretrained(config.MBERT_MODEL_NAME)
            print("   (get_cv_vector) ✅ 'Con Mắt' mBERT đã sẵn sàng!")

        inputs = g_tokenizer_mbert(
            cv_text, return_tensors="pt", max_length=config.MAX_TOKEN_LENGTH,
            truncation=True, padding=True, return_overflowing_tokens=True
        )
        num_chunks = inputs.input_ids.shape[0]
        if num_chunks > 1:
            print(f"   (get_cv_vector) 💡 CV quá dài, 'băm' thành {num_chunks} mẩu.")

        with torch.no_grad():
            outputs = g_model_mbert(
                input_ids=inputs['input_ids'],
                attention_mask=inputs['attention_mask']
            )
        cls_vectors = outputs.last_hidden_state[:, 0, :]
        cv_vector = torch.mean(cls_vectors, dim=0).unsqueeze(0)
        return cv_vector
    except Exception as e:
       
        return None

# --- BƯỚC 3: HÀM CHẠY CHÍNH (GỌI CẢ 2 BỘ NÃO) ---
def main():
    if len(sys.argv) < 2:
        print("❌ Lỗi: Vui lòng cung cấp tên file PDF.")
        print("💡 Ví dụ: python read_cv4.py LyMinh-CV.pdf")
        return

    pdf_file_name = sys.argv[1]
    print(f"\n--- Bắt đầu xử lý file: {pdf_file_name} ---")

    # === BƯỚC 1: ĐỌC TEXT (Đã nâng cấp) ===
    cv_text = extract_text_from_pdf(pdf_file_name)

    if cv_text:
        print("✅ Đọc text thành công!")
        # === BƯỚC 2A: TRÍCH XUẤT (CHO NGƯỜI) ===
        print("\n--- Chạy Bộ Não Regex V7 (Trích xuất) ---")
        results = extract_key_info(cv_text)
        print("   ✅ Trích xuất Regex hoàn tất.")

        # === BƯỚC 2B: VECTOR HÓA (CHO MÁY) - Đọc từ config.py ===
        if config.ENABLE_VECTOR:
            print("\n--- Chạy Con Mắt AI mBERT (Vector hóa) ---")
            vector_result = get_cv_vector_mbert(cv_text)
            if vector_result is not None:
                 print("   ✅ Vector hóa hoàn tất.")
            else:
                 print("   ❌ Vector hóa thất bại.")
        else:
            print(f"\n--- ⚡ Bỏ qua Vector hóa (config.ENABLE_VECTOR={config.ENABLE_VECTOR}) ---")
            vector_result = None


        # === BƯỚC 3: IN KẾT QUẢ TỔNG HỢP ===
        print("\n=============================================")
        print(f"   KẾT QUẢ ĐỌC CV (Bộ Não V8) - {pdf_file_name}")
        print("=============================================")

        print("\n--- PHẦN 1: TRÍCH XUẤT (CHO NGƯỜI XEM) ---")
        print(f"📧 Email:    {results.get('email', 'N/A')}")
        print(f"📱 Phone:    {results.get('phone', 'N/A')}")
        print(f"🎓 GPA/CGPA: {results.get('gpa', 'N/A')}")

        print("\n--- 🔗 LINKS ---")
        if results.get('links'):
            for link in results['links']: print(f"  • {link}")
        else: print("  (Không tìm thấy)")

        print("\n--- 🎓 HỌC VẤN (EDUCATION) ---")
        print(results.get('education', '  (Không tìm thấy)'))

        print("\n--- 💼 KINH NGHIỆM / THỰC TẬP (EXPERIENCE/INTERNSHIP) ---")
        print(results.get('experience', '  (Không tìm thấy)'))

        print("\n--- 🚀 DỰ ÁN (PROJECTS) ---")
        print(results.get('projects', '  (Không tìm thấy)'))

        print("\n--- 🛠️ KỸ NĂNG (SKILLS) ---")
        print(results.get('skills', '  (Không tìm thấy)'))

        # === IN KẾT QUẢ CỦA "CON MẮT" AI ===
        print("\n--- PHẦN 2: VECTOR 'DẤU VÂN TAY' (CHO MÁY HỌC) ---")
        if config.ENABLE_VECTOR and vector_result is not None:
            print(f"✅ Vector 'Dấu vân tay' đã được tạo!")
            print(f"   • Kích thước: {vector_result.shape}")
            print(f"   • 10 số đầu: {vector_result[0, :10].numpy()}")
        elif config.ENABLE_VECTOR and vector_result is None:
            print("  (Không thể tạo vector)")
        else:
            print(f"  ⚡ Vector hóa đã TẮT (config.ENABLE_VECTOR={config.ENABLE_VECTOR})")

        print("\n=============================================\n")
    else:
         print(f"❌ Không thể xử lý file '{pdf_file_name}' do lỗi đọc PDF.")


if __name__ == "__main__":
    main()