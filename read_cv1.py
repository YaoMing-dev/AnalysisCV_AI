import sys
import re
from pypdf import PdfReader

# --- BƯỚC 1: "ĐỌC" FILE PDF LẤY CHỮ ---
def extract_text_from_pdf(pdf_path):
    """Trích xuất toàn bộ text từ file PDF"""
    try:
        reader = PdfReader(pdf_path)
        full_text = ""
        for page in reader.pages:
            full_text += page.extract_text() + "\n"
        
        # Dọn dẹp text (thay nhiều \n bằng 1, nhiều dấu cách bằng 1)
        full_text = re.sub(r' +', ' ', full_text)
        full_text = re.sub(r'\n+', '\n', full_text).strip()
        return full_text
    except FileNotFoundError:
        print(f"❌ LỖI: Không tìm thấy file '{pdf_path}'.")
        return None
    except Exception as e:
        print(f"❌ Lỗi khi đọc PDF: {e}")
        return None

# --- BƯỚC 2: "BỘ NÃO" TRÍCH XUẤT (V6 - TÁI CẤU TRÚC) ---
def create_flexible_pattern(keyword):
    """
    Tạo regex pattern 'thông minh', xử lý dãn chữ (H O Ạ T)
    và đảm bảo nó là một tiêu đề (đứng đầu 1 dòng, 
    có thể có dấu cách hoặc \n ở trước)
    """
    # \s* = 0 hoặc nhiều dấu cách/xuống dòng
    # (?:^|\n) = Bắt đầu từ đầu file (^) HOẶC ( | ) bắt đầu từ 1 dòng mới (\n)
    pattern_chars = r'\s*'.join(re.escape(c) for c in keyword)
    return r"(?:^|\n)\s*" + pattern_chars + r"\s*(?:\n|$)"

def extract_key_info(cv_text):
    """
    Dùng Regex V6 để "tái cấu trúc" CV 2 cột và trích xuất.
    """
    info = {
        "email": None,
        "phone": None,
        "links": [],
        "gpa": None,
        "skills": None,
        "projects": None,
        "activities": None,
        "certificates": None,
        "experience": None,
    }

    # === Phần 1: Trích xuất thông tin đơn lẻ (Giống V3) ===
    # (Những thông tin này thường nằm chung 1 chỗ nên ít bị ảnh hưởng)
    email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", cv_text)
    if email_match: info["email"] = email_match.group(0)

    phone_match = re.search(r"0\d{9}", cv_text)
    if phone_match: info["phone"] = phone_match.group(0)

    link_matches = re.findall(r"(https?://[^ \t<>()]+|www\.[^ \t<>()]+)", cv_text)
    if link_matches:
        info["links"] = [re.sub(r'\n', '', link) for link in link_matches]

    gpa_match = re.search(r"GPA\s*:?.*?([\d\.]+)", cv_text, re.IGNORECASE | re.DOTALL)
    if gpa_match: info["gpa"] = gpa_match.group(1).strip()

    # === Phần 2: "Bộ Não" V6 - Trích xuất Section bằng cách Sắp xếp ===
    
    # 1. Định nghĩa TẤT CẢ các tiêu đề
    # (Tên key, Tiêu đề 1, Tiêu đề 2 (nếu có))
    ALL_SECTION_DEFINITIONS = {
        "experience":   ["Kinh nghiệm làm việc"],
        "projects":     ["Dự án cá nhân"],
        "education":    ["Học vấn"],
        "skills":       ["Kỹ năng"],
        "activities":   ["Hoạt động"],
        "certificates": ["Chứng chỉ"],
        "objective":    ["Mục tiêu nghề nghiệp"],
        "info":         ["Thông tin thêm"]
    }

    section_matches = []
    
    # 2. "Định vị" (Locate) tất cả tiêu đề
    for key, titles in ALL_SECTION_DEFINITIONS.items():
        for title in titles:
            pattern = create_flexible_pattern(title)
            match = re.search(pattern, cv_text, re.IGNORECASE)
            if match:
                # Lưu (vị trí, tên section, object match)
                section_matches.append((match.start(), key, match))
                break # Tìm thấy 1 title là đủ cho section này
    
    # 3. "Sắp xếp" (Sort) các section theo vị trí
    section_matches.sort(key=lambda x: x[0]) # Sắp xếp theo vị trí (index 0)

    # 4. "Trích xuất" (Extract)
    for i in range(len(section_matches)):
        current_key = section_matches[i][1]
        current_match = section_matches[i][2]
        
        start_index = current_match.end() # Bắt đầu đọc từ sau tiêu đề
        end_index = len(cv_text)          # Mặc định là hết file
        
        # Tìm "Điểm Kết Thúc" (là "Điểm Bắt Đầu" của section tiếp theo)
        if i < len(section_matches) - 1:
            end_index = section_matches[i+1][0] # Vị trí bắt đầu của section sau
            
        # "Cắt" nội dung
        content = cv_text[start_index:end_index].strip()
        
        # Dọn dẹp nội dung
        content = re.sub(r'^[\n\s]+|[\n\s]+$', '', content) # Xóa dòng trống đầu/cuối
        content = re.sub(r'(\n\s*){2,}', '\n', content)     # Xóa dòng trống thừa
        
        # Gán vào kết quả
        if content:
            info[current_key] = content

    return info

# --- BƯỚC 3: HÀM CHẠY CHÍNH (Đã nâng cấp để in ra) ---
def main():
    if len(sys.argv) < 2:
        print("❌ Lỗi: Vui lòng cung cấp tên file PDF.")
        print("💡 Ví dụ: python read_cv.py LyMinh-CV.pdf")
        return

    pdf_file_name = sys.argv[1]

    print(f"Đang đọc file '{pdf_file_name}'...")
    cv_text = extract_text_from_pdf(pdf_file_name)
    
    if cv_text:
        print("✅ Đọc file thành công! Đang trích xuất thông tin...")
        
        results = extract_key_info(cv_text)
        
        # --- IN KẾT QUẢ RA TERMINAL ---
        print("\n=============================================")
        print("   AI ĐÃ ĐỌC VÀ TRÍCH XUẤT KẾT QUẢ (V6)")
        print("=============================================")
        
        print("\n--- THÔNG TIN CƠ BẢN ---")
        print(f"📧 Email:    {results['email']}")
        print(f"📱 Phone:    {results['phone']}")
        print(f"🎓 GPA:      {results['gpa']}")
        
        print("\n--- LINKS ---")
        if results['links']:
            for link in results['links']: print(f"  • {link}")
        else: print("  (Không tìm thấy)")
        
        # --- CÁC SECTION ĐÃ TÓM TẮT (V6) ---
        
        print("\n--- 💼 KINH NGHIỆM LÀM VIỆC ---")
        if results['experience']:
            print(results['experience'])
        else: print("  (Không tìm thấy)")
            
        print("\n--- 🚀 DỰ ÁN CÁ NHÂN ---")
        if results['projects']:
            print(results['projects'])
        else: print("  (Không tìm thấy)")

        print("\n--- 🌟 HOẠT ĐỘNG ---")
        if results['activities']:
            print(results['activities'])
        else: print("  (Không tìm thấy)")
            
        print("\n--- 🏆 CHỨNG CHỈ ---")
        if results['certificates']:
            print(results['certificates'])
        else: print("  (Không tìm thấy)")
            
        print("\n--- 🛠️ KỸ NĂNG ---")
        if results['skills']:
            print(results['skills'])
        else: print("  (Không tìm thấy)")
            
        print("\n=============================================\n")


if __name__ == "__main__":
    main()