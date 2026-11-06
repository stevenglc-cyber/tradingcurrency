"""
Quét 28 cặp tiền tệ theo phương pháp của Tú Trading Systems:
1. Tính sức mạnh 8 đồng tiền theo % từ giá mở cửa ngày (giống MarketMilk).
2. Chọn 5 cặp mạnh – yếu nhất.
3. Chỉ tìm mô hình nến đảo chiều theo đúng hướng sức mạnh tiền tệ trên khung 4 giờ.
4. Lời/lỗ tối thiểu 1:1,5 hoặc có điểm hồi về (giá chờ).

Kết quả ghi ra data.json cho trang web đọc.
Khi có nến 4 giờ mới đóng, gửi báo cáo về Telegram.
"""
import io
import json
import os
import subprocess
import sys
import time
import uuid
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

# Đảm bảo mã hóa UTF-8 khi in log ra màn hình console (đặc biệt trên Windows)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# ---------------- Cài đặt (sửa ở đây nếu muốn) ----------------
SO_NEN_XET_DINH_DAY = 12    # Mô hình phải nằm ở đỉnh/đáy của bao nhiêu nến 4 giờ gần nhất
SO_NEN_GAN_NHAT_XET = 3     # Xét mô hình trong bao nhiêu nến 4 giờ vừa đóng
SO_NEN_TIM_MUC_TIEU = 20    # Mục tiêu = đỉnh/đáy của bao nhiêu nến 4 giờ gần nhất
SO_GIO_DAU_NGAY = 2         # Trong bao nhiêu giờ đầu ngày giao dịch thì dùng sức mạnh của cả ngày hôm trước
SO_NEN_TREN_BIEU_DO = 45    # Số nến 4 giờ vẽ trên ảnh biểu đồ gửi Telegram
SO_NEN_TRADINGVIEW = 100    # Số nến 4 giờ gửi ra web để vẽ TradingView Lightweight Charts và Sonic R
# ---------------------------------------------------------------

TIEN = ["EUR", "GBP", "AUD", "NZD", "USD", "CAD", "CHF", "JPY"]
CAP = [(i, j) for i in range(8) for j in range(i + 1, 8)]   # 28 cặp, tên chuẩn như EURUSD, GBPJPY...

try:
    NEW_YORK = ZoneInfo("America/New_York") if ZoneInfo else None
except Exception:
    NEW_YORK = None

GIO_VN = timezone(timedelta(hours=7))
THU_MUC = os.path.dirname(os.path.abspath(__file__))
FILE_DATA = os.path.join(THU_MUC, "data.json")
FILE_LICH_SU = os.path.join(THU_MUC, "lich_su_nen.json")

# Lấy từ GitHub Secrets hoặc biến môi trường
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip() or os.environ.get("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
# Đặt "co" khi chạy thử bằng tay trên GitHub Actions để luôn nhận tin
LUON_GUI = os.environ.get("LUON_GUI_TELEGRAM", "") == "co"


def lech_gio_san(ts):
    """Số giây giờ sàn lệch so với giờ quốc tế. Sàn MT5 phổ biến (như Global Prime)
    lấy 0 giờ sàn = 17 giờ New York, tức giờ sàn = giờ New York + 7."""
    if NEW_YORK is not None:
        try:
            dt = datetime.fromtimestamp(ts, timezone.utc).astimezone(NEW_YORK)
            return int(dt.utcoffset().total_seconds()) + 7 * 3600
        except Exception:
            pass
    # Dự phòng chuẩn xác khi môi trường thiếu tzdata
    dt_utc = datetime.fromtimestamp(ts, timezone.utc)
    y = dt_utc.year
    first_sun_mar = (6 - datetime(y, 3, 1).weekday()) % 7 + 1
    second_sun_mar = first_sun_mar + 7
    start_dst = datetime(y, 3, second_sun_mar, 7, tzinfo=timezone.utc)

    first_sun_nov = (6 - datetime(y, 11, 1).weekday()) % 7 + 1
    end_dst = datetime(y, 11, first_sun_nov, 6, tzinfo=timezone.utc)

    offset_seconds = -4 * 3600 if start_dst <= dt_utc < end_dst else -5 * 3600
    return offset_seconds + 7 * 3600


def lay_nen_gio(ten_cap):
    """Lấy nến 1 giờ trực tiếp từ Yahoo Finance."""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ten_cap}=X"
           "?interval=1h&range=365d")
    for lan in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                kq = json.load(r)["chart"]["result"][0]
            t = kq["timestamp"]
            q = kq["indicators"]["quote"][0]
            nen = []
            for k in range(len(t)):
                if None in (q["open"][k], q["high"][k], q["low"][k], q["close"][k]):
                    continue
                nen.append((t[k], q["open"][k], q["high"][k], q["low"][k], q["close"][k]))
            return nen
        except Exception as loi:
            print(f"Lỗi lấy {ten_cap} lần {lan + 1}: {loi}")
            time.sleep(2)
    return []


