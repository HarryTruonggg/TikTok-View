import os
import csv
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta

import requests

API_KEY = os.environ.get("SCRAPECREATORS_API_KEY")
MONTHS = int(os.environ.get("MONTHS", "6"))         # lấy bao nhiêu tháng gần nhất
MAX_PAGES = int(os.environ.get("MAX_PAGES", "5"))   # tối đa số lần gọi API cho MỖI kênh

VN = timezone(timedelta(hours=7))  # tính tháng theo giờ Việt Nam
URL = "https://api.scrapecreators.com/v3/tiktok/profile/videos"

if not API_KEY:
    sys.exit("Thiếu SCRAPECREATORS_API_KEY. Hãy thêm key vào GitHub Secrets.")

# Đọc danh sách kênh từ file channels.txt (mỗi dòng 1 kênh)
handles = []
with open("channels.txt", encoding="utf-8") as f:
    for line in f:
        h = line.strip()
        if not h or h.startswith("#"):
            continue
        h = h.split("tiktok.com/")[-1]          # cho phép dán cả link
        h = h.split("?")[0].strip("/").lstrip("@")
        if h and h not in handles:
            handles.append(h)

# Mốc đầu tháng cách đây MONTHS tháng
now = datetime.now(VN)
y, m = now.year, now.month - (MONTHS - 1)
while m <= 0:
    m += 12
    y -= 1
start = datetime(y, m, 1, tzinfo=VN)
print(f"Số kênh: {len(handles)} | lấy video từ {start:%d/%m/%Y} đến nay | tối đa {MAX_PAGES} lần gọi/kênh")
print(f"Tối đa {len(handles) * MAX_PAGES} lần gọi API (mỗi lần tốn credit)\n")


def fetch_channel(handle):
    """Trả về (danh sách video trong khoảng thời gian, số lần gọi API, lỗi nếu có)."""
    videos = {}
    cursor = None
    calls = 0
    for page in range(1, MAX_PAGES + 1):
        params = {"handle": handle}
        if cursor:
            params["max_cursor"] = cursor
        try:
            r = requests.get(URL, headers={"x-api-key": API_KEY}, params=params, timeout=60)
        except requests.RequestException as e:
            return list(videos.values()), calls, f"lỗi mạng: {e}"
        calls += 1
        if r.status_code != 200:
            return list(videos.values()), calls, f"lỗi {r.status_code}: {r.text[:200]}"
        data = r.json()
        items = data.get("aweme_list") or []
        if not items:
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
                "kênh": handle,
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
        if oldest and oldest < start:
            break
        cursor = data.get("max_cursor")
        if not cursor or data.get("has_more") in (0, False):
            break
        time.sleep(0.5)
    return [v for v in videos.values() if v["_dt"] >= start], calls, None


all_videos = []
summary = []   # tóm tắt chạy từng kênh
total_calls = 0
for i, h in enumerate(handles, 1):
    vids, calls, err = fetch_channel(h)
    total_calls += calls
    all_videos.extend(vids)
    status = "OK" if not err and vids else (err or "không có video")
    print(f"[{i}/{len(handles)}] @{h}: {len(vids)} video, {calls} lần gọi - {status}")
    summary.append({"kênh": h, "số video": len(vids), "số lần gọi API": calls, "trạng thái": status})
    time.sleep(0.5)

print(f"\nTổng số lần gọi API đã dùng: {total_calls}")

# Tổng hợp theo kênh + tháng
agg = defaultdict(lambda: {"số video": 0, "tổng view": 0, "tổng like": 0, "tổng comment": 0, "tổng share": 0})
for v in all_videos:
    t = agg[(v["kênh"], v["tháng"])]
    t["số video"] += 1
    t["tổng view"] += v["view"]
    t["tổng like"] += v["like"]
    t["tổng comment"] += v["comment"]
    t["tổng share"] += v["share"]

monthly_rows = []
for (h, month) in sorted(agg):
    t = agg[(h, month)]
    avg = round(t["tổng view"] / t["số video"]) if t["số video"] else 0
    monthly_rows.append({"kênh": h, "tháng": month, **t, "view TB/video": avg})

# Bảng chéo: mỗi kênh 1 dòng, mỗi tháng 1 cột (tổng view)
months = sorted({m for (_, m) in agg})
pivot_rows = []
for h in handles:
    row = {"kênh": h}
    total = 0
    for mth in months:
        val = agg[(h, mth)]["tổng view"] if (h, mth) in agg else 0
        row[mth] = val
        total += val
    row["TỔNG"] = total
    pivot_rows.append(row)
pivot_rows.sort(key=lambda r: r["TỔNG"], reverse=True)


def write_csv(path, rows, fields=None):
    if not rows:
        return
    fields = fields or list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


write_csv("bang_cheo_view.csv", pivot_rows)
write_csv("view_theo_kenh_thang.csv", monthly_rows)
write_csv("chi_tiet_video.csv", sorted(all_videos, key=lambda x: (x["kênh"], x["_dt"]), reverse=False))
write_csv("trang_thai_kenh.csv", summary)

print("\n=== TỔNG VIEW THEO THÁNG (TẤT CẢ KÊNH) ===")
for mth in months:
    tv = sum(r[mth] for r in pivot_rows)
    print(f"{mth}: {tv:,}")
print("\nĐã lưu: bang_cheo_view.csv, view_theo_kenh_thang.csv, chi_tiet_video.csv, trang_thai_kenh.csv")
