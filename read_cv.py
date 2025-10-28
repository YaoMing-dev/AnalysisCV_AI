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
        
        # Dọn dẹp text (giữ lại \n để regex mới hoạt động)
        full_text = re.sub(r' +', ' ', full_text) # Thay nhiều dấu cách bằng 1
        return full_text
    except FileNotFoundError:
        print(f"❌ LỖI: Không tìm thấy file '{pdf_path}'.")
        return None
    except Exception as e:
        print(f"❌ Lỗi khi đọc PDF: {e}")
        return None

# --- BƯỚC 2: "BỘ NÃO" TRÍCH XUẤT (V3 - CẢI TIỆN GPA) ---
def extract_key_info(cv_text):
    """
    Dùng Regex 'thông minh' hơn để trích xuất thông tin.
    """
    info = {
        "email": None,
        "phone": None,
        "links": [],
        "gpa": None,
        "skills": []
    }

    # 1. Quét Email (Regex cũ vẫn tốt)
    email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", cv_text)
    if email_match:
        info["email"] = email_match.group(0)

    # 2. Quét Số điện thoại (Regex cũ vẫn tốt)
    phone_match = re.search(r"0\d{9}", cv_text)
    if phone_match:
        info["phone"] = phone_match.group(0)

    # 3. Quét Links (Regex V2 đã tốt)
    link_matches = re.findall(r"(https?://[^ \t<>()]+|www\.[^ \t<>()]+)", cv_text)
    if link_matches:
        # Dọn dẹp link (xóa ký tự \n nếu có)
        info["links"] = [re.sub(r'\n', '', link) for link in link_matches]

    # 4. Quét GPA (*** CẢI TIỆN LẦN NỮA V3 ***)
    #    Regex này tìm "GPA" (không phân biệt hoa/thường)
    #    theo sau là (dấu cách, :, \n) BẤT KỲ
    #    và sau đó là con số (vd: 3.3)
    #    re.IGNORECASE = không phân biệt "GPA" hay "gpa"
    #    re.DOTALL = cho phép dấu . khớp với cả \n (xuống dòng)
    gpa_match = re.search(r"GPA\s*:?.*?([\d\.]+)", cv_text, re.IGNORECASE | re.DOTALL)
    
    if gpa_match:
        # group(1) bây giờ chỉ bắt số '3.3'
        info["gpa"] = gpa_match.group(1).strip() # Dùng .strip() để xóa khoảng trắng nếu có
    
    # 5. Quét Kỹ năng (Giữ nguyên)
    potential_skills = ["Python", "Java", "C#", ".NET", "ReactJS", "React Native", 
                        "SQL", "Docker", "Git", "SEO", "WordPress", "PHP"]
    
    found_skills = []
    for skill in potential_skills:
        if re.search(skill, cv_text, re.IGNORECASE):
            found_skills.append(skill)
    
    info["skills"] = list(set(found_skills)) # Dùng set() để loại bỏ trùng lặp

    return info

# --- BƯỚC 3: HÀM CHẠY CHÍNH (Không thay đổi) ---
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
        print("   AI ĐÃ ĐỌC VÀ TRÍCH XUẤT KẾT QUẢ (V3)")
        print("=============================================")
        print(f"📧 Email:    {results['email']}")
        print(f"📱 Phone:    {results['phone']}")
        print(f"🎓 GPA:      {results['gpa']}") # <-- Sẽ ra "3.3"
        
        print("\n🔗 Links:") # <-- Sẽ ra link đầy đủ
        if results['links']:
            for link in results['links']:
                print(f"  • {link}")
        else:
            print("  (Không tìm thấy)")

        print("\n🛠️ Kỹ năng (phát hiện được):")
        if results['skills']:
            print(f"  {', '.join(results['skills'])}")
        else:
            print("  (Không tìm thấy)")
        print("=============================================\n")


if __name__ == "__main__":
    main()