def gop_nen_4_gio(nen_gio, bay_gio):
    """Gộp nến 1 giờ thành nến 4 giờ theo giờ sàn MT5 (0-4h, 4-8h, 8-12h, 12-16h, 16-20h, 20-24h).
    Trả về (danh sách nến đã đóng, danh sách nến đang chạy)."""
    nhom = {}
    thu_tu = []
    for (t, o, h, l, c) in nen_gio:
        khoa = (t + lech_gio_san(t)) // 14400
        if khoa not in nhom:
            gio_mo = khoa * 14400 - lech_gio_san(t)
            nhom[khoa] = {"t": t, "o": o, "h": h, "l": l, "c": c, "khoa": khoa, "dong": gio_mo + 14400}
            thu_tu.append(khoa)
        else:
            b = nhom[khoa]
            b["h"] = max(b["h"], h)
            b["l"] = min(b["l"], l)
            b["c"] = c
    nen = [nhom[k] for k in thu_tu]
    khoa_hien_tai = (bay_gio + lech_gio_san(bay_gio)) // 14400
    da_dong = [b for b in nen if b["khoa"] < khoa_hien_tai]
    dang_chay = [b for b in nen if b["khoa"] >= khoa_hien_tai]
    return da_dong, dang_chay


def tinh_atr(nen):
    atr = [0.0] * len(nen)
    a = 0.0
    for i in range(1, len(nen)):
        tr = max(nen[i]["h"] - nen[i]["l"],
                 abs(nen[i]["h"] - nen[i - 1]["c"]),
                 abs(nen[i]["l"] - nen[i - 1]["c"]))
        a = (a * (i - 1) + tr) / i if i <= 14 else (a * 13 + tr) / 14
        atr[i] = a
    return atr



def tinh_ema_list(bars, period, col):
    """Tính EMA chuẩn mực. bars là list [t, o, h, l, c]. col: 1=o, 2=h, 3=l, 4=c."""
    if len(bars) < period:
        return [None] * len(bars)
    k = 2.0 / (period + 1.0)
    sma = sum(b[col] for b in bars[:period]) / period
    res = [None] * (period - 1) + [sma]
    prev = sma
    for b in bars[period:]:
        prev = (b[col] * k) + (prev * (1.0 - k))
        res.append(prev)
    return res


def dong_goi_nen_kem_ema(bars, so_le=5, so_nen_lay=150):
    """Tính toàn bộ bộ chỉ báo Sonic R chuẩn Vũ Tiến (EMA 34 High, Close, Low, EMA 89, EMA 200, EMA 610)
    và đóng gói các nến gần nhất."""
    if not bars:
        return []
    e34h = tinh_ema_list(bars, 34, 2)
    e34c = tinh_ema_list(bars, 34, 4)
    e34l = tinh_ema_list(bars, 34, 3)
    e89 = tinh_ema_list(bars, 89, 4)
    e200 = tinh_ema_list(bars, 200, 4)
    e610 = tinh_ema_list(bars, 610, 4)

    bat_dau = max(0, len(bars) - so_nen_lay)
    kq = []
    for idx in range(bat_dau, len(bars)):
        b = bars[idx]
        kq.append([
            b[0],
            round(b[1], so_le),
            round(b[2], so_le),
            round(b[3], so_le),
            round(b[4], so_le),
            round(e34h[idx], so_le) if e34h[idx] is not None else None,
            round(e34c[idx], so_le) if e34c[idx] is not None else None,
            round(e34l[idx], so_le) if e34l[idx] is not None else None,
            round(e89[idx], so_le) if e89[idx] is not None else None,
            round(e200[idx], so_le) if e200[idx] is not None else None,
            round(e610[idx], so_le) if e610[idx] is not None else None,
        ])
    return kq


