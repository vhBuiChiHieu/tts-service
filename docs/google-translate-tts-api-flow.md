# Phân tích luồng hoạt động Google Translate Web TTS API (Undocumented)

Tài liệu này ghi chú luồng chi tiết cách extension Read Aloud gọi "chui" (undocumented) vào API của Google Translate Web để thực hiện Text-to-Speech (TTS) hoàn toàn miễn phí, mô phỏng lại cách trang `translate.google.com` gọi âm thanh khi người dùng nhấn nút "Nghe".

## 1. Giới hạn độ dài và phân mảnh văn bản
Frontend của Google Translate giới hạn độ dài cho một lần gọi âm thanh (thường là khoảng 200 ký tự) để ngăn lạm dụng. Do đó, bước đầu tiên trước khi gửi request là phải băm nhỏ chuỗi văn bản dài đầu vào thành nhiều đoạn ngắn:

- Thuật toán có thể cắt ranh giới câu bằng dấu ngắt câu `. , ; ? !` để đảm bảo ngữ điệu đoạn đọc không bị mất tự nhiên.
- Dưới dạng API service mới, bạn cũng cần mô phỏng lại một text chunker như logic `CharBreaker(200)` của Read Aloud.

## 2. Bước quan trọng: Khởi tạo và cào (Scrape) hệ thống Token `WIZ_global_data`
Hệ thống Web của Google sử dụng cơ chế nội bộ là `WIZ_global_data` đóng vai trò xác thực phiên giao dịch, tránh fake request.
Bạn cần phải thực hiện một HTTP `GET` request thông thường trỏ tới link hệ thống: `https://translate.google.com/`.

Sau khi nhận trả về giao diện HTML, bạn dùng Regex để truy xuất các Token ẩn trong mảng Javascript:
- **`f.sid`**: (Regex pattern `"FdrFJe":"(.*?)"`)
- **`bl`**: Build ID của frontend hiện tại (Regex pattern `"cfb2h":"(.*?)"`)
- **`at`**: Payload Token Authorization, chống giả mạo như XSRF (Regex pattern `"SNlM0e":"(.*?)"`)

Quá trình quét Regex này sẽ lấy ra 3 key. Bạn nên lưu trữ (Cache) 3 giá trị này cho các request phía sau, và set thời gian sinh trưởng (TTL) của chúng là tầm **1 giờ** (nghĩa là 1 giờ sau mới đi bào lại HTML một lần cho tối ưu).

## 3. Tạo Payload RPC và thực thi Request `batchexecute`
Sử dụng các WIZ token đã lấy được, bạn mô phỏng luồng gọi thủ tục từ xa RPC chuyên dùng của Google gọi là `batchexecute`.

Endpoint gọi API: 
```http
POST https://translate.google.com/_/TranslateWebserverUi/data/batchexecute
```

### Parameter và Body của Request:
1. Gắn Params vào **Query String** (URL):
   - `rpcids`: `jQ1olc` (đây là ID bắt buộc đặc thù của thủ tục gọi Synthesize Speech).
   - `f.sid`: giá trị token lấy ở bước 2.
   - `bl`: giá trị token lấy ở bước 2.
   - `hl`: `"en"`
   - `soc-app`: `1`
   - `soc-platform`: `1`
   - `soc-device`: `1`
   - `_reqid`: Một mã ID render ngẫu nhiên theo số nguyên tịnh tiến.
   - `rt`: `"c"`

2. Khởi tạo **Body** định dạng URL-encoded (application/x-www-form-urlencoded):
   - `at`: giá trị token lấy ở bước 2.
   - `f.req`: Payload được JSON hóa nhiều lớp mảng lồng nhau, chứa văn bản và ngôn ngữ (ví dụ `"vi"`), cụ thể format như sau:
     ```json
     [[["jQ1olc", "[\\"Văn bản cần đọc\\", \\"vi\\", null]", null, "generic"]]]
     ```
     > **Lưu ý**: Chú ý cẩn thận cách chuỗi nội dung JSON.stringify được nhồi vào mảng cha và bị escape dấu nháy!

