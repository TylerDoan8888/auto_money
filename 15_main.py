import time
from PIL import ImageGrab, Image
import cv2
import numpy as np
import pytesseract
import ctypes
import pyautogui
import time

# ========== CẤU HÌNH ==========
pytesseract.pytesseract.tesseract_cmd = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"

# Toạ độ vùng tiền cược (chỉnh lại cho đúng màn hình bạn)
TAI_BBOX = (775, 670, 990, 720)   # vùng tiền cược Tài
XIU_BBOX = (1055, 670, 1270, 720) # vùng tiền cược Xỉu

# Vùng theo dõi tiền tài khoản để biết win/lose
ACCOUNT_BBOX = (300, 200, 530, 240)

# Vùng đồng hồ đếm ngược
CLOCK_BBOX = (220, 420, 430, 570)

# Tọa độ click nút cược
TAI_CLICK_POS = (650, 750)   # vị trí click Tài
XIU_CLICK_POS = (1335, 750)  # vị trí click Xỉu

# ========== TRẠNG THÁI ==========
game_no = 1
flag_direction = -1   # "win"/"lose" cho nhà cái
martingale_level = 1        # số lần click hiện tại (1, 2, 4, ...)
last_bet_side = None        # bên mình đã cược ở ván trước
last_balance = None         # số dư ván trước


# ========== HỖ TRỢ ==========
def extract_money_from_image(image: Image.Image, debug=False, tag=""):
    img_np = np.array(image.convert("RGB"))
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

    # Tăng tương phản + sharpen để làm rõ chữ số
    gray = cv2.convertScaleAbs(gray, alpha=2.0, beta=0)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    text = pytesseract.image_to_string(
        thresh,
        config='--psm 7 -c tessedit_char_whitelist=0123456789'
    )

    text = text.strip().replace(",", "").replace(".", "")

    # DEBUG: lưu file ra để kiểm tra
    if debug:
        cv2.imwrite(f"debug_gray_{tag}.png", gray)
        cv2.imwrite(f"debug_thresh_{tag}.png", thresh)
        print(f"[DEBUG {tag}] OCR raw = '{text}'")

    return int(text) if text.isdigit() else 0



# ======== CLICK CỰC NHANH BẰNG WINAPI ==========
PUL = ctypes.POINTER(ctypes.c_ulong)

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", PUL)]

class INPUT_I(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong),
                ("ii", INPUT_I)]

SendInput = ctypes.windll.user32.SendInput

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

# ==== Hàm click tuyệt đối ====
def fast_click_absolute(x, y, times=1):
    screen_w, screen_h = pyautogui.size()
    abs_x = int(x * 65535 / screen_w)
    abs_y = int(y * 65535 / screen_h)

    for _ in range(times):
        extra = ctypes.c_ulong(0)

        # Chuột xuống
        ii = INPUT_I()
        ii.mi = MOUSEINPUT(abs_x, abs_y, 0,
                           MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_MOVE,
                           0, ctypes.pointer(extra))
        input_event = INPUT(ctypes.c_ulong(0), ii)
        SendInput(1, ctypes.pointer(input_event), ctypes.sizeof(input_event))

        # Chuột nhả
        ii = INPUT_I()
        ii.mi = MOUSEINPUT(abs_x, abs_y, 0,
                           MOUSEEVENTF_LEFTUP | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_MOVE,
                           0, ctypes.pointer(extra))
        input_event = INPUT(ctypes.c_ulong(0), ii)
        SendInput(1, ctypes.pointer(input_event), ctypes.sizeof(input_event))

        time.sleep(0.002)  # delay 2ms

# ==== Hàm click theo bên Tài/Xỉu ====
def click_side(side: str, times: int):
    pos = TAI_CLICK_POS if side == "Tài" else XIU_CLICK_POS
    fast_click_absolute(pos[0], pos[1], times)
    print(f"🖱️ Đặt {side} với {times} click tại {pos}")

# ========== LOGIC ==========
def process_result(game_no: int):
    """Xử lý tại giây 28 - kiểm tra win/lose dựa vào số dư"""
    global last_balance, flag_direction, martingale_level

    current_balance = extract_money_from_image(ImageGrab.grab(bbox=ACCOUNT_BBOX))
    print(f"[💳 G{game_no}] Balance hiện tại = {current_balance}")

    if last_balance is not None:
        if current_balance > last_balance:
            print("👉 Bạn WIN ")
            martingale_level = 1
        elif current_balance < last_balance:
            flag_direction = - flag_direction
            print("👉 Bạn LOSE ")
            martingale_level *= 2
        else:
            print("👉 Không thay đổi số dư, có thể hoà hoặc miss OCR")
    last_balance = current_balance

def process_money(game_no: int):
    """Xử lý tại giây 05 - tiền cược"""
    global last_bet_side

    tai = extract_money_from_image(ImageGrab.grab(bbox=TAI_BBOX))
    xiu = extract_money_from_image(ImageGrab.grab(bbox=XIU_BBOX))

    if abs(tai - xiu) > 5_000_000:
        if tai > xiu:
            big_side, small_side = "Tài", "Xỉu"
        else:
            big_side, small_side = "Xỉu", "Tài"

        if flag_direction == -1:
            bet_side = small_side
        elif flag_direction == 1:
            bet_side = big_side

        click_side(bet_side, martingale_level)
        print(f"👉 Cược THEO ({bet_side})")

# ========== VÒNG LẶP ==========
def wait_for_target_time():
    global game_no
    while True:
        time_img = ImageGrab.grab(bbox=CLOCK_BBOX).convert("RGB")
        time_np = np.array(time_img)
        gray = cv2.cvtColor(time_np, cv2.COLOR_RGB2GRAY)
        _, binary = cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY)

        text = pytesseract.image_to_string(
            binary, config='--psm 7 -c tessedit_char_whitelist=0123456789O'
        )
        text = text.strip().replace(" ", "").replace("\n", "").upper().replace("O", "0")

        if text == "25":
            process_result(game_no)
            time.sleep(13)
        elif text == "06":
            process_money(game_no)
            game_no += 1
            time.sleep(10)
        else:
            time.sleep(0.1)

if __name__ == "__main__":
    wait_for_target_time()
