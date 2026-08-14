# SPDX-FileCopyrightText: 2025
# SPDX-License-Identifier: MIT

import time
import rtc
from os import getenv

import board
import busio
import displayio
import neopixel
from digitalio import DigitalInOut
from adafruit_display_text import label
from adafruit_bitmap_font import bitmap_font
from adafruit_matrixportal.matrix import Matrix
import adafruit_esp32spi.adafruit_esp32spi as _espmod
from adafruit_esp32spi import adafruit_esp32spi
import adafruit_connection_manager
import adafruit_requests
from adafruit_ntp import NTP

# ——— Configuration ———
SSID               = getenv("CIRCUITPY_WIFI_SSID")
PASSWORD           = getenv("CIRCUITPY_WIFI_PASSWORD")

API_BASE_URL       = "https://api.weatherflow.com/wxengine/rest/spot/getSpotSetByList"
API_PARAMS         = {
    "wa_ver": "1777",
    "device_id": "00d8a1231a5807fd67e7d78d846664e1",
    "device_type": "iPhone",
    "device_os": "18.5",
    "wf_apikey": "6e564a0e-245a-4ab0-a351-359466f83aa4",
    "v": "1.3",
    "wf_token": "303a818ae828018c637e027c7900cfa0",
    "activity": "Kite",
    "spot_list": "332,334,330,336",
    "fav_spot_list": "",
    "spot_types": "1,100,101",
    "include_spot_products": "false",
    "page": "1",
    "units_distance": "mi",
    "units_wind": "kts",
    "units_temp": "f",
    "sort": "distance",
    "num_per_page": "100",
    "format": "json"
}
API_HEADERS        = {
    "User-Agent": "iKitesurf/1777 CFNetwork/3826.500.131 Darwin/24.5.0",
    "Accept": "*/*",
    "Accept-Encoding": "identity"
}
SPOT_NAMES         = ["Wall", "Pond", "Slick", "Flats"]

# colors
COLOR_LOCATION     = 0xFFFFFF
COLOR_WIND_DEFAULT = 0xFFFF00
COLOR_WIND_ALERT   = 0x00FF00
COLOR_DIRECTION    = 0x00FFFF
COLOR_TIME         = 0xFF0000

# SPI timeouts (for slow TLS/JSON)
_espmod.ESP_SPIcontrol._SPI_CHAR_TIMEOUT = 60.0
_espmod.ESP_SPIcontrol._SPI_RESP_TIMEOUT = 60.0


def percent_encode(s: str) -> str:
    safe = "-_.~"
    out = []
    for ch in s:
        o = ord(ch)
        if (48 <= o <= 57) or (65 <= o <= 90) or (97 <= o <= 122) or (ch in safe):
            out.append(ch)
        else:
            out.append("%%%02X" % o)
    return "".join(out)


def urlencode(params: dict) -> str:
    parts = [
        f"{k}={percent_encode(params[k])}"
        for k in sorted(params)
    ]
    return "&".join(parts)


def get_api_url() -> str:
    return API_BASE_URL + "?" + urlencode(API_PARAMS)


def init_esp() -> adafruit_esp32spi.ESP_SPIcontrol:
    cs  = DigitalInOut(board.ESP_CS)
    rdy = DigitalInOut(board.ESP_BUSY)
    rst = DigitalInOut(board.ESP_RESET)
    spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
    return adafruit_esp32spi.ESP_SPIcontrol(spi, cs, rdy, rst)


def connect_to_wifi(esp: adafruit_esp32spi.ESP_SPIcontrol) -> None:
    print("Connecting to Wi-Fi…")
    while not esp.is_connected:
        try:
            esp.connect_AP(SSID, PASSWORD)
        except RuntimeError:
            time.sleep(5)
    print("Connected, IP →", esp.ipv4_address)


def sync_rtc_with_ntp(esp: adafruit_esp32spi.ESP_SPIcontrol, tz_offset: int = -4) -> None:
    pool = adafruit_connection_manager.get_radio_socketpool(esp)
    try:
        ntp = NTP(pool, tz_offset=tz_offset)
        rtc.RTC().datetime = ntp.datetime
        print("RTC NTP-synced →", time.localtime())
    except Exception as e:
        print("NTP sync failed →", e)


def setup_display_and_fonts():
    displayio.release_displays()
    matrix  = Matrix(bit_depth=6)
    display = matrix.display
    group   = displayio.Group()
    display.root_group = group

    font    = bitmap_font.load_font("/fonts/4x6.bdf")
    char_w  = font.get_glyph(ord("M")).width
    char_h  = font.get_glyph(ord("0")).height

    return display, group, font, char_w, char_h


