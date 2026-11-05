# Hướng Dẫn Triển Khai Website "Bàn Ghép Cặp H4 & TradingAgents AI" Lên GitHub Pages

Hệ thống hoạt động hoàn toàn tự động và **miễn phí 100% trên GitHub**:
- **Tự động quét định kỳ:** GitHub Actions tự chạy mỗi giờ (phút thứ 07), lấy dữ liệu 28 cặp tiền tệ từ Yahoo Finance, tính sức mạnh tiền tệ CSM, tìm mô hình nến H4 đảo chiều, cập nhật dữ liệu lên trang web.
- **Báo cáo về Telegram:** Tự động gửi thông báo danh sách lệnh và biểu đồ phân tích trực tiếp về Telegram cá nhân/nhóm của bạn mỗi khi có nến 4 giờ mới đóng.
- **Trang web tương tác:** Bất kỳ ai có đường link đều có thể xem bảng sức mạnh, lệnh đề xuất, mô hình bị loại và mở popup thẩm định của Hội đồng Đa tác tử **TradingAgents AI**. Máy tính của bạn tắt thì hệ thống trên mạng vẫn chạy bình thường.

---

## BƯỚC 1. TẠO BOT TELEGRAM (NẾU MUỐN NHẬN BÁO CÁO VỀ ĐIỆN THOẠI)
*Nếu chỉ muốn dùng trang web mà không cần nhận tin Telegram, bạn có thể bỏ qua bước này.*

1. Mở Telegram, tìm kiếm bot **@BotFather**.
2. Gõ lệnh `/newbot`, đặt tên bot (ví dụ: `H4_TradingAgent_Bot`), sau đó đặt username kết thúc bằng `_bot` (ví dụ: `my_h4_tradingagent_bot`).
3. BotFather sẽ cấp cho bạn một chuỗi **HTTP API Token** (dạng `123456789:AAH...`). Hãy sao chép lại chuỗi này.
4. Mở bot bạn vừa tạo trên Telegram, bấm nút **Start** (Bắt đầu) và gửi một tin nhắn bất kỳ cho bot.
5. Để lấy Chat ID cá nhân: Tìm kiếm bot **@userinfobot**, bấm Start. Dòng số sau chữ **Id** chính là mã chat của bạn (ví dụ: `987654321`).

---

## BƯỚC 2. TẠO KHO LƯU TRỮ (REPOSITORY) TRÊN GITHUB

