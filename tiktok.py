import os
import csv
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta

import requests

API_KEY = os.environ.get("SCRAPECREATORS_API_KEY")
HANDLE = os.environ.get("HANDLE", "mobilelegendsvn_funtap").strip().lstrip("@")
MONTHS = int(os.environ.get("MONTHS", "12"))       # lấy bao nhiêu tháng gần nhất
MAX_PAGES = int(os.environ.get("MAX_PAGES", "10"))  # tối đa bao nhiêu lần gọi API (mỗi lần tốn credit)

VN = timezone(timedelta(hours=7))  # tính tháng theo giờ Việt Nam
URL = "https://api.scrapecreators.com/v3/tiktok/profile/videos"

if not API_KEY:
    sys.exit("Thiếu SCRAPECREATORS_API_KEY. Hãy thêm key vào GitHub Secrets.")

# Mốc đầu tháng cách đây MONTHS tháng
now = datetime.now(VN)
y, m = now.year, now.month - (MONTHS - 1)
while m <= 0:
    m += 12
    y -= 1
start = datetime(y, m, 1, tzinfo=VN)
print(f"Kênh: @{HANDLE} | lấy video từ {start:%d/%m/%Y} đến nay")

videos = {}
cursor = None
for page in range(1, MAX_PAGES + 1):
    params = {"handle": HANDLE}
    if cursor:
        params["max_cursor"] = cursor
    r = requests.get(URL, headers={"x-api-key": API_KEY}, params=params, timeout=60)
    if r.status_code != 200:
        print(f"Lỗi {r.status_code}: {r.text[:500]}")
        break
    data = r.json()
    items = data.get("aweme_list") or []
    print(f"Trang {page}: nhận {len(items)} video")
    if not items:
        if page == 1:
            print("Không có video. Kết quả trả về:", str(data)[:500])
        break

    oldest = None
    for v in items:
        ts = v.get("create_time")
        if not ts:
            continue
        dt = datetime.fromtimestamp(int(ts), VN)
        oldest = dt if oldest is None or dt < oldest else oldest
        s = v.get("statistics", {})
        videos[v.get("aweme_id")] = {
            "id": v.get("aweme_id"),
            "ngày đăng": dt.strftime("%Y-%m-%d %H:%M"),
            "tháng": dt.strftime("%Y-%m"),
            "view": s.get("play_count") or 0,
            "like": s.get("digg_count") or 0,
            "comment": s.get("comment_count") or 0,
            "share": s.get("share_count") or 0,
            "mô tả": (v.get("desc") or "").replace("\n", " "),
            "_dt": dt,
        }

    # Dừng nếu đã đi qua mốc thời gian cần lấy
    if oldest and oldest < start:
        break
    cursor = data.get("max_cursor")
    if not cursor or data.get("has_more") in (0, False):
        break
    time.sleep(1)

rows = sorted((v for v in videos.values() if v["_dt"] >= start), key=lambda x: x["_dt"], reverse=True)

# Tổng hợp theo tháng
monthly = defaultdict(lambda: {"số video": 0, "tổng view": 0, "tổng like": 0, "tổng comment": 0, "tổng share": 0})
for v in rows:
    t = monthly[v["tháng"]]
    t["số video"] += 1
    t["tổng view"] += v["view"]
    t["tổng like"] += v["like"]
    t["tổng comment"] += v["comment"]
    t["tổng share"] += v["share"]

print("\n=== VIEW THEO THÁNG ===")
print(f"{'Tháng':<10}{'Số video':>10}{'Tổng view':>16}{'View TB/video':>16}")
monthly_rows = []
for month in sorted(monthly):
    t = monthly[month]
    avg = round(t["tổng view"] / t["số video"]) if t["số video"] else 0
    print(f"{month:<10}{t['số video']:>10}{t['tổng view']:>16,}{avg:>16,}")
    monthly_rows.append({"tháng": month, **t, "view TB/video": avg})

if monthly_rows:
    with open("view_theo_thang.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=monthly_rows[0].keys())
        w.writeheader()
        w.writerows(monthly_rows)
    with open("chi_tiet_video.csv", "w", newline="", encoding="utf-8-sig") as f:
        fields = [k for k in rows[0].keys() if k != "_dt"]
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print("\nĐã lưu: view_theo_thang.csv và chi_tiet_video.csv")
else:
    print("Không có video nào trong khoảng thời gian này.")
