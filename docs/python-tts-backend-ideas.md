# Kiến trúc và Giải pháp xây dựng Python Local TTS Backend

Tài liệu này ghi chú lại các ý tưởng thiết kế và những lưu ý cốt lõi khi dùng Python dựng một Backend Service chạy cục bộ để gọi request "chui" sang API Google Translate, phục vụ riêng cho mục đích xử lý text siêu lớn (như dịch Audio Truyện chử).

## 1. Giới hạn HTTP Request & Chống Cấm IP (Rate-limit)
Dù chạy trên môi trường ở Local thì rate-limit vẫn tuân theo cơ chế của Google kiểm tra theo IP của người gửi (Public IP). Vì truyện chữ chứa số lượng từ rất lớn (có thể đẩy ra hàng trăm chunk cho một chương), gửi request dồn dập sẽ dẫn tới lỗi **HTTP 429 hoặc 403**.

- **Giải pháp:** Bắt buộc áp dụng cấu trúc luồng đồng bộ (Synchronous) bằng vòng lặp thay vì đa tiến trình (`asyncio` hoặc threading) cho các lệnh `fetch()`. Đồng thời rải thêm "Delay" nhân tạo vào hệ thống.
  ```python
  import time
  import random
  # ... xử lý chunk ...
  # Delay ngẫu nhiên từ 0.5 đến 1.5 giây sau mỗi lệnh lấy Audio
  time.sleep(random.uniform(0.5, 1.5))
  ```

## 2. Giải pháp Hợp nhất phần cứng Audio (Audio Merging)
File `mp3` sinh ra từ việc giải mã chuỗi `base64` trả về từ Google Translate bao gồm dữ liệu phần header lặp lại. Việc nối (concatenate) thẳng thừng các Byte arrays (bằng File Write Append) vẫn sẽ phát đươc âm thanh, nhưng do Header lặp lại, một số trình duyệt hay thiết bị di động có thể lỗi thanh tua nhanh (Seekbar), hoặc tính toán thời gian (Duration) sai.

- **Giải pháp:** Dùng thư viện `pydub` (chạy trên core `ffmpeg`). `pydub` sẽ parse và gộp nối các segment và sau đó render/export lại ra một file MP3 siêu chuẩn, header sạch đẹp, mượt mà và duration chính xác 100%.

## 3. Thuật toán Xử lý và Băm Văn Bản (Text Chunking/Pre-processing)
Text nguồn (Truyện chữ thường bẩn do ký tự vô hình từ trang trích xuất). Không bao giờ được dùng logic băm cứng "đúng X số ký tự thì xuống dòng" do sẽ làm lỡ câu, gây đọc vấp kinh hoàng.

- **Giải pháp:**
  1. Dùng `Regex` (Biểu thức chính quy) làm sạch dấu cách thừa, các đoạn "….", hoặc những ký tự đặc biệt vô nghĩa.
  2. Băm văn bản bước 1: dùng thư viện NLP (VD: thư viện `nltk` hàm `sent_tokenize` của Python) để mổ văn tự ra thành nhiều mảng "Câu gốc hoàn chỉnh".
  3. Băm văn bản bước 2: dùng vòng lặp nối từng câu nhỏ lại, nếu tổng ký tự lớn hơn 200 thì ngắt và tạo một Chunk mới.

## 4. Xử lý "Khựng Giọng" và Trải nghiệm thính giác
Audio giữa những Chunk độc lập thường bị dính vào nhau nếu bạn để tự động đọc. Khi nghe từ chương này qua chương khác có thể bị nhồi sóng âm không tự nhiên.

- **Giải pháp:** Sử dụng chính tính năng của `pydub` để chèn những "khoảng lặng" (Silent space).
  ```python
  from pydub import AudioSegment

  combined_audio = AudioSegment.empty()
  silent_blip = AudioSegment.silent(duration=250) # khoảng lùi 250 miligiay cho mỗi câu
  silent_break = AudioSegment.silent(duration=1000) # nghỉ 1 giây cho chuyển cảnh truyện

  # gộp trong vòng lặp bằng phép cộng +
  combined_audio += audio_chunk_segment + silent_blip 
  ```

## 5. Tóm tắt các Tool Stack Khuyên Dùng
- **Mảng HTTP:** Thư viện `requests` (xử lý WIZ Tokens và Form Urlencoded data siêu nhẹ).
- **Mảng Text:** `regex` và `nltk`.
- **Mảng Audio:** `pydub` kết hợp cài ứng dụng nền `ffpmeg` trên Windows.