def create_labels(group, font, char_w, char_h, display):
    FIRST_LINE_Y  = 4
    ROW_SPACING   = char_h
    max_name_len  = max(len(n) for n in SPOT_NAMES)

    wind_start_x  = 1 + (max_name_len + 1) * char_w - 1
    dir_start_x   = wind_start_x + (5 + 1) * char_w  # 5 chars for "SS Kt", plus space

    wind_value_lbls = []
    wind_dir_lbls   = []

    for idx, name in enumerate(SPOT_NAMES):
        y = FIRST_LINE_Y + idx * ROW_SPACING

        # location label (white)
        loc = label.Label(font, text=name, color=COLOR_LOCATION, x=1, y=y)
        group.append(loc)

        # wind speed+unit label (yellow/green)
        val = label.Label(font, text="", color=COLOR_WIND_DEFAULT,
                          x=wind_start_x, y=y)
        group.append(val)
        wind_value_lbls.append(val)

        # wind direction label (blue)
        dr = label.Label(font, text="", color=COLOR_DIRECTION,
                         x=dir_start_x, y=y)
        group.append(dr)
        wind_dir_lbls.append(dr)

    # time label (red)
    time_lbl = label.Label(font, text="", color=COLOR_TIME,
                           x=0, y=display.height - 2)
    group.append(time_lbl)

    return wind_value_lbls, wind_dir_lbls, time_lbl


def create_requests_session(esp):
    pool = adafruit_connection_manager.get_radio_socketpool(esp)
    ssl  = adafruit_connection_manager.get_radio_ssl_context(esp)
    return adafruit_requests.Session(pool, ssl)


def is_onshore(idx: int, direction: str) -> bool:
    # Wall, Pond, Slick: alert on southern-component winds
    if idx < 3:
        return "S" in direction
    # Flats: alert on northern-component winds
    if idx == 3:
        return "N" in direction
    return False


def update_wind_labels(data, wind_vals, wind_dirs):
    names = data["data_names"]
    i_desc = names.index("wind_desc")
    values = data["data_values"]
    for i in range(len(SPOT_NAMES)):
        raw = values[i][i_desc]  # e.g. "12 KT NW"
        spd, _, _, d = raw.split()
        speed = int(spd)

        # pad speed to width=2
        speed_str = (" " * (2 - len(spd))) + spd

        wind_vals[i].text = f"{speed_str} Kt"
        wind_dirs[i].text = d

        # highlight green if onshore/northern logic matches AND speed > 15
        if is_onshore(i, d) and speed > 15:
            wind_vals[i].color = COLOR_WIND_ALERT
        else:
            wind_vals[i].color = COLOR_WIND_DEFAULT

        print(f"{SPOT_NAMES[i]} →", wind_vals[i].text, wind_dirs[i].text)


def update_time_label(time_lbl, display, char_w):
    now = time.localtime()
    h   = now.tm_hour
    am  = "AM"
    if h == 0:
        disp_h = 12
    elif h >= 12:
        am     = "PM"
        disp_h = h - 12 if h > 12 else 12
    else:
        disp_h = h

    ts = f"{disp_h}:{now.tm_min:02d} {am}"
    time_lbl.text = ts

    # center horizontally
    tw = len(ts) * char_w
    time_lbl.x = (display.width - tw) // 2
    print("Time →", ts)


def show_error(wind_vals, wind_dirs, time_lbl):
    for v, d in zip(wind_vals, wind_dirs):
        v.text = "Error"
        d.text = ""
    time_lbl.text = ""


def main():
    # hardware init
    esp, npix = init_esp(), neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=0.2)
    npix.fill((0, 255, 0))

    # connectivity
    connect_to_wifi(esp)
    sync_rtc_with_ntp(esp)

    # display & labels
    display, group, font, char_w, char_h = setup_display_and_fonts()
    winds, dirs, time_lbl = create_labels(group, font, char_w, char_h, display)

    url = get_api_url()
    session = create_requests_session(esp)

    while True:
        try:
            print("Fetching →", url)
            resp = session.get(url, headers=API_HEADERS, timeout=60)
            data = resp.json()
            resp.close()

            if data.get("status", {}).get("status_code", -1) == 0:
                update_wind_labels(data, winds, dirs)
                update_time_label(time_lbl, display, char_w)
            else:
                show_error(winds, dirs, time_lbl)

        except Exception as e:
            print("Fetch failed →", e)
            esp.reset()
            time.sleep(5)
            connect_to_wifi(esp)
            continue

        display.refresh()
        time.sleep(60)

main()