def lay_nen_15m_va_1d(ten_cap, so_le=5):
    """Lấy dữ liệu nến M15 và 1D (Daily) từ Yahoo Finance cho Sonic R."""
    sym = ten_cap.replace('/', '')
    kq = {"15": [], "D": []}
    
    # 1. Khung M15 (60 ngày ~ 5700 nến để tính EMA 610)
    try:
        url15 = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}=X?interval=15m&range=60d"
        req = urllib.request.Request(url15, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            res15 = json.load(r)["chart"]["result"][0]
        t15 = res15["timestamp"]
        q15 = res15["indicators"]["quote"][0]
        bars15 = [[t15[i], q15["open"][i], q15["high"][i], q15["low"][i], q15["close"][i]]
                  for i in range(len(t15)) if q15["close"][i] is not None]
        kq["15"] = dong_goi_nen_kem_ema(bars15, so_le, 150)
    except Exception as e:
        print(f"Lỗi lấy 15m {sym}: {e}")

    # 2. Khung 1D (5 năm ~ 1300 nến để tính EMA 610)
    try:
        urld = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}=X?interval=1d&range=5y"
        req = urllib.request.Request(urld, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            resd = json.load(r)["chart"]["result"][0]
        td = resd["timestamp"]
        qd = resd["indicators"]["quote"][0]
        barsd = [[td[i], qd["open"][i], qd["high"][i], qd["low"][i], qd["close"][i]]
                 for i in range(len(td)) if qd["close"][i] is not None]
        kq["D"] = dong_goi_nen_kem_ema(barsd, so_le, 150)
    except Exception as e:
        print(f"Lỗi lấy 1d {sym}: {e}")

    return kq

def than(b): return abs(b["c"] - b["o"])
def bien(b): return b["h"] - b["l"]
def rau_tren(b): return b["h"] - max(b["o"], b["c"])
def rau_duoi(b): return min(b["o"], b["c"]) - b["l"]
def tang(b): return b["c"] > b["o"]
def giam(b): return b["c"] < b["o"]


def mo_hinh_tang(n, i, a):
    """Trả về danh sách (tên mô hình, số nến tạo mô hình)."""
    k, p = n[i], n[i - 1]
    ds = []
    # Nhấn chìm tăng: nến trước giảm, nến sau tăng đóng cửa vượt giá mở nến trước, thân lớn hơn
    if giam(p) and tang(k) and k["c"] >= p["o"] and than(k) > than(p):
        ds.append(("nhấn chìm tăng", 2))
    # Búa: râu dưới dài gấp đôi thân, râu trên ngắn, nến không quá nhỏ
    if rau_duoi(k) >= 2 * than(k) and rau_tren(k) <= 0.35 * bien(k) and bien(k) >= 0.6 * a:
        ds.append(("búa", 1))
    # Sao mai: nến giảm lớn, 1 hoặc 2 nến lưỡng lự, rồi nến tăng đóng trên giữa thân nến giảm lớn
    for so_giua in (1, 2):
        if i - 1 - so_giua < 0:
            continue
        lon = n[i - 1 - so_giua]
        giua = n[i - so_giua:i]
        if (giam(lon) and than(lon) > 0.5 * a and all(than(g) <= 0.6 * than(lon) for g in giua)
                and tang(k) and than(k) > 0.3 * a and k["c"] > (lon["o"] + lon["c"]) / 2):
            ds.append(("sao mai", so_giua + 2))
            break
    # Đáy nhíp: hai đáy bằng nhau, nến sau tăng
    if giam(p) and tang(k) and abs(k["l"] - p["l"]) < 0.1 * a and than(k) > 0.3 * a:
        ds.append(("đáy nhíp", 2))
    # Xuyên đâm: nến giảm lớn, nến tăng đóng trên giữa thân nhưng chưa vượt giá mở nến giảm
    if (giam(p) and than(p) > 0.5 * a and tang(k)
            and (p["o"] + p["c"]) / 2 < k["c"] < p["o"]):
        ds.append(("xuyên đâm", 2))
    # Quét đáy: râu chọc thủng đáy thấp nhất 12 nến trước rồi đóng cửa quay lên trên đáy đó
    day_cu = min(b["l"] for b in n[i - 12:i])
    if k["l"] < day_cu < k["c"] and k["c"] - k["l"] >= 0.5 * bien(k) and bien(k) >= 0.6 * a:
        ds.append(("quét đáy", 1))
    # Phá giả nến mẹ: 1-2 nến nằm gọn trong nến mẹ, nến sau chọc thủng đáy nến mẹ rồi đóng cửa quay vào trong
    for so_con in (1, 2):
        me = n[i - so_con - 1]
        con = n[i - so_con:i]
        if (bien(me) >= 0.8 * a and all(b["h"] <= me["h"] and b["l"] >= me["l"] for b in con)
                and k["l"] < me["l"] < k["c"] < me["h"]):
            ds.append(("phá giả nến mẹ", so_con + 2))
            break
    # Ba nến trong tăng: nến giảm lớn, nến nhỏ nằm trong thân nó, nến tăng đóng vượt giá mở nến giảm lớn
    pp = n[i - 2]
    if (giam(pp) and than(pp) > 0.5 * a and max(p["o"], p["c"]) <= pp["o"] and min(p["o"], p["c"]) >= pp["c"]
            and tang(k) and k["c"] > pp["o"]):
        ds.append(("ba nến trong tăng", 3))
    # Ba lính trắng: ba nến tăng thân dài liên tiếp, mỗi nến mở trong thân nến trước, đóng cao hơn, gần đỉnh nến
    ba = n[i - 2:i + 1]
    if (all(tang(b) and than(b) > 0.5 * a and rau_tren(b) <= 0.3 * bien(b) for b in ba)
            and all(ba[x - 1]["o"] <= ba[x]["o"] <= ba[x - 1]["c"] and ba[x]["c"] > ba[x - 1]["c"] for x in (1, 2))):
        ds.append(("ba lính trắng", 3))
    return ds


def mo_hinh_giam(n, i, a):
    """Trả về danh sách (tên mô hình, số nến tạo mô hình)."""
    k, p = n[i], n[i - 1]
    ds = []
    if tang(p) and giam(k) and k["c"] <= p["o"] and than(k) > than(p):
        ds.append(("nhấn chìm giảm", 2))
    if rau_tren(k) >= 2 * than(k) and rau_duoi(k) <= 0.35 * bien(k) and bien(k) >= 0.6 * a:
        ds.append(("sao băng", 1))
    for so_giua in (1, 2):
        if i - 1 - so_giua < 0:
            continue
        lon = n[i - 1 - so_giua]
        giua = n[i - so_giua:i]
        if (tang(lon) and than(lon) > 0.5 * a and all(than(g) <= 0.6 * than(lon) for g in giua)
                and giam(k) and than(k) > 0.3 * a and k["c"] < (lon["o"] + lon["c"]) / 2):
            ds.append(("sao hôm", so_giua + 2))
            break
    if tang(p) and giam(k) and abs(k["h"] - p["h"]) < 0.1 * a and than(k) > 0.3 * a:
        ds.append(("đỉnh nhíp", 2))
    if (tang(p) and than(p) > 0.5 * a and giam(k)
            and p["o"] < k["c"] < (p["o"] + p["c"]) / 2):
        ds.append(("mây đen", 2))
    # Quét đỉnh: râu chọc thủng đỉnh cao nhất 12 nến trước rồi đóng cửa quay xuống dưới đỉnh đó
    dinh_cu = max(b["h"] for b in n[i - 12:i])
    if k["c"] < dinh_cu < k["h"] and k["h"] - k["c"] >= 0.5 * bien(k) and bien(k) >= 0.6 * a:
        ds.append(("quét đỉnh", 1))
    # Phá giả nến mẹ: nến sau chọc thủng đỉnh nến mẹ rồi đóng cửa quay vào trong
    for so_con in (1, 2):
        me = n[i - so_con - 1]
        con = n[i - so_con:i]
        if (bien(me) >= 0.8 * a and all(b["h"] <= me["h"] and b["l"] >= me["l"] for b in con)
                and me["l"] < k["c"] < me["h"] < k["h"]):
            ds.append(("phá giả nến mẹ", so_con + 2))
            break
    # Ba nến trong giảm
    pp = n[i - 2]
    if (tang(pp) and than(pp) > 0.5 * a and max(p["o"], p["c"]) <= pp["c"] and min(p["o"], p["c"]) >= pp["o"]
            and giam(k) and k["c"] < pp["o"]):
        ds.append(("ba nến trong giảm", 3))
    # Ba quạ đen: ba nến giảm thân dài liên tiếp, mỗi nến mở trong thân nến trước, đóng thấp hơn, gần đáy nến
    ba = n[i - 2:i + 1]
    if (all(giam(b) and than(b) > 0.5 * a and rau_duoi(b) <= 0.3 * bien(b) for b in ba)
            and all(ba[x - 1]["c"] <= ba[x]["o"] <= ba[x - 1]["o"] and ba[x]["c"] < ba[x - 1]["c"] for x in (1, 2))):
        ds.append(("ba quạ đen", 3))
    return ds


def gio_vn(ts):
    return datetime.fromtimestamp(ts, GIO_VN).strftime("%H:%M %d/%m")


def quet_mo_hinh(da_dong, dang_chay, gia, huong):
    """Tìm mô hình gần nhất còn hiệu lực theo đúng hướng cần (1 = mua, -1 = bán). Trả về dict hoặc None."""
    n = da_dong
    if len(n) < max(SO_NEN_XET_DINH_DAY + 3, SO_NEN_TIM_MUC_TIEU + 1):
        return None
    atr = tinh_atr(n)
    for i in range(len(n) - 1, len(n) - 1 - SO_NEN_GAN_NHAT_XET, -1):
        a = atr[i]
        if a <= 0:
            continue
        cua_so = n[i - SO_NEN_XET_DINH_DAY:i + 1]
        sau = n[i + 1:] + dang_chay

        # Mô hình tăng: vùng nến tạo mô hình (ít nhất 3 nến) phải chứa đáy thấp nhất của cửa sổ
        ten, day, so_nen = [], None, 1
        for (tm, so) in (mo_hinh_tang(n, i, a) if huong == 1 else []):
            d = min(b["l"] for b in n[i - max(3, so) + 1:i + 1])
            if d <= min(b["l"] for b in cua_so):
                ten.append(tm)
                so_nen = max(so_nen, so)
                day = d if day is None else min(day, d)
        if ten and gia > day and all(b["l"] > day for b in sau):
            cat_lo = day - 0.1 * a
            muc_tieu = max(b["h"] for b in n[-SO_NEN_TIM_MUC_TIEU:])
            if muc_tieu <= gia:
                muc_tieu = gia + 2 * (gia - cat_lo)
            return {"huong": 1, "mo_hinh": " + ".join(ten), "gio_nen": gio_vn(n[i]["dong"]), "chi_so": i, "so_nen": so_nen,
                    "cat_lo": cat_lo, "muc_tieu": muc_tieu}

        ten, dinh, so_nen = [], None, 1
        for (tm, so) in (mo_hinh_giam(n, i, a) if huong == -1 else []):
            d = max(b["h"] for b in n[i - max(3, so) + 1:i + 1])
            if d >= max(b["h"] for b in cua_so):
                ten.append(tm)
                so_nen = max(so_nen, so)
                dinh = d if dinh is None else max(dinh, d)
        if ten and gia < dinh and all(b["h"] < dinh for b in sau):
            cat_lo = dinh + 0.1 * a
            muc_tieu = min(b["l"] for b in n[-SO_NEN_TIM_MUC_TIEU:])
            if muc_tieu >= gia:
                muc_tieu = gia - 2 * (cat_lo - gia)
            return {"huong": -1, "mo_hinh": " + ".join(ten), "gio_nen": gio_vn(n[i]["dong"]), "chi_so": i, "so_nen": so_nen,
                    "cat_lo": cat_lo, "muc_tieu": muc_tieu}
    return None


def dau_ngay_san(ts):
    """Thời điểm mở cửa ngày giao dịch của sàn chứa thời điểm ts (0 giờ sàn = 17 giờ New York)."""
    lech = lech_gio_san(ts)
    return (ts + lech) // 86400 * 86400 - lech


def cach_do_suc_manh(bay_gio, nen_mau):
    """Sức mạnh tính giống MarketMilk: % thay đổi từ giá mở cửa ngày của sàn.
    Ngay đầu ngày (sức mạnh chưa hình thành) thì dùng sức mạnh cả ngày vừa kết thúc."""
    dau = dau_ngay_san(bay_gio)
    if bay_gio - dau >= SO_GIO_DAU_NGAY * 3600:
        return "từ giá mở cửa ngày", dau, bay_gio
    truoc = [x[0] for x in nen_mau if x[0] < dau]
    if not truoc:
        return "từ giá mở cửa ngày", dau, bay_gio
    return "cả ngày hôm trước", dau_ngay_san(truoc[-1]), dau


def thay_doi_phan_tram(nen_gio, moc_dau, moc_cuoi):
    """% thay đổi từ giá mở của nến giờ đầu tiên sau mốc đầu, tới giá đóng của nến giờ cuối cùng trước mốc cuối."""
    gia_dau = next((o for (t, o, h, l, c) in nen_gio if t >= moc_dau), None)
    gia_cuoi = None
    for (t, o, h, l, c) in nen_gio:
        if t < moc_cuoi:
            gia_cuoi = c
    if not gia_dau or gia_cuoi is None:
        return 0.0
    return (gia_cuoi - gia_dau) / gia_dau * 100


def phan_tich(lay_nen=lay_nen_gio, bay_gio=None):
    bay_gio = bay_gio or int(time.time())
    tong = [0.0] * 8
    dem = [0] * 8
    tho = {}
    dau = dau_ngay_san(bay_gio)
    cach_do, moc_dau, moc_cuoi = "từ giá mở cửa ngày", dau, bay_gio
    for (i, j) in CAP:
        ten = TIEN[i] + TIEN[j]
        nen = [x for x in lay_nen(ten) if x[0] < bay_gio]
        if len(nen) < 100:
            print(f"Thiếu dữ liệu {ten}, bỏ qua")
            continue
        tho[(i, j)] = nen
        if len(tho) == 1:
            cach_do, moc_dau, moc_cuoi = cach_do_suc_manh(bay_gio, nen)
        pct = thay_doi_phan_tram(nen, moc_dau, moc_cuoi)
        tong[i] += pct
        dem[i] += 1
        tong[j] -= pct
        dem[j] += 1
    suc_manh = [tong[c] / dem[c] if dem[c] else 0.0 for c in range(8)]
    xep_hang = sorted(range(8), key=lambda c: -suc_manh[c])

    # Chỉ ghép: đồng mạnh nhất với 3 đồng yếu nhất, và đồng yếu nhất với 3 đồng mạnh nhất.
    # Luôn mua đồng mạnh, bán đồng yếu.
    manh_nhat, yeu_nhat = xep_hang[0], xep_hang[-1]
    ghep = [(manh_nhat, y) for y in xep_hang[-3:][::-1]] + [(m, yeu_nhat) for m in xep_hang[1:3]]
    chon = {}
    for (m, y) in ghep:
        if (m, y) in tho:
            chon[(m, y)] = 1        # đồng mạnh đứng trước trong tên cặp: MUA
        elif (y, m) in tho:
            chon[(y, m)] = -1       # đồng yếu đứng trước trong tên cặp: BÁN

    dat, loai, theo_doi = [], [], []
    nen_dong_moi_nhat = 0
    tat_ca_nen = {}  # Lưu toàn bộ 28 cặp phục vụ TradingView Chart & Sonic R

    for (i, j), nen in tho.items():
        ten_cap = f"{TIEN[i]}/{TIEN[j]}"
        so = 3 if TIEN[j] == "JPY" else 5
        da_dong, dang_chay = gop_nen_4_gio(nen, bay_gio)
        if da_dong:
            nen_dong_moi_nhat = max(nen_dong_moi_nhat, da_dong[-1]["dong"])

        # Lưu 100 nến cho TradingView
        tat_ca = da_dong + dang_chay
        bat_dau_tv = max(0, len(tat_ca) - SO_NEN_TRADINGVIEW)
        tat_ca_nen[ten_cap] = [[b["dong"], round(b["o"], so), round(b["h"], so), round(b["l"], so), round(b["c"], so)]
                               for b in tat_ca[bat_dau_tv:]]

        if (i, j) not in chon:
            continue
        huong = chon[(i, j)]
        gia = nen[-1][4]
        th = quet_mo_hinh(da_dong, dang_chay, gia, huong)
        theo_doi.append({
            "cap": ten_cap,
            "huong": "MUA" if huong == 1 else "BÁN",
            "chenh": round(abs(suc_manh[i] - suc_manh[j]), 2),
            "trang_thai": th["mo_hinh"] if th else "Chưa có mô hình đảo chiều"
        })
        if not th:
            continue
        rui_ro = abs(gia - th["cat_lo"])
        chenh = suc_manh[i] - suc_manh[j] if th["huong"] == 1 else suc_manh[j] - suc_manh[i]
        dong = {
            "cap": ten_cap, "goc": TIEN[i], "dinh": TIEN[j],
            "huong": "MUA" if th["huong"] == 1 else "BÁN",
            "mo_hinh": th["mo_hinh"], "gio_nen": th["gio_nen"],
            "chenh": round(chenh, 2),
            "gia": round(gia, so), "cat_lo": round(th["cat_lo"], so), "muc_tieu": round(th["muc_tieu"], so),
            "loi_lo": round(abs(th["muc_tieu"] - gia) / rui_ro, 1) if rui_ro > 0 else 0,
        }
        # Giá chờ: mức giá hồi về để lệnh đạt lời/lỗ 1:1,5 (cắt lỗ và mục tiêu giữ nguyên)
        if dong["loi_lo"] < 1.5:
            gia_cho = (th["muc_tieu"] + 1.5 * th["cat_lo"]) / 2.5
            if (th["huong"] == 1 and th["cat_lo"] < gia_cho < gia) or (th["huong"] == -1 and gia < gia_cho < th["cat_lo"]):
                dong["gia_cho"] = round(gia_cho, so)
        # Nến 4 giờ gần nhất để vẽ biểu đồ nhỏ (gồm cả nến đang chạy)
        bat_dau = max(0, len(tat_ca) - SO_NEN_TREN_BIEU_DO)
        dong["nen"] = [[b["dong"], round(b["o"], so), round(b["h"], so), round(b["l"], so), round(b["c"], so)]
                       for b in tat_ca[bat_dau:]]
        dong["chi_so_mh"] = th["chi_so"] - bat_dau
        dong["so_le"] = so
        dong["so_nen_mh"] = th["so_nen"]
        dat.append(dong)

    dat.sort(key=lambda d: -d["chenh"])
    theo_doi.sort(key=lambda d: -d["chenh"])

    # Tạo kho dữ liệu đa khung (M15, H4, 1D) kèm trọn bộ Sonic R (EMA 34 H/C/L, 89, 200, 610)
    da_khung = {}
    cac_cap_can_lay = [d["cap"] for d in theo_doi[:5]]
    for d in dat:
        if d["cap"] not in cac_cap_can_lay:
            cac_cap_can_lay.append(d["cap"])

    print(f"Đang tải nến M15 và 1D kèm Sonic R cho {len(cac_cap_can_lay)} cặp theo dõi...")
    for ten_cap in cac_cap_can_lay:
        so = 3 if "JPY" in ten_cap else 5
        parts = ten_cap.split('/')
        if (parts[0], parts[1]) in [(TIEN[i], TIEN[j]) for (i, j) in CAP]:
            ij = (TIEN.index(parts[0]), TIEN.index(parts[1]))
        elif (parts[1], parts[0]) in [(TIEN[i], TIEN[j]) for (i, j) in CAP]:
            ij = (TIEN.index(parts[1]), TIEN.index(parts[0]))
        else:
            continue
        
        if ij in tho:
            da_dong, dang_chay = gop_nen_4_gio(tho[ij], bay_gio)
            tat_ca = da_dong + dang_chay
            h4_bars = [[b["dong"], b["o"], b["h"], b["l"], b["c"]] for b in tat_ca]
            pack_h4 = dong_goi_nen_kem_ema(h4_bars, so, 150)
            pack_m15_d1 = lay_nen_15m_va_1d(ten_cap, so)
            da_khung[ten_cap] = {
                "15": pack_m15_d1.get("15", []),
                "240": pack_h4,
                "D": pack_m15_d1.get("D", []),
            }

    canh_bao = []
    for c in TIEN:
        mua = sum(1 for d in dat if (d["huong"] == "MUA" and d["goc"] == c) or (d["huong"] == "BÁN" and d["dinh"] == c))
        ban = sum(1 for d in dat if (d["huong"] == "BÁN" and d["goc"] == c) or (d["huong"] == "MUA" and d["dinh"] == c))
        if mua >= 2:
            canh_bao.append(f"Đang mua {c} trong {mua} lệnh. Nếu {c} quay đầu, các lệnh này cùng lỗ. Nên chia nhỏ khối lượng.")
        if ban >= 2:
            canh_bao.append(f"Đang bán {c} trong {ban} lệnh. Nếu {c} bật tăng, các lệnh này cùng lỗ. Nên chia nhỏ khối lượng.")

    return {
        "cap_nhat": datetime.fromtimestamp(bay_gio, GIO_VN).strftime("%H:%M %d/%m/%Y"),
        "nen_4_gio_dong": gio_vn(nen_dong_moi_nhat) if nen_dong_moi_nhat else "",
        "ma_nen": nen_dong_moi_nhat,
        "nen_dong_ts": nen_dong_moi_nhat,
        "so_cap_doc_duoc": len(tho),
        "cach_do": cach_do,
        "suc_manh": [{"tien": TIEN[c], "phan_tram": round(suc_manh[c], 2)} for c in xep_hang],
        "dat": dat, "loai": loai, "theo_doi": theo_doi, "tat_ca_nen": tat_ca_nen, "da_khung": da_khung, "canh_bao": canh_bao,
        "cai_dat": {"so_nen_dinh_day": SO_NEN_XET_DINH_DAY, "so_nen_gan_nhat": SO_NEN_GAN_NHAT_XET,
                    "so_nen_muc_tieu": SO_NEN_TIM_MUC_TIEU},
    }


def soan_tin_tom_tat(kq):
    """Tin nhắn văn bản ngắn gọn, có thể gửi độc lập khi không vẽ được biểu đồ."""
    dong_sm = []
    for x in kq["suc_manh"]:
        dau = "+" if x["phan_tram"] > 0 else ""
        dong_sm.append(f"{x['tien']}: {dau}{x['phan_tram']:.2f}%")
    t = [f"<b>BÀN GHÉP CẶP H4 & TRADINGAGENTS AI</b>",
         f"Nến đóng lúc <b>{kq['nen_4_gio_dong']}</b>", "",
         f"<b>Sức mạnh tiền tệ</b> ({kq['cach_do']})",
         "<pre>" + "\n".join(dong_sm) + "</pre>"]
    t.append("<b>5 cặp mạnh – yếu đang theo dõi</b>")
    for x in kq.get("theo_doi", []):
        dau = "🟢" if x["huong"] == "MUA" else "🔴"
        co = "✅ " + x["trang_thai"] if x["trang_thai"] != "Chưa có mô hình đảo chiều" else "chờ mô hình"
        t.append(f"{dau} {x['huong']} {x['cap']} · {co}")
    t.append("")
    if not kq["dat"]:
        t += ["Chưa cặp nào có mô hình nến đảo chiều đúng hướng. Chờ nến tiếp theo."]
    else:
        t.append(f"<b>{len(kq['dat'])} lệnh đề xuất</b> (ảnh chi tiết ở tin sau)")
        for k, d in enumerate(kq["dat"], 1):
            dau = "🟢" if d["huong"] == "MUA" else "🔴"
            cho = f" · Chờ hồi: {d['gia_cho']}" if "gia_cho" in d else ""
            t.append(f"{k}. {dau} <b>{d['huong']} {d['cap']}</b>: {d['mo_hinh']} (đóng lúc {d['gio_nen']})")
            t.append(f"   Vào: {d['gia']} · TP: {d['muc_tieu']} · SL: {d['cat_lo']} · R:R 1:{d['loi_lo']}{cho}")
    if kq["canh_bao"]:
        t += ["", "<b>Cảnh báo rủi ro:</b>"] + [f"⚠️ {c}" for c in kq["canh_bao"]]
    return "\n".join(t)


def chuan_bi_matplotlib():
    """Cài phông DejaVu Sans để Matplotlib hiển thị tiếng Việt trên GitHub Actions."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    try:
        import urllib.request, os
        font_dir = os.path.expanduser("~/.fonts")
        font_file = os.path.join(font_dir, "DejaVuSans.ttf")
        if not os.path.exists(font_file):
            os.makedirs(font_dir, exist_ok=True)
            url = "https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf"
            urllib.request.urlretrieve(url, font_file)
        import matplotlib.font_manager as fm
        fm.fontManager.addfont(font_file)
        plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial"]
    except Exception as e:
        print(f"Cảnh báo phông chữ: {e}")
        plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial"]
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def ve_bieu_do(d, duong_dan):
    """Vẽ nến 4 giờ kèm vùng vào lệnh, cắt lỗ, mục tiêu. Lưu ảnh PNG."""
    plt = chuan_bi_matplotlib()
    from matplotlib.patches import Rectangle
    nen = d["nen"]
    sl = d["so_le"]
    vao = d.get("gia_cho") or d["gia"]
    mua = d["huong"] == "MUA"
    XANH, DO, LAM, VANG, XAM, CHU = "#16a06a", "#d84a3c", "#2563c9", "#e8a317", "#8a96a3", "#1c2733"

    fig, ax = plt.subplots(figsize=(8, 5.4), dpi=140)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#fbfcfd")
    n = len(nen)

    for k, (t, o, h, l, c) in enumerate(nen):
        mau = XANH if c >= o else DO
        ax.plot([k, k], [l, h], color=mau, linewidth=1.2, zorder=2)
        ax.add_patch(Rectangle((k - 0.32, min(o, c)), 0.64, max(abs(c - o), 10 ** -sl),
                               facecolor=mau, edgecolor=mau, zorder=3))

    # Vùng lời và lỗ tính từ nến mô hình sang phải
    x0, x1 = d["chi_so_mh"] + 0.5, n + 3
    ax.add_patch(Rectangle((x0, min(vao, d["cat_lo"])), x1 - x0, abs(vao - d["cat_lo"]),
                           facecolor=DO, alpha=0.10, zorder=1))
    ax.add_patch(Rectangle((x0, min(vao, d["muc_tieu"])), x1 - x0, abs(vao - d["muc_tieu"]),
                           facecolor=XANH, alpha=0.10, zorder=1))
    # Đánh dấu nến mô hình
    i = d["chi_so_mh"]
    ax.axvspan(i - d.get("so_nen_mh", 1) + 0.5, i + 0.5, color=VANG, alpha=0.22, zorder=0)
    cum = nen[max(0, i - d.get("so_nen_mh", 1) + 1):i + 1]
    y_mui = min(x[3] for x in cum) if mua else max(x[2] for x in cum)
    ax.annotate(d["mo_hinh"].upper(), xy=(i, y_mui),
                xytext=(i, y_mui - (ax.get_ylim()[1] - ax.get_ylim()[0]) * 0.05 if mua else y_mui + (ax.get_ylim()[1] - ax.get_ylim()[0]) * 0.05),
                ha="center", fontsize=9, fontweight="bold", color=CHU,
                arrowprops=dict(arrowstyle="->", color=CHU, lw=1.2))

    # Ba đường: mục tiêu, vào lệnh, cắt lỗ
    def ke(gia, mau, nhan, kieu="-"):
        ax.axhline(gia, color=mau, linestyle=kieu, linewidth=1.2, zorder=4)
        ax.text(n + 0.2, gia, f"{nhan}: {gia:.{sl}f}", color=mau,
                fontsize=8.5, fontweight="bold", va="center")

    ke(d["muc_tieu"], XANH, "MỤC TIÊU")
    if d.get("gia_cho"):
        ke(d["gia_cho"], LAM, "LỆNH CHỜ (R:R 1:1,5)")
        ke(d["gia"], XAM, "Hiện tại", kieu=":")
    else:
        ke(d["gia"], LAM, "VÀO LỆNH")
    ke(d["cat_lo"], DO, "CẮT LỖ")

    ax.set_xlim(-0.5, n + 4.5)
    ax.grid(True, linestyle="--", alpha=0.25, color=XAM)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    huong_str = "MUA" if mua else "BÁN"
    mau_huong = XANH if mua else DO
    fig.text(0.08, 0.95, f"{huong_str} {d['cap']}", fontsize=14, fontweight="bold", color=mau_huong)
    fig.text(0.08, 0.915, f"{d['mo_hinh']} (nến 4H đóng lúc {d['gio_nen']}) · R:R 1:{d['loi_lo']}",
             fontsize=9.5, color=XAM)

    plt.subplots_adjust(top=0.88, bottom=0.08, left=0.08, right=0.82)
    fig.savefig(duong_dan, dpi=140, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)


def gui_telegram(van_ban, anh_ds=None):
    """Gửi báo cáo qua Telegram Bot API (không cần cài thêm thư viện python-telegram-bot)."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Chưa cài TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID trong Secrets")
        return False
    base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

    def post(url, data):
        req = urllib.request.Request(url, data=data, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())

    # Gửi tin nhắn tóm tắt
    dl = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID, "text": van_ban, "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    try:
        post(f"{base}/sendMessage", dl)
    except Exception as e:
        print(f"Lỗi gửi tin nhắn Telegram: {e}")
        return False

    # Gửi từng ảnh biểu đồ
    for anh in (anh_ds or []):
        if not os.path.exists(anh):
            continue
        try:
            boundary = uuid.uuid4().hex
            body = []
            body.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{TELEGRAM_CHAT_ID}\r\n".encode())
            with open(anh, "rb") as f:
                body.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"chart.png\"\r\nContent-Type: image/png\r\n\r\n".encode())
                body.append(f.read())
                body.append(b"\r\n")
            body.append(f"--{boundary}--\r\n".encode())
            req = urllib.request.Request(f"{base}/sendPhoto", data=b"".join(body),
                                         headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
            with urllib.request.urlopen(req, timeout=30) as r:
                pass
        except Exception as e:
            print(f"Lỗi gửi ảnh Telegram: {e}")
    return True


def doc_lich_su_nen():
    if os.path.exists(FILE_LICH_SU):
        try:
            with open(FILE_LICH_SU, "r", encoding="utf-8") as f:
                return json.load(f).get("nen_dong_ts", 0)
        except Exception:
            pass
    return 0


def ghi_lich_su_nen(nen_dong_ts):
    with open(FILE_LICH_SU, "w", encoding="utf-8") as f:
        json.dump({"nen_dong_ts": nen_dong_ts}, f)


def doc_du_lieu_mau():
    """Đọc dữ liệu mẫu đi kèm repo khi API sàn bị lỗi hoặc đang chạy thử offline."""
    file_mau = os.path.join(THU_MUC, "du_lieu_mau.json")
    if os.path.exists(file_mau):
        with open(file_mau, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def main():
    print("Bắt đầu quét 28 cặp tiền tệ...")
    kq = phan_tich()
    dung_mau = False
    if kq["so_cap_doc_duoc"] < 20:
        print(f"Chỉ đọc được {kq['so_cap_doc_duoc']}/28 cặp. Thử dùng dữ liệu mẫu...")
        mau = doc_du_lieu_mau()
        if mau:
            kq = phan_tich(lay_nen=lambda sym: mau.get(sym, []))
            dung_mau = True
            kq["du_lieu_mau"] = True
    kq["du_lieu_mau"] = dung_mau

    # Ghi file data.json cho trang web
    with open(FILE_DATA, "w", encoding="utf-8") as f:
        json.dump(kq, f, ensure_ascii=False, indent=2)
    print(f"Đã cập nhật {FILE_DATA}")

    # Kiểm tra xem có nến 4 giờ mới đóng không
    nen_cu = doc_lich_su_nen()
    nen_moi = kq.get("nen_dong_ts", 0)
    co_nen_moi = nen_moi > nen_cu

    print(f"Nến vừa đóng: {kq['nen_4_gio_dong']} (ts={nen_moi}), nến đã gửi lần trước: ts={nen_cu}")
    if not co_nen_moi and not LUON_GUI:
        print("Chưa có nến 4 giờ mới, không gửi Telegram.")
        return

    # Vẽ biểu đồ cho các lệnh đạt chuẩn
    anh_ds = []
    for k, d in enumerate(kq["dat"]):
        duong_dan = os.path.join(THU_MUC, f"chart_{k}.png")
        try:
            ve_bieu_do(d, duong_dan)
            anh_ds.append(duong_dan)
        except Exception as e:
            print(f"Lỗi vẽ biểu đồ {d['cap']}: {e}")

    tin = soan_tin_tom_tat(kq)
    print("Nội dung gửi Telegram:\n" + tin)
    if gui_telegram(tin, anh_ds):
        print("Đã gửi báo cáo Telegram thành công.")
        if nen_moi and not dung_mau:
            ghi_lich_su_nen(nen_moi)
    else:
        print("Chưa gửi được Telegram (xem lỗi ở trên).")


if __name__ == "__main__":
    main()
