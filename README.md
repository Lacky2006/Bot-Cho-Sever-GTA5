# V Roleplay Community Bot

Bot Discord Python theo OOP dành cho server GTA5 Roleplay. Bot tự tạo kênh chào mừng/tạm biệt, danh mục hỗ trợ, panel ticket có nút và trang transcript HTML xem trực tuyến.

## Tính năng

- Tự tạo `#welcome`, `#byebye`, danh mục `🎫 HỖ TRỢ TICKET`, `#hỗ-trợ-ticket`, `#log-ticket` và danh mục ticket đã đóng.
- Welcome có link Luật thành phố, Whitelist, Ticket và ảnh banner từ `.env`.
- Bốn form ticket: Hỗ trợ, Tố cáo, Donate, Báo lỗi.
- Panel là persistent view: khởi động lại bot vẫn bấm được; bot không gửi panel trùng nếu tin cũ còn tồn tại.
- Đăng ký Verified Citizen qua DM với 5 câu hỏi; đơn được lưu SQLite và gửi vào `#log-citizen` để nhân viên duyệt/từ chối.
- Duyệt đơn sẽ cấp role Citizen theo `CITIZEN_ROLE_ID`; từ chối yêu cầu nhập lý do và gửi DM cho người đăng ký.
- Khi bot khởi động, bot cấp role `New Citizen` cho thành viên hiện có; thành viên mới cũng nhận role này tự động (`NEW_CITIZEN_ROLE_ID`).
- `+cl`: chủ ticket hoặc nhân viên hỗ trợ được đóng ticket. Kênh chuyển sang danh mục đã đóng và bị khóa với người mở.
- `+delete`: chỉ admin/role hỗ trợ được xóa kênh ticket ngay.
- Transcript HTML hiển thị biệt danh trong server, avatar, nội dung và ảnh/file đính kèm đã lưu cục bộ.
- Link transcript có mã ngẫu nhiên khó đoán, xem bằng ngrok hoặc IP/domain VPS.
- Ticket đã đóng và transcript tự xóa sau 15 ngày (có thể đổi trong `.env`).

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
PUBLIC_BASE_URL=https://dia-chi-cong-khai
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

## 4. Link xem transcript

Web log chạy ở cổng `8080`. Có hai cách:

- VPS: mở firewall cổng 8080 và đặt `PUBLIC_BASE_URL=http://IP_VPS:8080` (nên dùng domain + HTTPS qua Nginx/Caddy khi chạy thật).
- Máy cá nhân + ngrok: chạy `ngrok http 8080`, rồi đặt URL HTTPS ngrok vào `PUBLIC_BASE_URL` và khởi động lại bot.

Không điền URL API của Grok AI; thứ cần dùng ở đây là URL tunnel của **ngrok** hoặc IP/domain VPS.

## Chạy bằng Docker

```bash
docker compose up -d --build
docker compose logs -f
```

Dữ liệu SQLite, transcript và ảnh được giữ trong thư mục `data/`. Hãy sao lưu thư mục này nếu chuyển VPS.

## Quyền lệnh

- `+cl`: chủ ticket, admin hoặc role có ID bằng `SUPPORT_ROLE_ID`.
- `+delete`: chỉ admin hoặc role hỗ trợ.

Việc dọn ticket chạy mỗi giờ, vì vậy một ticket có thể được xóa muộn hơn thời hạn tối đa khoảng một giờ.

