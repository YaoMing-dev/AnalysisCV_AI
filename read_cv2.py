import sys
import re
from pypdf import PdfReader

# Fix encoding cho Windows console để hiển thị tiếng Việt
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# --- BƯỚC 1: "ĐỌC" FILE PDF LẤY CHỮ ---
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
        # LỖI KINH ĐIỂN: Đây là lỗi khi bạn chạy lệnh ở sai thư mục
        print(f"❌ LỖI: Không tìm thấy file '{pdf_path}'.")
        print("💡 Gợi ý: Hãy chắc chắn file PDF và file read_cv.py NẰM CHUNG 1 THƯ MỤC.")
        return None
    except Exception as e:
        print(f"❌ Lỗi khi đọc PDF: {e}")
        return None

# --- BƯỚC 2: "BỘ NÃO" TRÍCH XUẤT (V7 - ĐA NGÔN NGỮ & ĐA DẠNG) ---
def create_flexible_pattern(keyword):
    """
    Tạo regex pattern 'thông minh', xử lý dãn chữ (H O Ạ T)
    """
    pattern_chars = r'\s*'.join(re.escape(c) for c in keyword)
    return r"(?:^|\n)\s*" + pattern_chars + r"\s*(?:\n|$)"

def extract_key_info(cv_text):
    """
    Dùng Regex V7 để "tái cấu trúc" CV đa dạng (Anh/Việt, 1/2 cột).
    """
    info = {
        "email": None,
        "phone": None,
        "links": [],
        "gpa": None,
        "education": None,
        "skills": None,
        "projects": None,
        "activities": None,
        "certificates": None,
        "experience": None,
        "objective": None,
        "info": None,  # Thêm key "info" để khớp với ALL_SECTION_DEFINITIONS
    }

    # === Phần 1: Trích xuất thông tin đơn lẻ (Đa dạng) ===
    
    # 1. Email (Giữ nguyên, Regex này đã đa dạng)
    email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", cv_text)
    if email_match: info["email"] = email_match.group(0)

    # 2. Phone (*** CẢI TIỆN V7 ***: Đọc SĐT quốc tế +91, 070...)
    phone_match = re.search(r"(\(?\+?\d{1,4}\)?[\s.-]?)?(\d[\s.-]?){8,12}", cv_text)
    if phone_match: info["phone"] = phone_match.group(0).strip()

    # 3. Links (Giữ nguyên V3)
    link_matches = re.findall(r"(https?://[^ \t<>()]+|www\.[^ \t<>()]+)", cv_text)
    if link_matches:
        info["links"] = [re.sub(r'\n', '', link) for link in link_matches]

    # 4. GPA (*** CẢI TIỆN V7 ***: Tìm GPA hoặc CGPA)
    gpa_match = re.search(r"(GPA|CGPA)\s*:?.*?([\d\.]+)", cv_text, re.IGNORECASE | re.DOTALL)
    if gpa_match: info["gpa"] = gpa_match.group(2).strip() # group(2) là con số

    # === Phần 2: "Bộ Não" V7 - Trích xuất Section (Đa Ngôn Ngữ) ===
    
    # 1. Định nghĩa TẤT CẢ các tiêu đề đồng nghĩa (Anh/Việt)
    #    ĐÂY LÀ PHẦN "CẢI THIỆN" BẠN CẦN
    ALL_SECTION_DEFINITIONS = {
        "education":    ["Học vấn", "EDUCATION"],
        "experience":   ["Kinh nghiệm làm việc", "INTERNSHIPS", "INTERNSHIP", "EXPERIENCE"],
        "projects":     ["Dự án cá nhân", "PROJECTS", "DESIGN PROJECT"],
        "skills":       ["Kỹ năng", "SKILLS", "PROGRAMMING SKILLS"],
        "activities":   ["Hoạt động", "ACHIEVEMENTS & ACTIVITIES", "ACHIEVEMENTS"],
        "certificates": ["Chứng chỉ", "CERTIFICATES", "CERTIFICATIONS"],
        "objective":    ["Mục tiêu nghề nghiệp", "CAREER OBJECTIVE", "OBJECTIVE"],
        "info":         ["Thông tin thêm", "STRENGTHS", "HOBBIES", "LANGUAGE"] # Các mục phụ
    }

    section_matches = []
    
    # 2. "Định vị" (Locate) tất cả tiêu đề
    for key, titles in ALL_SECTION_DEFINITIONS.items():
        for title in titles:
            pattern = create_flexible_pattern(title)
            match = re.search(pattern, cv_text, re.IGNORECASE)
            if match:
                section_matches.append((match.start(), key, match))
                break 
    
    # 3. "Sắp xếp" (Sort) các section theo vị trí
    section_matches.sort(key=lambda x: x[0]) 

    # 4. "Trích xuất" (Extract)
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
            if info[current_key]:
                info[current_key] += "\n" + content # Nối skills và programming skills
            else:
                info[current_key] = content

    return info

# --- BƯỚC 3: HÀM CHẠY CHÍNH (Đã nâng cấp để in ra) ---
def main():
    if len(sys.argv) < 2:
        print("❌ Lỗi: Vui lòng cung cấp tên file PDF.")
        print("💡 Ví dụ: python read_cv.py LyMinh-CV.pdf")
        return

    pdf_file_name = sys.argv[1]

    print(f"\nĐang đọc file '{pdf_file_name}'...")
    cv_text = extract_text_from_pdf(pdf_file_name)
    
    if cv_text:
        print("✅ Đọc file thành công! Đang trích xuất thông tin...")
        
        results = extract_key_info(cv_text)
        
        print("\n=============================================")
        print(f"   KẾT QUẢ ĐỌC CV (Bộ Não V7) - {pdf_file_name}")
        print("=============================================")
        
        print("\n--- THÔNG TIN CƠ BẢN ---")
        print(f"📧 Email:    {results['email']}")
        print(f"📱 Phone:    {results['phone']}")
        print(f"🎓 GPA/CGPA: {results['gpa']}")
        
        print("\n--- 🔗 LINKS ---")
        if results['links']:
            for link in results['links']: print(f"  • {link}")
        else: print("  (Không tìm thấy)")
        
        print("\n--- 🎯 MỤC TIÊU (OBJECTIVE) ---")
        if results['objective']:
            print(results['objective'])
        else: print("  (Không tìm thấy)")
            
        print("\n--- 🎓 HỌC VẤN (EDUCATION) ---")
        if results['education']:
            print(results['education'])
        else: print("  (Không tìm thấy)")
            
        print("\n--- 💼 KINH NGHIỆM / THỰC TẬP (EXPERIENCE/INTERNSHIP) ---")
        if results['experience']:
            print(results['experience'])
        else: print("  (Không tìm thấy)")
            
        print("\n--- 🚀 DỰ ÁN (PROJECTS) ---")
        if results['projects']:
            print(results['projects'])
        else: print("  (Không tìm thấy)")
            
        print("\n--- 🌟 HOẠT ĐỘNG / THÀNH TÍCH (ACTIVITIES/ACHIEVEMENTS) ---")
        if results['activities']:
            print(results['activities'])
        else: print("  (Không tìm thấy)")
            
        print("\n--- 🏆 CHỨNG CHỈ (CERTIFICATES) ---")
        if results['certificates']:
            print(results['certificates'])
        else: print("  (Không tìm thấy)")
            
        print("\n--- 🛠️ KỸ NĂNG (SKILLS) ---")
        if results['skills']:
            print(results['skills'])
        else: print("  (Không tìm thấy)")
            
        print("\n=============================================\n")

if __name__ == "__main__":
    main()