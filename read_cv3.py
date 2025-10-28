import sys
import re
import io
from pypdf import PdfReader
import torch
from transformers import AutoModel, AutoTokenizer

# === BẢN VÁ CỦA BẠN: Fix encoding cho Windows console ===
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# === BƯỚC 1: "ĐỌC" FILE PDF LẤY CHỮ ===
def extract_text_from_pdf(pdf_path):
    """Trích xuất toàn bộ text từ file PDF"""
    try:
        reader = PdfReader(pdf_path)
        full_text = ""
        for page in reader.pages:
            full_text += page.extract_text() + "\n"
        
        full_text = re.sub(r' +', ' ', full_text)
        full_text = re.sub(r'\n+', '\n', full_text).strip()
        return full_text
    except FileNotFoundError:
        print(f"❌ LỖI: Không tìm thấy file '{pdf_path}'.")
        print("💡 Gợi ý: Hãy chắc chắn file PDF và file read_cv3.py NẰM CHUNG 1 THƯ MỤC.")
        return None
    except Exception as e:
        print(f"❌ Lỗi khi đọc PDF: {e}")
        return None

# === BƯỚC 2A: "BỘ NÃO" V7 (TRÍCH XUẤT CHO NGƯỜI XEM) ===
# (Giữ nguyên logic "đa dạng" từ read_cv2.py)

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

# Chỉ load model 1 lần
g_model_mbert = None
g_tokenizer_mbert = None

def get_cv_vector_mbert(cv_text):
    """
    Dùng "Con Mắt" mBERT (đa ngôn ngữ) để "đọc" toàn bộ CV
    và biến nó thành 1 vector "dấu vân tay" (1, 768).
    """
    global g_model_mbert, g_tokenizer_mbert
    
    try:
        # 1. Tải "Con Mắt" (Chỉ tải 1 lần đầu tiên)
        if g_model_mbert is None:
            print("\nĐang tải 'Con Mắt' AI (mBERT) - (Chỉ tải 1 lần, có thể mất vài phút)...")
            model_name = "bert-base-multilingual-cased"
            g_tokenizer_mbert = AutoTokenizer.from_pretrained(model_name)
            g_model_mbert = AutoModel.from_pretrained(model_name)
            print("✅ 'Con Mắt' mBERT đã sẵn sàng!")

        # 2. "Băm" (Chunking) CV dài (Giống logic Colab)
        # mBERT có giới hạn 512 từ
        inputs = g_tokenizer_mbert(
            cv_text, 
            return_tensors="pt", 
            max_length=512,
            truncation=True,
            padding=True,
            return_overflowing_tokens=True # Tự động "băm"
        )
        
        num_chunks = inputs.input_ids.shape[0]
        if num_chunks > 1:
            print(f"💡 CV quá dài, 'Con Mắt' đã 'băm' thành {num_chunks} mẩu.")

        # 3. Đưa tất cả "mẩu" qua "Con Mắt"
        with torch.no_grad():
            outputs = g_model_mbert(
                input_ids=inputs['input_ids'],
                attention_mask=inputs['attention_mask']
            )

        # 4. Lấy vector tóm tắt (vector [CLS]) cho TỪNG mẩu
        cls_vectors = outputs.last_hidden_state[:, 0, :]
        
        # 5. Tính TRUNG BÌNH CỘNG của tất cả vector mẩu
        cv_vector = torch.mean(cls_vectors, dim=0).unsqueeze(0)
        
        return cv_vector

    except Exception as e:
        print(f"❌ Lỗi khi vector hóa CV: {e}")
        print("💡 Gợi ý: Hãy chắc chắn bạn đã cài đặt 'torch' và 'transformers'.")
        print("💡 Chạy lệnh: pip install torch transformers")
        return None

# --- BƯỚC 3: HÀM CHẠY CHÍNH (GỌI CẢ 2 BỘ NÃO) ---
def main():
    if len(sys.argv) < 2:
        print("❌ Lỗi: Vui lòng cung cấp tên file PDF.")
        print("💡 Ví dụ: python read_cv3.py LyMinh-CV.pdf")
        return

    pdf_file_name = sys.argv[1]
    print(f"\nĐang đọc file '{pdf_file_name}'...")
    
    # === BƯỚC 1: ĐỌC TEXT ===
    cv_text = extract_text_from_pdf(pdf_file_name)
    
    if cv_text:
        # === BƯỚC 2A: TRÍCH XUẤT (CHO NGƯỜI) ===
        print("✅ Đọc file thành công! Đang trích xuất (cho Người xem)...")
        results = extract_key_info(cv_text)
        
        # === BƯỚC 2B: VECTOR HÓA (CHO MÁY) ===
        print("\nĐang vector hóa (cho Máy học)...")
        vector_result = get_cv_vector_mbert(cv_text)

        # === BƯỚC 3: IN KẾT QUẢ TỔNG HỢP ===
        print("\n=============================================")
        print(f"   KẾT QUẢ ĐỌC CV (Bộ Não V8) - {pdf_file_name}")
        print("=============================================")
        
        print("\n--- PHẦN 1: TRÍCH XUẤT (CHO NGƯỜI XEM) ---")
        print(f"📧 Email:    {results['email']}")
        print(f"📱 Phone:    {results['phone']}")
        print(f"🎓 GPA/CGPA: {results['gpa']}")
        
        print("\n--- 🔗 LINKS ---")
        if results['links']:
            for link in results['links']: print(f"  • {link}")
        else: print("  (Không tìm thấy)")
            
        print("\n--- 🎓 HỌC VẤN (EDUCATION) ---")
        if results['education']: print(results['education'])
        else: print("  (Không tìm thấy)")
            
        print("\n--- 💼 KINH NGHIỆM / THỰC TẬP (EXPERIENCE/INTERNSHIP) ---")
        if results['experience']: print(results['experience'])
        else: print("  (Không tìm thấy)")
            
        print("\n--- 🚀 DỰ ÁN (PROJECTS) ---")
        if results['projects']: print(results['projects'])
        else: print("  (Không tìm thấy)")
            
        print("\n--- 🛠️ KỸ NĂNG (SKILLS) ---")
        if results['skills']: print(results['skills'])
        else: print("  (Không tìm thấy)")

        # === IN KẾT QUẢ CỦA "CON MẮT" AI ===
        print("\n--- PHẦN 2: VECTOR 'DẤU VÂN TAY' (CHO MÁY HỌC) ---")
        if vector_result is not None:
            print(f"✅ Vector 'Dấu vân tay' đã được tạo!")
            print(f"   • Kích thước: {vector_result.shape} (1 CV, 768 đặc trưng)")
            print(f"   • 10 số đầu: {vector_result[0, :10].numpy()}")
        else:
            print("  (Không thể tạo vector)")
            
        print("\n=============================================\n")

if __name__ == "__main__":
    main()