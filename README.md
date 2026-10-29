# V Roleplay Community Bot

Bot Discord Python theo OOP dành cho server GTA5 Roleplay. Bot tự tạo kênh chào mừng/tạm biệt, danh mục hỗ trợ và panel ticket có nút. Transcript được lưu thành file HTML trên VPS.

## Tính năng

- Tự tạo `#welcome`, `#byebye`, danh mục `🎫 HỖ TRỢ TICKET`, `#hỗ-trợ-ticket`, `#log-ticket` và danh mục ticket đã đóng.
- Welcome có link Luật thành phố, Whitelist, Ticket và ảnh banner từ `.env`.
- Bốn form ticket: Hỗ trợ, Tố cáo, Donate, Báo lỗi.
- Panel là persistent view: khởi động lại bot vẫn bấm được; bot không gửi panel trùng nếu tin cũ còn tồn tại.
- Đăng ký Verified Citizen qua DM với 5 câu hỏi; đơn được lưu SQLite và gửi vào `#log-citizen` để nhân viên duyệt/từ chối.
- Duyệt đơn sẽ cấp role Citizen theo `CITIZEN_ROLE_ID`; từ chối yêu cầu nhập lý do và gửi DM cho người đăng ký.
- Khi bot khởi động, bot cấp role `New Citizen` cho thành viên hiện có; thành viên mới cũng nhận role này tự động (`NEW_CITIZEN_ROLE_ID`).
- `+cl`: chủ ticket hoặc nhân viên hỗ trợ đóng ticket. Bot xuất transcript HTML, ghi vào `#log-ticket`, rồi xóa phòng ticket ngay.
- `+delete`: chỉ admin/role hỗ trợ được xóa kênh ticket ngay.
- Transcript HTML hiển thị biệt danh trong server, avatar, nội dung và ảnh/file đính kèm đã lưu trong cùng thư mục.
- Transcript được lưu trong `data/transcripts/` trên VPS và mở công khai qua `PUBLIC_BASE_URL` trên cổng 5000; log Discord, file HTML, ảnh và file đính kèm tự xóa sau 15 ngày (có thể đổi bằng `TRANSCRIPT_RETENTION_DAYS` trong `.env`).
- Khi cập nhật bot, các phòng ticket cũ trong danh mục `TICKET ĐÃ ĐÓNG` sẽ được lưu transcript/log rồi xóa; danh mục này cũng được xóa khi trống.

## 1. Tạo bot Discord

1. Vào [Discord Developer Portal](https://discord.com/developers/applications), tạo Application và Bot.
2. Trong trang **Bot**, bật hai privileged intents:
   - `SERVER MEMBERS INTENT`
   - `MESSAGE CONTENT INTENT`
3. Ở OAuth2 URL Generator chọn scope `bot`, rồi cấp các quyền:
   - View Channels, Send Messages, Embed Links, Attach Files, Read Message History
   - Manage Channels, Manage Messages
4. Mời bot vào server. Role của bot cần nằm đủ cao để bot xem/cấu hình kênh.

## 2. Cấu hình

Yêu cầu Python 3.11 trở lên. Sao chép `.env.example` thành `.env`, sau đó điền:

```env
DISCORD_TOKEN=token_cua_bot
SUPPORT_ROLE_ID=id_role_ho_tro
CITIZEN_ROLE_ID=id_role_citizen
NEW_CITIZEN_ROLE_ID=id_role_new_citizen
RULES_URL=link_kenh_luat
WHITELIST_URL=link_kenh_whitelist
WELCOME_IMAGE_URL=https://domain/banner-welcome.png
TICKET_IMAGE_URL=https://domain/banner-ticket.png
PUBLIC_BASE_URL=http://IP_VPS_CUA_BAN:5000
WEB_HOST=0.0.0.0
WEB_PORT=5000
```

Để lấy ID role: bật Developer Mode trong Discord, bấm phải role **Hỗ trợ**, **Citizen** hoặc **New Citizen** rồi chọn **Copy Role ID**. Role bot cần nằm cao hơn cả hai role Citizen để cấp role. Bật `SERVER MEMBERS INTENT` để bot nhận thành viên mới và đồng bộ role thành viên hiện có. Không đưa file `.env` lên GitHub.

## 3. Chạy trực tiếp

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

Linux/VPS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Chạy bằng Docker

```bash
docker compose up -d --build
docker compose logs -f
```

Dữ liệu SQLite, transcript HTML và ảnh được giữ trong thư mục `data/` trên VPS. Mở cổng TCP 5000 trên firewall/security group để vào link dạng `http://IP_VPS:5000/logs/<mã-ticket>/`. Hãy sao lưu thư mục `data/` nếu chuyển VPS.

## Quyền lệnh

- `+cl`: chủ ticket, admin hoặc role có ID bằng `SUPPORT_ROLE_ID`.
- `+delete`: chỉ admin hoặc role hỗ trợ.

Việc dọn ticket chạy mỗi giờ, vì vậy một ticket có thể được xóa muộn hơn thời hạn tối đa khoảng một giờ.

