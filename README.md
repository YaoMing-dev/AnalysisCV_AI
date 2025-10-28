# AIreadCV-many-version-

Chào bạn,

Đây là một ý tưởng TUYỆT VỜI và là bước "chuẩn" cuối cùng. Dựa trên toàn bộ quá trình chúng ta xây dựng và gỡ lỗi (từ V1 đến V8), đây là một file README.md (hướng dẫn) hoàn chỉnh.

Nó giải thích dự án của bạn là gì, và quan trọng nhất, nó hướng dẫn "người khác" chính xác cách cài đặt và chạy nó (bao gồm cả venv và requirements.txt).

Bạn chỉ cần tạo một file mới tên là README.md trong thư mục D:\Dev\BasicAI (ngang hàng với read_cv3.py) và dán toàn bộ nội dung này vào.

(Bắt đầu nội dung file README.md từ đây)

 Trình phân tích CV bằng AI (AI CV Parser)
Đây là một dự án Python được xây dựng để "đọc" và "hiểu" các file CV PDF đa dạng. "Bộ não" AI này có khả năng chạy trên nhiều layout CV (1-2 cột) và xử lý cả tiếng Anh lẫn tiếng Việt.

Dự án này là kết quả của quá trình phát triển (V1-V8), với file read_cv3.py là phiên bản hoàn chỉnh nhất.

 Tính năng chính
"Bộ não" V8 (read_cv3.py) thực hiện 2 nhiệm vụ song song mỗi khi chạy:

Trích xuất (cho Người xem):

Sử dụng "Bộ não" Regex (V7) đa ngôn ngữ để "quét", "tái cấu trúc" và "tóm tắt" các mục quan trọng.

Hiểu đa ngôn ngữ: Nhận diện các tiêu đề tiếng Việt (Kinh nghiệm làm việc, Dự án cá nhân) và tiếng Anh (EXPERIENCE, PROJECTS).

Thông minh: Xử lý được CV 2 cột (lỗi text lộn xộn), lỗi dãn chữ (C H Ứ N G C H Ỉ), và lỗi xuống dòng (GPA:\n3.3).

Vector hóa (cho Máy học):

Sử dụng "Con Mắt" AI (bert-base-multilingual-cased) để "đọc" toàn bộ nội dung CV.

Tự động "băm" (chunking) các CV dài.

Tạo ra một vector "dấu vân tay" (1, 768) đại diện cho toàn bộ CV, sẵn sàng cho các tác vụ AI/ML (như train model chấm điểm, so sánh CV...).

📋 Yêu cầu
Python 3.7+

Các thư viện được liệt kê trong requirements.txt

⚙️ Hướng dẫn Cài đặt (Cho người dùng mới)
Đây là các bước để "người khác" có thể tải về và chạy dự án của bạn từ GitHub.

Bước 1: Tải code về (Clone)
Mở terminal của bạn và chạy lệnh sau:

Bash

git clone https://github.com/FemtoHell/AIreadCV-many-version-.git
Bước 2: Di chuyển vào thư mục dự án
Bash

cd AIreadCV-many-version-
(Hoặc tên thư mục bạn đã clone, ví dụ: cd BasicAI)

Bước 3: Tạo và Kích hoạt Môi trường ảo (VITAL)
Đây là bước quan trọng nhất để tránh xung đột thư viện.

1. Tạo môi trường ảo (tên là venv):

Bash

python -m venv venv
2. Kích hoạt môi trường ảo:

Trên Windows (Git Bash / PowerShell):

Bash

.\venv\Scripts\activate
Trên macOS / Linux:

Bash

source venv/bin/activate
(Bạn sẽ thấy chữ (venv) xuất hiện ở đầu dòng terminal)

Bước 4: Cài đặt "Phần Cứng" (Dependencies)
Dùng file requirements.txt đã được cung cấp để cài đặt chính xác các thư viện mà "bộ não" AI cần:

Bash

pip install -r requirements.txt
(Lệnh này sẽ tự động cài pypdf, torch, transformers... với đúng phiên bản)

🏃‍♂️ Cách sử dụng
Sau khi cài đặt xong, bạn đã sẵn sàng để "đọc" CV!

Thêm file CV: Đặt các file CV (dạng .pdf) của bạn vào chung thư mục với file read_cv3.py.

Chạy "Bộ Não" V8: (Hãy chắc chắn bạn vẫn đang ở trong (venv))

Sử dụng cú pháp: python [TÊN_SCRIPT] [TÊN_FILE_CV]

Ví dụ (Test CV Tiếng Việt):

Bash

python read_cv3.py LyMinh-CV.pdf
Ví dụ (Test CV Tiếng Anh 1):

Bash

python read_cv3.py CVpj_tweet.pdf
Ví dụ (Test CV Tiếng Anh 2):

Bash

python read_cv3.py Rosu_CV.pdf
📊 Giải thích Kết quả
Mỗi lần chạy, bạn sẽ nhận được 2 phần kết quả:

=============================================
   KẾT QUẢ ĐỌC CV (Bộ Não V8) - [Tên file CV]
=============================================

--- PHẦN 1: TRÍCH XUẤT (CHO NGƯỜI XEM) ---
📧 Email:    ...
🎓 GPA/CGPA: ...
--- 🚀 DỰ ÁN (PROJECTS) ---
... (Nội dung tóm tắt) ...

