# Cập nhật Muse Việt Nam không cần Google Cloud

## Cần biết trước

- Nguồn là RSS YouTube, **không phải API riêng của Muse**. Không cần Google Cloud hoặc YouTube API key.
- RSS chỉ có khoảng 15 video gần nhất/kênh. Lịch 6 giờ là mục tiêu, không đảm bảo không mất tập nếu đăng quá nhanh, lịch bị trì hoãn hoặc job lỗi. Không tự lấy đủ lịch sử cũ. Video có thể bị xóa/chặn vùng/chặn nhúng; khớp tên cũng có thể thất bại hoặc sai, đặc biệt là tên tiếng Việt và mùa phim. Cần kiểm tra thủ công.
- RSS không cung cấp thời lượng; lọc tiêu đề không thể loại chính xác mọi clip. oEmbed thành công **không chứng minh** video có thể nhúng hoặc phát tại Việt Nam. Nếu player báo lỗi, mở video trên YouTube để kiểm tra.
- Dữ liệu mẫu của app không tự cập nhật. Cần Supabase, schema, Edge Functions và cấu hình app dùng backend thật. App vẫn đang phát triển, chưa xác nhận toàn bộ luồng trên tài khoản của bạn.
- Supabase và GitHub Actions có gói miễn phí kèm điều kiện, hạn mức và có thể thay đổi; dự án không đảm bảo 0đ mãi hoặc 100% thời gian hoạt động.

## 1. Thử lấy dữ liệu, không cần Supabase

Trong PowerShell, vào **thư mục gốc dự án mới**, không phải app:

```powershell
cd "C:\protect code\Anistream\anistream-muse"
py -m pip install -r ingest\requirements.txt
py -m ingest.main youtube --dry-run
```

Đây là chạy thử đọc RSS và tìm thông tin AniList, **không ghi dữ liệu**. Kiểm tra đầu ra có `Muse Việt Nam`, các tập được nhận dạng và danh sách `chưa khớp`. Nếu AniList/network/oEmbed không truy cập được, xử lý lỗi trước khi tiếp tục. Tránh dùng `--deep`: cờ đó cần YouTube Data API key.

## 2. Kết nối backend thật

Thực hiện hướng dẫn `HUONG_DAN_CHAY.md` và `ingest/README.md` cho schema Supabase và deploy các Edge Functions `home`, `anime`, `search`, `schedule`. Không coi việc chạy Flutter ở chế độ mock là hoàn thành backend.

Tạo `.env` ở thư mục gốc bằng cách sao chép `.env.example`, sau đó điền `SUPABASE_URL` và `SUPABASE_SERVICE_KEY` (khóa service role hoặc secret key được backend hỗ trợ). **Không gửi khóa cho ai, không đưa vào Flutter, không commit `.env` hoặc đưa vào GitHub repository.** Chỉ dùng khóa server-side tin cậy; khóa có quyền rất cao. Chạy:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
py -m ingest.main catalog
py -m ingest.main youtube
```

Kiểm tra log số lượng video, những tên chưa khớp; đối chiếu `anime` và `streaming_links` trong Supabase. Chỉ các tên trùng đầy đủ hoặc alias biên tập mới được tự động chấp nhận; vẫn cần rà soát đúng bộ/mùa. Tên tiếng Việt chưa có alias thường không khớp. Các series chưa khớp có thể thêm alias vào `ingest/aliases.json`, dùng đúng AniList ID và chạy lại. Nếu ghi thất bại phải sửa lỗi trước khi thiết lập lịch.

## 3. Tự động chạy bằng GitHub Actions (không bắt buộc)

1. Tạo repository GitHub và tải mã dự án lên, bao gồm **`.github/workflows/ingest.yml`**. Không tải `.env` hoặc khóa lên repository. Đảm bảo workflow ở nhánh mặc định.
2. Trong repository vào Settings → Secrets and variables → Actions → New repository secret. Thêm `SUPABASE_URL` và `SUPABASE_SERVICE_KEY` với giá trị tương ứng. Không đưa service key vào app hoặc chia sẻ công khai.
3. Trong tab Actions cho phép workflow nếu được yêu cầu. Chọn workflow `ingest` → Run workflow → chọn `youtube`. Mở log kiểm tra có video khớp và ghi thành công.
4. Sau đó workflow dự kiến chạy RSS vào phút 0 mỗi 6 giờ (UTC), lịch AniList 30 phút/lần và catalog mỗi ngày. GitHub có thể trì hoãn/bỏ chạy lịch, đặc biệt trong repo không hoạt động; hãy kiểm tra tab Actions và hạn mức GitHub. Khi job lỗi, cần chạy lại sớm vì RSS có cửa sổ ngắn.

Để giảm nhu cầu GitHub Actions, có thể tắt/bỏ hai lịch `schedule` và `catalog` trong workflow; RSS giữ `0 */6 * * *`. Nhớ catalog/lịch AniList sau đó phải cập nhật bằng cách khác.

## 4. Chạy app dùng backend thật

Sau khi Edge Functions đã deploy, vào thư mục `app` và thay các giá trị placeholder dưới đây bằng **URL dự án thật và anon/publishable key** (không phải service key):

```powershell
cd app
flutter run -d chrome --dart-define=USE_MOCK=false --dart-define=API_BASE=https://<project-ref>.supabase.co/functions/v1 --dart-define=ANON_KEY=<anon-key>
```

Trong PowerShell, để tránh ký tự `<` `>` bị hiểu nhầm, thay toàn bộ placeholder trước khi chạy. Kiểm tra video trong app và trên YouTube; không hứa video nào cũng có thể nhúng. Nếu không thấy tập, xem log `chưa khớp`, bảng `streaming_links`, các Edge Functions và việc app đã tắt mock. File app chi tiết tập được cập nhật để đưa những tập có link vào danh sách ngay cả khi lịch AniList chưa có dòng tương ứng.

## Bổ sung tập cũ

Không có cách tự động lấy đầy đủ lịch sử bằng RSS này. Có thể ghi nhận thủ công các link video/playlist chính thức để biên tập và đối chiếu với từng bộ. Hiện dự án **chưa có màn hình nhập playlist và tự tách từng tập**; đừng kỳ vọng dán link playlist là tự nhập toàn bộ. Không trích xuất stream, không bỏ quảng cáo và không vượt giới hạn địa lý.

## 5. Ghép tên Việt khi bị báo chưa khớp

Một số tên Việt không có trong AniList. File `ingest/aliases.json` có hai tên Muse được biên tập sẵn. Khi log ghi `chưa khớp`, mở video trên YouTube, so sánh tên gốc/nội dung/mùa với trang AniList và lấy ID từ URL `https://anilist.co/anime/<ID>/...`. Chỉ thêm khi chắc chắn đúng bộ và đúng mùa.

Mở `ingest/aliases.json`, thêm vào bên trong đối tượng `aliases` một dòng JSON ví dụ:

```json
"Tên đúng như log": 12345
```

`12345` chỉ là ví dụ, phải thay bằng ID đã kiểm tra; nhớ dấu phẩy giữa các dòng. Chạy lại `py -m ingest.main youtube --dry-run`, xem kết quả trước khi chạy ghi thật. Cần cập nhật alias trong repository để GitHub Actions dùng được. RSS chỉ giữ cửa sổ ngắn: tập cũ đã rời RSS sẽ không được lấy lại tự động chỉ nhờ thêm alias.
