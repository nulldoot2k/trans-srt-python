# SRT Translator
SRT Translator là một ứng dụng web đơn giản, mạnh mẽ giúp dịch phụ đề file .srt từ ngôn ngữ nguồn sang ngôn ngữ đích một cách nhanh chóng và chính xác.

Ứng dụng hỗ trợ hai chế độ dịch:

- Chế độ miễn phí nhanh: sử dụng Google Translate (không cần API key, không giới hạn)
- Chế độ chất lượng cao: sử dụng các mô hình AI mạnh mẽ (Groq, Google Gemini, OpenAI)

# Tính năng nổi bật

- Giao diện đẹp, hiện đại, dễ sử dụng
- Hỗ trợ auto detect ngôn ngữ nguồn
- Hiển thị tiến độ dịch theo thời gian thực (progress bar + thời gian ước tính còn lại)
- Xem trước nội dung phụ đề đã dịch
- Tải file .srt đã dịch về máy
- Hỗ trợ dịch lại file mới mà không cần tải lại trang
- Chế độ miễn phí hoạt động ổn định với số lượng phụ đề lớn
- Tích hợp cache để tăng tốc dịch lặp lại
- Bảo mật API key bằng .env và localStorage

# Công nghệ sử dụng

- Backend: Python + Flask
- Frontend: HTML5 + CSS3 (backdrop-filter, gradient) + Vanilla JavaScript
- Dịch miễn phí: Google Translate (parallel requests với ThreadPoolExecutor)
- Dịch AI: Groq / Google Gemini / OpenAI (batch translation)
- Tối ưu: Rate limiting (Flask-Limiter), caching, progress polling, thread-safe variables
- Deployment: Dễ dàng container hóa với Docker & Docker Compose

# Cấu trúc thư mục

```
├── app.py                  # Backend Flask chính
├── requirements.txt        # Dependencies
├── .env                    # API keys (không commit lên git!)
├── README.md
└── statis/
    ├── index.html          # Trang chính
    ├── main.js             # Logic frontend (upload, progress, translation)
    └── style.css           # Giao diện đẹp mắt
```

# Cài đặt & Chạy Docker

```
git clone <your-repo-url>
cd srt-translator
cp .env.example .env
docker-compose up -d
```

Truy cập: http://localhost:5000