1. Đăng nhập vào [GitHub](https://github.com), bấm nút **New** (hoặc dấu `+` ở góc trên bên phải) để tạo repository mới.
2. Đặt tên kho lưu trữ: Ví dụ `SucManh_Nen_H4` hoặc `h4-tradingagent`.
3. Chọn chế độ: **Public** (để dùng được tính năng GitHub Pages miễn phí).
4. **Không** tích chọn "Add a README file" hay .gitignore (vì chúng ta đã chuẩn bị sẵn mã nguồn).
5. Bấm **Create repository**.

---

## BƯỚC 3. ĐẨY TOÀN BỘ MÃ NGUỒN LÊN GITHUB

Mở PowerShell trên máy tính và chạy lần lượt các lệnh sau (thay `<ten-tai-khoan>` và `<ten-repo>` bằng tài khoản GitHub của bạn):

```powershell
# Di chuyển vào thư mục dự án đã tạo sẵn
cd "e:\Jess Trade\h4-currency-tradingagent"

# Khởi tạo git và commit
git init
git add .
git commit -m "Khoi tao he thong Ban Ghep Cap H4 & TradingAgents AI"
git branch -M main

# Liên kết với kho GitHub vừa tạo
git remote add origin https://github.com/<ten-tai-khoan>/<ten-repo>.git

# Đẩy code lên GitHub
git push -u origin main
```

*(Lưu ý: Nếu GitHub yêu cầu đăng nhập, hãy làm theo hướng dẫn trên trình duyệt hoặc sử dụng GitHub Personal Access Token).*

---

## BƯỚC 4. BẬT TÍNH NĂNG TRANG WEB (GITHUB PAGES)

1. Trên trang repository của bạn trên GitHub, bấm vào tab **Settings** (Cài đặt) ở thanh menu trên cùng.
2. Ở cột menu bên trái, tìm và bấm vào mục **Pages**.
3. Tại phần **Build and deployment**:
   - **Source:** Chọn `Deploy from a branch`.
   - **Branch:** Chọn `main`, thư mục để mặc định là `/(root)`.
   - Bấm nút **Save**.
4. Chờ khoảng 1–2 phút, F5 tải lại trang. Bạn sẽ thấy dòng thông báo màu xanh kèm đường dẫn website cá nhân của bạn, dạng:
   👉 **`https://<ten-tai-khoan>.github.io/<ten-repo>/`**

---

## BƯỚC 5. CẤU HÌNH SECRET TELEGRAM (BẢO MẬT TUYỆT ĐỐI)

1. Vẫn trong phần **Settings** của repository, nhìn sang cột menu bên trái: Bấm vào **Secrets and variables** -> Chọn **Actions**.
2. Bấm nút **New repository secret** và lần lượt thêm 2 mục:
   - Mục 1:
     - Name: `TELEGRAM_TOKEN`
     - Secret: Dán chuỗi mã Token bot đã lấy ở Bước 1.
     - Bấm **Add secret**.
   - Mục 2:
     - Name: `TELEGRAM_CHAT_ID`
     - Secret: Dán chuỗi mã Chat ID đã lấy ở Bước 1.
     - Bấm **Add secret**.

*(Các mã này được mã hóa bảo mật tuyệt đối trên server của GitHub, không ai xem được kể cả khi kho ở chế độ Public).*

---

## BƯỚC 6. CHẠY THỬ NGHIỆM LẦN ĐẦU TIÊN

1. Bấm vào tab **Actions** trên repository GitHub của bạn.
2. Nếu GitHub hiện thông báo hỏi bật Actions, hãy bấm nút màu xanh **I understand my workflows, go ahead and enable them**.
3. Ở cột bên trái, bấm vào tên workflow: **Quet nen 4 gio va suc manh tien te**.
4. Ở góc bên phải, bấm vào nút **Run workflow** -> Bấm nút xanh **Run workflow**.
5. Chờ khoảng 1 phút cho tiến trình chạy xong (hiện dấu tích xanh):
   - Telegram của bạn sẽ lập tức nhận được tin nhắn tổng hợp sức mạnh tiền tệ kèm ảnh biểu đồ của các cặp thỏa mãn tiêu chí!
   - Mở đường dẫn GitHub Pages đã tạo ở Bước 4, bạn sẽ thấy trang web hiển thị dữ liệu phân tích trực tiếp theo thời gian thực!

---

## CÁC CON SỐ CÀI ĐẶT CÓ THỂ ĐIỀU CHỈNH TRONG `phan_tich.py`:

| Tham số | Mặc định | Ý nghĩa |
| :--- | :---: | :--- |
| `SO_NEN_XET_DINH_DAY` | 12 | Cụm mô hình nến H4 phải nằm ở Đỉnh/Đáy của bao nhiêu nến 4 giờ gần nhất |
| `SO_NEN_GAN_NHAT_XET` | 3 | Quét mô hình nến đảo chiều trong bao nhiêu nến 4 giờ vừa đóng |
| `CHENH_LECH_TOI_THIEU` | 0.15 | Chênh lệch sức mạnh dòng tiền tối thiểu giữa đồng Mua và đồng Bán (%) |
| `SO_NEN_TIM_MUC_TIEU` | 20 | Mục tiêu chốt lời (TP) tìm theo Đỉnh/Đáy của bao nhiêu nến 4 giờ gần nhất |