## 4. Bóc tách JSON Response và lấy File âm thanh MP3 (Base64 Encode)
Giao tiếp RPC Batch Execute của Google sẽ trả về một cấu trúc dữ liệu chuỗi khá "dị", nhiều dãy text nối tiếp nhau bằng số ký tự của từng đoạn chuỗi JSON.

Cách phân rã kết quả:
1. Tìm con số khai báo độ dài chuỗi ở ngay đầu nội dung body (dùng Regex `\d+`).
2. Lấy con số này (index) và tiến hành `JSON.parse` nội dung của chuỗi vừa bóc tách đó (đây là chuỗi json mảng metadata envelopes phản hồi).
3. Sau khi Deserialize ra mảng Envelopes thì đi theo Index tới mốc lõi của kết quả: 
   `payload = envelopes[0][2]`
4. Deserialize String Payload đó thêm một lần nữa (`JSON.parse(payload)`), bạn sẽ thu được mảng âm thanh.
5. Truy cập `payload[0]` mang định dạng **Base64 String** thuần túy của nội dung âm thanh MP3.

Bạn có thể nối kèm Prefix `"data:audio/mpeg;base64," + payload[0]` vào để test trực tiếp trên Web Browser HTML5, hoặc decode trên Server để trả về `.mp3` nhị phân (Buffer) cho các Client/App sử dụng.

## 5. Những lưu ý "Vàng" để tránh lỗi khi build Backend Service

Để service hoạt động trơn tru 100% bằng NodeJS/Python/Go, bạn bắt buộc phải bổ sung những điểm sau (do Browser Extension đã tự động làm nên chúng ta không thấy trong code):

1. **Giả mạo Trình duyệt (Fake User-Agent):**
   Bạn BẮT BUỘC phải đính kèm Header `User-Agent` hợp lệ (VD: Chrome/114.0...) trong GET request lấy WIZ Token và POST request lấy âm thanh. Nếu dùng thư viện HTTP mặc định (như `axios` hay `node-fetch`), server của Google có thể chặn và trả về 403 Forbidden.

2. **Cấu hình Content-Type:**
   POST Request Body phải được stringify và encode theo đúng chuẩn Form. Header request `batchexecute` phải là:
   `Content-Type: application/x-www-form-urlencoded;charset=utf-8`

3. **URL Encoding cho Body:**
   Cái cục Payload `f.req` bắt buộc phải được bọc qua thư viện URL Encode thì server mới đọc được, ví dụ ở NodeJS:
   ```javascript
   const body = new URLSearchParams();
   body.append('f.req', JSON.stringify([[["jQ1olc", JSON.stringify([text, lang, null]), null, "generic"]]]));
   body.append('at', wizToken.at);
   ```

4. **Quản lý Cache & IP Rate-limit:**
   Do cách này hoàn toàn dựa vào API bị ẩn (Undocumented), Google có thể thắt chặt giới hạn rate-limit IP (bạn có thể dính Error 429 nếu gọi dồn dập). Nên có proxy loop hoặc giãn cách delay giữa các text chunks.

Dưới đây là Demo mô phỏng hàm call sau khi lấy được WIZ:
```javascript
async function synthesize(text, lang, wiz) {
   const url = `https://translate.google.com/_/TranslateWebserverUi/data/batchexecute?rpcids=jQ1olc&f.sid=${wiz['f.sid']}&bl=${wiz['bl']}&hl=en&soc-app=1&soc-platform=1&soc-device=1&_reqid=12345&rt=c`;
   
   const body = new URLSearchParams();
   body.append("f.req", JSON.stringify([[["jQ1olc", JSON.stringify([text, lang, null]), null, "generic"]]]));
   body.append("at", wiz["at"]);

   const response = await fetch(url, {
       method: "POST",
       headers: {
           "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
           "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36..."
       },
       body: body.toString()
   });

   const resText = await response.text();
   // Cắt lấy đoạn json payload và trả về base64 mp3...
}
```
