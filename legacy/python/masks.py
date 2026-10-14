#!/usr/bin/env python3
"""
Device / computer / mobile masks for EXIF & PDF identity scrambling.

Each mask makes a file look like it was captured or authored on a real-world
device (phone, camera, tablet, computer, scanner) from a given region.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeviceMask:
    """A spoofed device identity usable for EXIF and/or PDF metadata."""

    id: str
    label: str
    category: str  # phone | camera | tablet | computer | scanner | drone
    region: str  # ISO-ish region key: US, JP, DE, FR, RU, CN, KR, KP, VN, BR, GB, ...
    country: str
    city: str
    make: str
    model: str
    software: str
    lens_make: str = ""
    lens_model: str = ""
    gps_lat: float = 0.0
    gps_lon: float = 0.0
    # PDF / document identity
    creator: str = ""
    producer: str = ""
    artist: str = ""
    timezone_offset: str = "+00:00"  # informational; used when stamping PDF dates
    locale_hint: str = "en_US"  # for UserComment / cultural flavor


# ---------------------------------------------------------------------------
# Catalog — phones, cameras, computers, tablets from around the world
# ---------------------------------------------------------------------------

MASKS: list[DeviceMask] = [
    # --- United States ---
    DeviceMask(
        "us-iphone15pm",
        "Apple iPhone 15 Pro Max (USA)",
        "phone",
        "US",
        "United States",
        "New York",
        "Apple",
        "iPhone 15 Pro Max",
        "17.2.1",
        gps_lat=40.7128,
        gps_lon=-74.0060,
        creator="Photos",
        producer="iOS 17.2.1",
        timezone_offset="-05:00",
        locale_hint="en_US",
    ),
    DeviceMask(
        "us-pixel8",
        "Google Pixel 8 Pro (USA)",
        "phone",
        "US",
        "United States",
        "San Francisco",
        "Google",
        "Pixel 8 Pro",
        "HDR+ 1.0.674945365z",
        gps_lat=37.7749,
        gps_lon=-122.4194,
        creator="Google Photos",
        producer="Android 14",
        timezone_offset="-08:00",
        locale_hint="en_US",
    ),
    DeviceMask(
        "us-macbook",
        "MacBook Pro / macOS Preview (USA)",
        "computer",
        "US",
        "United States",
        "Cupertino",
        "Apple",
        "MacBookPro18,3",
        "macOS 14.3 Preview",
        gps_lat=37.3230,
        gps_lon=-122.0322,
        creator="Preview",
        producer="macOS Version 14.3 (Build 23D56)",
        timezone_offset="-08:00",
        locale_hint="en_US",
    ),
    DeviceMask(
        "us-win11",
        "Windows 11 PC / Photos (USA)",
        "computer",
        "US",
        "United States",
        "Seattle",
        "Microsoft",
        "Surface Laptop 5",
        "Windows Photos 2024.11050.3001.0",
        gps_lat=47.6062,
        gps_lon=-122.3321,
        creator="Microsoft® Word for Microsoft 365",
        producer="Microsoft® Word for Microsoft 365",
        timezone_offset="-08:00",
        locale_hint="en_US",
    ),
    DeviceMask(
        "us-canonr5",
        "Canon EOS R5 (USA)",
        "camera",
        "US",
        "United States",
        "Los Angeles",
        "Canon",
        "Canon EOS R5",
        "Firmware Version 1.8.1",
        "Canon",
        "RF24-70mm F2.8 L IS USM",
        34.0522,
        -118.2437,
        creator="Digital Photo Professional",
        producer="Canon Digital Camera",
        timezone_offset="-08:00",
        locale_hint="en_US",
    ),
    # --- United Kingdom ---
    DeviceMask(
        "gb-iphone14",
        "Apple iPhone 14 (UK)",
        "phone",
        "GB",
        "United Kingdom",
        "London",
        "Apple",
        "iPhone 14",
        "17.1.2",
        gps_lat=51.5074,
        gps_lon=-0.1278,
        creator="Photos",
        producer="iOS 17.1.2",
        timezone_offset="+00:00",
        locale_hint="en_GB",
    ),
    DeviceMask(
        "gb-leica",
        "Leica Q3 (UK)",
        "camera",
        "GB",
        "United Kingdom",
        "Edinburgh",
        "LEICA CAMERA AG",
        "LEICA Q3",
        "2.0.1",
        "LEICA",
        "SUMMILUX 1:1.7/28 ASPH.",
        55.9533,
        -3.1883,
        creator="Adobe Photoshop Lightroom Classic 13.1",
        producer="Adobe Photoshop Lightroom Classic 13.1 (Macintosh)",
        timezone_offset="+00:00",
        locale_hint="en_GB",
    ),
    # --- Germany ---
    DeviceMask(
        "de-galaxy-s24",
        "Samsung Galaxy S24 Ultra (Germany)",
        "phone",
        "DE",
        "Germany",
        "Berlin",
        "samsung",
        "SM-S928B",
        "S928BXXU1AXCA",
        gps_lat=52.5200,
        gps_lon=13.4050,
        creator="Samsung Notes",
        producer="Android 14; SM-S928B",
        timezone_offset="+01:00",
        locale_hint="de_DE",
    ),
    DeviceMask(
        "de-leica-m11",
        "Leica M11 (Germany)",
        "camera",
        "DE",
        "Germany",
        "Wetzlar",
        "LEICA CAMERA AG",
        "LEICA M11",
        "2.0.2",
        "LEICA",
        "APO-Summicron-M 1:2/50 ASPH.",
        50.5619,
        8.5044,
        creator="Adobe Photoshop 25.3",
        producer="Adobe Photoshop 25.3 (Windows)",
        timezone_offset="+01:00",
        locale_hint="de_DE",
    ),
    DeviceMask(
        "de-thinkpad",
        "Lenovo ThinkPad / LibreOffice (Germany)",
        "computer",
        "DE",
        "Germany",
        "Munich",
        "LENOVO",
        "20W0S0Y200",
        "LibreOffice 24.2",
        gps_lat=48.1351,
        gps_lon=11.5820,
        creator="Writer",
        producer="LibreOffice 24.2.1.2 (X86_64; Linux)",
        timezone_offset="+01:00",
        locale_hint="de_DE",
    ),
    # --- France ---
    DeviceMask(
        "fr-iphone13",
        "Apple iPhone 13 (France)",
        "phone",
        "FR",
        "France",
        "Paris",
        "Apple",
        "iPhone 13",
        "16.7.5",
        gps_lat=48.8566,
        gps_lon=2.3522,
        creator="Photos",
        producer="iOS 16.7.5",
        timezone_offset="+01:00",
        locale_hint="fr_FR",
    ),
    DeviceMask(
        "fr-sony-a7iv",
        "Sony α7 IV (France)",
        "camera",
        "FR",
        "France",
        "Lyon",
        "SONY",
        "ILCE-7M4",
        "ILCE-7M4 v3.01",
        "SONY",
        "FE 24-70mm F2.8 GM II",
        45.7640,
        4.8357,
        creator="Imaging Edge Desktop",
        producer="SONY ILCE-7M4",
        timezone_offset="+01:00",
        locale_hint="fr_FR",
    ),
    DeviceMask(
        "fr-dell",
        "Dell XPS / Adobe Acrobat (France)",
        "computer",
        "FR",
        "France",
        "Marseille",
        "Dell Inc.",
        "XPS 15 9530",
        "Adobe Acrobat Pro 2024.002.20687",
        gps_lat=43.2965,
        gps_lon=5.3698,
        creator="Adobe InDesign 19.2 (Windows)",
        producer="Adobe PDF Library 17.0",
        timezone_offset="+01:00",
        locale_hint="fr_FR",
    ),
    # --- Russia ---
    DeviceMask(
        "ru-xiaomi",
        "Xiaomi 14 (Russia)",
        "phone",
        "RU",
        "Russia",
        "Moscow",
        "Xiaomi",
        "23127PN0CG",
        "MIUI Camera 6.0",
        gps_lat=55.7558,
        gps_lon=37.6173,
        creator="Mi Browser",
        producer="Android 14; 23127PN0CG",
        timezone_offset="+03:00",
        locale_hint="ru_RU",
    ),
    DeviceMask(
        "ru-nikon-z8",
        "Nikon Z8 (Russia)",
        "camera",
        "RU",
        "Russia",
        "Saint Petersburg",
        "NIKON CORPORATION",
        "NIKON Z 8",
        "Ver.2.00",
        "NIKON",
        "NIKKOR Z 24-70mm f/2.8 S",
        59.9311,
        30.3609,
        creator="NX Studio 1.5.0",
        producer="NIKON Z 8 Ver.2.00",
        timezone_offset="+03:00",
        locale_hint="ru_RU",
    ),
    DeviceMask(
        "ru-yandex",
        "Yandex Book / Windows PC (Russia)",
        "computer",
        "RU",
        "Russia",
        "Novosibirsk",
        "YANDEX",
        "YNDX-000SB",
        "Yandex Browser 24.1",
        gps_lat=55.0084,
        gps_lon=82.9357,
        creator="Microsoft Print to PDF",
        producer="Microsoft: Print To PDF",
        timezone_offset="+07:00",
        locale_hint="ru_RU",
    ),
    # --- China ---
    DeviceMask(
        "cn-huawei-p60",
        "Huawei P60 Pro (China)",
        "phone",
        "CN",
        "China",
        "Beijing",
        "HUAWEI",
        "ALN-AL10",
        "Camera 13.0.0.300",
        gps_lat=39.9042,
        gps_lon=116.4074,
        creator="Huawei Share",
        producer="HarmonyOS 4.0.0",
        timezone_offset="+08:00",
        locale_hint="zh_CN",
    ),
    DeviceMask(
        "cn-vivo",
        "vivo X100 Pro (China)",
        "phone",
        "CN",
        "China",
        "Shanghai",
        "vivo",
        "V2324A",
        "Camera 5.0.6.12",
        gps_lat=31.2304,
        gps_lon=121.4737,
        creator="vivo Office",
        producer="OriginOS 4",
        timezone_offset="+08:00",
        locale_hint="zh_CN",
    ),
    DeviceMask(
        "cn-fujifilm",
        "Fujifilm X-T5 (China)",
        "camera",
        "CN",
        "China",
        "Chengdu",
        "FUJIFILM",
        "X-T5",
        "X-T5 Ver1.20",
        "FUJIFILM",
        "XF16-55mmF2.8 R LM WR",
        30.5728,
        104.0668,
        creator="FUJIFILM X RAW STUDIO",
        producer="FUJIFILM X-T5",
        timezone_offset="+08:00",
        locale_hint="zh_CN",
    ),
    DeviceMask(
        "cn-huawei-matebook",
        "Huawei MateBook / WPS (China)",
        "computer",
        "CN",
        "China",
        "Shenzhen",
        "HUAWEI",
        "KLVL-W56W",
        "WPS Office 12.1.0.16388",
        gps_lat=22.5431,
        gps_lon=114.0579,
        creator="WPS 文字",
        producer="Kingsoft PDF 12.1",
        timezone_offset="+08:00",
        locale_hint="zh_CN",
    ),
    # --- Japan ---
    DeviceMask(
        "jp-iphone15",
        "Apple iPhone 15 (Japan)",
        "phone",
        "JP",
        "Japan",
        "Tokyo",
        "Apple",
        "iPhone 15",
        "17.3",
        gps_lat=35.6762,
        gps_lon=139.6503,
        creator="写真",
        producer="iOS 17.3",
        timezone_offset="+09:00",
        locale_hint="ja_JP",
    ),
    DeviceMask(
        "jp-sony-xperia",
        "Sony Xperia 1 V (Japan)",
        "phone",
        "JP",
        "Japan",
        "Osaka",
        "Sony",
        "XQ-DQ44",
        "61.1.A.2.21",
        gps_lat=34.6937,
        gps_lon=135.5023,
        creator="Xperia Lounge",
        producer="Android 14; XQ-DQ44",
        timezone_offset="+09:00",
        locale_hint="ja_JP",
    ),
    DeviceMask(
        "jp-canon-r6",
        "Canon EOS R6 Mark II (Japan)",
        "camera",
        "JP",
        "Japan",
        "Kyoto",
        "Canon",
        "Canon EOS R6m2",
        "Firmware Version 1.4.0",
        "Canon",
        "RF50mm F1.2 L USM",
        35.0116,
        135.7681,
        creator="Digital Photo Professional 4",
        producer="Canon EOS R6m2",
        timezone_offset="+09:00",
        locale_hint="ja_JP",
    ),
    DeviceMask(
        "jp-vaio",
        "VAIO / macOS-style PDF (Japan)",
        "computer",
        "JP",
        "Japan",
        "Yokohama",
        "VAIO",
        "VJS1258",
        "JustSystems ATOK PDF",
        gps_lat=35.4437,
        gps_lon=139.6380,
        creator="一太郎 2024",
        producer="JustSystems PDF Driver 6.0",
        timezone_offset="+09:00",
        locale_hint="ja_JP",
    ),
    # --- South Korea ---
    DeviceMask(
        "kr-galaxy-zfold",
        "Samsung Galaxy Z Fold5 (South Korea)",
        "phone",
        "KR",
        "South Korea",
        "Seoul",
        "samsung",
        "SM-F946N",
        "F946NKSU2BWKK",
        gps_lat=37.5665,
        gps_lon=126.9780,
        creator="Samsung Notes",
        producer="Android 14; SM-F946N",
        timezone_offset="+09:00",
        locale_hint="ko_KR",
    ),
    DeviceMask(
        "kr-galaxy-s23",
        "Samsung Galaxy S23 (South Korea)",
        "phone",
        "KR",
        "South Korea",
        "Busan",
        "samsung",
        "SM-S911N",
        "S911NKSU5CXB1",
        gps_lat=35.1796,
        gps_lon=129.0756,
        creator="Microsoft 365",
        producer="Android 14; SM-S911N",
        timezone_offset="+09:00",
        locale_hint="ko_KR",
    ),
    DeviceMask(
        "kr-lg-gram",
        "LG gram / Hancom (South Korea)",
        "computer",
        "KR",
        "South Korea",
        "Incheon",
        "LG Electronics",
        "16Z90R-G.AA7BK",
        "한컴오피스 2024",
        gps_lat=37.4563,
        gps_lon=126.7052,
        creator="한글 2024",
        producer="Hancom PDF 12.0",
        timezone_offset="+09:00",
        locale_hint="ko_KR",
    ),
    # --- North Korea (plausible / stylized regional masks) ---
    DeviceMask(
        "kp-arnon",
        "Arirang / regional Android tablet (DPRK)",
        "tablet",
        "KP",
        "North Korea",
        "Pyongyang",
        "Arirang",
        "Arirang 171",
        "Red Star OS Camera 4.0",
        gps_lat=39.0392,
        gps_lon=125.7625,
        creator="Samjiyon Document",
        producer="Red Star OS 4.0 PDF",
        timezone_offset="+09:00",
        locale_hint="ko_KP",
    ),
    DeviceMask(
        "kp-samjiyon",
        "Samjiyon tablet (DPRK)",
        "tablet",
        "KP",
        "North Korea",
        "Pyongyang",
        "Samjiyon",
        "Samjiyon Tab 8",
        "Samjiyon 3.0",
        gps_lat=39.0194,
        gps_lon=125.7381,
        creator="Samjiyon Office",
        producer="Red Star PDF Engine 3.5",
        timezone_offset="+09:00",
        locale_hint="ko_KP",
    ),
    DeviceMask(
        "kp-pc",
        "Red Star OS workstation (DPRK)",
        "computer",
        "KP",
        "North Korea",
        "Pyongyang",
        "Moranbong",
        "PC-1711",
        "Red Star OS 4.0",
        gps_lat=39.0335,
        gps_lon=125.7540,
        creator="Naenara Office",
        producer="Red Star PDF 4.0",
        timezone_offset="+09:00",
        locale_hint="ko_KP",
    ),
    # --- Vietnam ---
    DeviceMask(
        "vn-oppo",
        "OPPO Find X6 Pro (Vietnam)",
        "phone",
        "VN",
        "Vietnam",
        "Ho Chi Minh City",
        "OPPO",
        "PGEM10",
        "ColorOS Camera 14.0",
        gps_lat=10.8231,
        gps_lon=106.6297,
        creator="OPPO Browser",
        producer="ColorOS 14; PGEM10",
        timezone_offset="+07:00",
        locale_hint="vi_VN",
    ),
    DeviceMask(
        "vn-vsmart",
        "Vsmart Active 3 (Vietnam)",
        "phone",
        "VN",
        "Vietnam",
        "Hanoi",
        "Vsmart",
        "Vsmart Active 3",
        "VOS 3.0",
        gps_lat=21.0285,
        gps_lon=105.8542,
        creator="Google Docs",
        producer="Android 11; Vsmart Active 3",
        timezone_offset="+07:00",
        locale_hint="vi_VN",
    ),
    DeviceMask(
        "vn-asus",
        "ASUS Vivobook / LibreOffice (Vietnam)",
        "computer",
        "VN",
        "Vietnam",
        "Da Nang",
        "ASUSTeK COMPUTER INC.",
        "Vivobook_ASUSLaptop X1504ZA",
        "LibreOffice 7.6",
        gps_lat=16.0544,
        gps_lon=108.2022,
        creator="Writer",
        producer="LibreOffice 7.6.4.1 (X86_64; Windows)",
        timezone_offset="+07:00",
        locale_hint="vi_VN",
    ),
    # --- Portugal / Brazil (Portuguese) ---
    DeviceMask(
        "pt-iphone",
        "Apple iPhone 12 (Portugal)",
        "phone",
        "PT",
        "Portugal",
        "Lisbon",
        "Apple",
        "iPhone 12",
        "16.6",
        gps_lat=38.7223,
        gps_lon=-9.1393,
        creator="Fotos",
        producer="iOS 16.6",
        timezone_offset="+00:00",
        locale_hint="pt_PT",
    ),
    DeviceMask(
        "br-moto",
        "Motorola Edge 40 (Brazil)",
        "phone",
        "BR",
        "Brazil",
        "São Paulo",
        "motorola",
        "motorola edge 40",
        "XT2303-2_HILOS_14_U1USS34.73-20-1",
        gps_lat=-23.5505,
        gps_lon=-46.6333,
        creator="Google Drive",
        producer="Android 14; motorola edge 40",
        timezone_offset="-03:00",
        locale_hint="pt_BR",
    ),
    DeviceMask(
        "br-canon",
        "Canon EOS Rebel T8i (Brazil)",
        "camera",
        "BR",
        "Brazil",
        "Rio de Janeiro",
        "Canon",
        "Canon EOS Rebel T8i",
        "Firmware Version 1.0.1",
        "Canon",
        "EF-S18-55mm f/4-5.6 IS STM",
        -22.9068,
        -43.1729,
        creator="Canon Digital Photo Professional",
        producer="Canon EOS Rebel T8i",
        timezone_offset="-03:00",
        locale_hint="pt_BR",
    ),
    # --- More global variety ---
    DeviceMask(
        "in-oneplus",
        "OnePlus 12 (India)",
        "phone",
        "IN",
        "India",
        "Mumbai",
        "OnePlus",
        "CPH2573",
        "OxygenOS 14.0",
        gps_lat=19.0760,
        gps_lon=72.8777,
        creator="OnePlus Notes",
        producer="OxygenOS 14.0; CPH2573",
        timezone_offset="+05:30",
        locale_hint="en_IN",
    ),
    DeviceMask(
        "ae-iphone",
        "Apple iPhone 15 Pro (UAE)",
        "phone",
        "AE",
        "United Arab Emirates",
        "Dubai",
        "Apple",
        "iPhone 15 Pro",
        "17.2",
        gps_lat=25.2048,
        gps_lon=55.2708,
        creator="Files",
        producer="iOS 17.2",
        timezone_offset="+04:00",
        locale_hint="ar_AE",
    ),
    DeviceMask(
        "au-pixel",
        "Google Pixel 7a (Australia)",
        "phone",
        "AU",
        "Australia",
        "Sydney",
        "Google",
        "Pixel 7a",
        "HDR+ 1.0.640113802z",
        gps_lat=-33.8688,
        gps_lon=151.2093,
        creator="Google Drive",
        producer="Android 14",
        timezone_offset="+11:00",
        locale_hint="en_AU",
    ),
    DeviceMask(
        "mx-samsung",
        "Samsung Galaxy A54 (Mexico)",
        "phone",
        "MX",
        "Mexico",
        "Mexico City",
        "samsung",
        "SM-A546E",
        "A546EXXS8CXA1",
        gps_lat=19.4326,
        gps_lon=-99.1332,
        creator="Microsoft Word",
        producer="Android 14; SM-A546E",
        timezone_offset="-06:00",
        locale_hint="es_MX",
    ),
    DeviceMask(
        "za-huawei",
        "Huawei nova 11 (South Africa)",
        "phone",
        "ZA",
        "South Africa",
        "Cape Town",
        "HUAWEI",
        "FOA-LX9",
        "Camera 12.0.0.450",
        gps_lat=-33.9249,
        gps_lon=18.4241,
        creator="Huawei Docs",
        producer="EMUI 13.1.0",
        timezone_offset="+02:00",
        locale_hint="en_ZA",
    ),
    DeviceMask(
        "it-fujifilm",
        "Fujifilm X100VI (Italy)",
        "camera",
        "IT",
        "Italy",
        "Rome",
        "FUJIFILM",
        "X100VI",
        "X100VI Ver1.10",
        "FUJIFILM",
        "FUJINON 23mm F2",
        41.9028,
        12.4964,
        creator="Capture One 16",
        producer="FUJIFILM X100VI",
        timezone_offset="+01:00",
        locale_hint="it_IT",
    ),
    DeviceMask(
        "es-iphone",
        "Apple iPhone SE (Spain)",
        "phone",
        "ES",
        "Spain",
        "Madrid",
        "Apple",
        "iPhone SE (3rd generation)",
        "17.1",
        gps_lat=40.4168,
        gps_lon=-3.7038,
        creator="Pages",
        producer="iOS 17.1",
        timezone_offset="+01:00",
        locale_hint="es_ES",
    ),
    DeviceMask(
        "ca-ipad",
        "Apple iPad Pro (Canada)",
        "tablet",
        "CA",
        "Canada",
        "Toronto",
        "Apple",
        "iPad Pro (12.9-inch) (6th generation)",
        "17.2",
        gps_lat=43.6532,
        gps_lon=-79.3832,
        creator="GoodNotes 6",
        producer="iPadOS 17.2",
        timezone_offset="-05:00",
        locale_hint="en_CA",
    ),
    DeviceMask(
        "nl-dji",
        "DJI Mini 4 Pro (Netherlands)",
        "drone",
        "NL",
        "Netherlands",
        "Amsterdam",
        "DJI",
        "FC8482",
        "10.01.06.04",
        gps_lat=52.3676,
        gps_lon=4.9041,
        creator="DJI Fly",
        producer="DJI Mini 4 Pro",
        timezone_offset="+01:00",
        locale_hint="nl_NL",
    ),
    DeviceMask(
        "se-sony",
        "Sony α6700 (Sweden)",
        "camera",
        "SE",
        "Sweden",
        "Stockholm",
        "SONY",
        "ILCE-6700",
        "ILCE-6700 v2.00",
        "SONY",
        "E 18-135mm F3.5-5.6 OSS",
        59.3293,
        18.0686,
        creator="Imaging Edge Desktop",
        producer="SONY ILCE-6700",
        timezone_offset="+01:00",
        locale_hint="sv_SE",
    ),
    DeviceMask(
        "pl-xiaomi",
        "Xiaomi Redmi Note 13 (Poland)",
        "phone",
        "PL",
        "Poland",
        "Warsaw",
        "Xiaomi",
        "23129RA5FL",
        "MIUI Camera 5.3",
        gps_lat=52.2297,
        gps_lon=21.0122,
        creator="Microsoft Edge",
        producer="Android 13; 23129RA5FL",
        timezone_offset="+01:00",
        locale_hint="pl_PL",
    ),
    DeviceMask(
        "tr-samsung",
        "Samsung Galaxy A35 (Turkey)",
        "phone",
        "TR",
        "Turkey",
        "Istanbul",
        "samsung",
        "SM-A356E",
        "A356EXXS2AXA1",
        gps_lat=41.0082,
        gps_lon=28.9784,
        creator="Adobe Scan",
        producer="Android 14; SM-A356E",
        timezone_offset="+03:00",
        locale_hint="tr_TR",
    ),
    DeviceMask(
        "sg-iphone",
        "Apple iPhone 14 Pro (Singapore)",
        "phone",
        "SG",
        "Singapore",
        "Singapore",
        "Apple",
        "iPhone 14 Pro",
        "17.2.1",
        gps_lat=1.3521,
        gps_lon=103.8198,
        creator="Files",
        producer="iOS 17.2.1",
        timezone_offset="+08:00",
        locale_hint="en_SG",
    ),
    DeviceMask(
        "th-oppo",
        "OPPO Reno11 (Thailand)",
        "phone",
        "TH",
        "Thailand",
        "Bangkok",
        "OPPO",
        "CPH2599",
        "ColorOS Camera 14.0",
        gps_lat=13.7563,
        gps_lon=100.5018,
        creator="OPPO Share",
        producer="ColorOS 14; CPH2599",
        timezone_offset="+07:00",
        locale_hint="th_TH",
    ),
    DeviceMask(
        "eg-samsung",
        "Samsung Galaxy A15 (Egypt)",
        "phone",
        "EG",
        "Egypt",
        "Cairo",
        "samsung",
        "SM-A155F",
        "A155FXXU2AXA1",
        gps_lat=30.0444,
        gps_lon=31.2357,
        creator="Microsoft Print to PDF",
        producer="Android 14; SM-A155F",
        timezone_offset="+02:00",
        locale_hint="ar_EG",
    ),
    DeviceMask(
        "ar-motorola",
        "Motorola G84 (Argentina)",
        "phone",
        "AR",
        "Argentina",
        "Buenos Aires",
        "motorola",
        "motorola edge 40 neo",
        "XT2307-1",
        gps_lat=-34.6037,
        gps_lon=-58.3816,
        creator="Google Chrome",
        producer="Android 14; motorola edge 40 neo",
        timezone_offset="-03:00",
        locale_hint="es_AR",
    ),
    DeviceMask(
        "nz-iphone",
        "Apple iPhone 13 mini (New Zealand)",
        "phone",
        "NZ",
        "New Zealand",
        "Auckland",
        "Apple",
        "iPhone 13 mini",
        "16.7",
        gps_lat=-36.8509,
        gps_lon=174.7645,
        creator="Photos",
        producer="iOS 16.7",
        timezone_offset="+13:00",
        locale_hint="en_NZ",
    ),
    DeviceMask(
        "ch-leica",
        "Leica SL3 (Switzerland)",
        "camera",
        "CH",
        "Switzerland",
        "Zurich",
        "LEICA CAMERA AG",
        "LEICA SL3",
        "1.1.0",
        "LEICA",
        "VARIO-ELMARIT-SL 1:2.8/24-70 ASPH.",
        47.3769,
        8.5417,
        creator="Adobe Lightroom Classic",
        producer="Adobe Photoshop Lightroom Classic 13.0 (Macintosh)",
        timezone_offset="+01:00",
        locale_hint="de_CH",
    ),
    DeviceMask(
        "us-epson-scan",
        "Epson Perfection scanner (USA)",
        "scanner",
        "US",
        "United States",
        "Chicago",
        "EPSON",
        "Perfection V600",
        "Epson Scan 2 6.7.6.0",
        gps_lat=41.8781,
        gps_lon=-87.6298,
        creator="Epson Scan 2",
        producer="EPSON Perfection V600",
        timezone_offset="-06:00",
        locale_hint="en_US",
    ),
    DeviceMask(
        "jp-ricoh-theta",
        "RICOH THETA X (Japan)",
        "camera",
        "JP",
        "Japan",
        "Sapporo",
        "RICOH",
        "RICOH THETA X",
        "2.51.0",
        gps_lat=43.0618,
        gps_lon=141.3545,
        creator="THETA+",
        producer="RICOH THETA X",
        timezone_offset="+09:00",
        locale_hint="ja_JP",
    ),
    DeviceMask(
        "kr-drone",
        "DJI Air 3 (South Korea)",
        "drone",
        "KR",
        "South Korea",
        "Jeju",
        "DJI",
        "FC8282",
        "01.00.0600",
        gps_lat=33.4996,
        gps_lon=126.5312,
        creator="DJI Fly",
        producer="DJI Air 3",
        timezone_offset="+09:00",
        locale_hint="ko_KR",
    ),
    DeviceMask(
        "cn-dji-mavic",
        "DJI Mavic 3 Pro (China)",
        "drone",
        "CN",
        "China",
        "Hangzhou",
        "DJI",
        "FC3582",
        "10.00.07.02",
        gps_lat=30.2741,
        gps_lon=120.1551,
        creator="DJI Fly",
        producer="DJI Mavic 3 Pro",
        timezone_offset="+08:00",
        locale_hint="zh_CN",
    ),
    DeviceMask(
        "de-brother-scan",
        "Brother scanner / Windows (Germany)",
        "scanner",
        "DE",
        "Germany",
        "Hamburg",
        "Brother",
        "ADS-4700W",
        "Brother iPrint&Scan 10.2",
        gps_lat=53.5511,
        gps_lon=9.9937,
        creator="Brother iPrint&Scan",
        producer="Brother ADS-4700W",
        timezone_offset="+01:00",
        locale_hint="de_DE",
    ),
    DeviceMask(
        "fr-ipad",
        "Apple iPad Air (France)",
        "tablet",
        "FR",
        "France",
        "Bordeaux",
        "Apple",
        "iPad Air (5th generation)",
        "17.1",
        gps_lat=44.8378,
        gps_lon=-0.5792,
        creator="Notability",
        producer="iPadOS 17.1",
        timezone_offset="+01:00",
        locale_hint="fr_FR",
    ),
    DeviceMask(
        "ru-canon",
        "Canon PowerShot G7 X (Russia)",
        "camera",
        "RU",
        "Russia",
        "Kazan",
        "Canon",
        "Canon PowerShot G7 X Mark III",
        "Firmware Version 1.1.0",
        "Canon",
        "6.1-24.4 mm",
        55.8304,
        49.0661,
        creator="ImageBrowser EX",
        producer="Canon PowerShot G7 X Mark III",
        timezone_offset="+03:00",
        locale_hint="ru_RU",
    ),
    DeviceMask(
        "vn-canon",
        "Canon EOS 90D (Vietnam)",
        "camera",
        "VN",
        "Vietnam",
        "Hue",
        "Canon",
        "Canon EOS 90D",
        "Firmware Version 1.1.1",
        "Canon",
        "EF-S18-135mm f/3.5-5.6 IS USM",
        16.4637,
        107.5909,
        creator="Digital Photo Professional",
        producer="Canon EOS 90D",
        timezone_offset="+07:00",
        locale_hint="vi_VN",
    ),
    DeviceMask(
        "us-surface",
        "Microsoft Surface Pro (USA)",
        "tablet",
        "US",
        "United States",
        "Redmond",
        "Microsoft Corporation",
        "Surface Pro 9",
        "Windows 11 Pro 22631",
        gps_lat=47.6740,
        gps_lon=-122.1215,
        creator="Microsoft Print to PDF",
        producer="Microsoft: Print To PDF",
        timezone_offset="-08:00",
        locale_hint="en_US",
    ),
    DeviceMask(
        "jp-toshiba-scan",
        "Canon imageFORMULA scanner (Japan)",
        "scanner",
        "JP",
        "Japan",
        "Nagoya",
        "Canon",
        "DR-C240",
        "CaptureOnTouch 4.0",
        gps_lat=35.1815,
        gps_lon=136.9066,
        creator="CaptureOnTouch",
        producer="Canon DR-C240",
        timezone_offset="+09:00",
        locale_hint="ja_JP",
    ),
]


# ---------------------------------------------------------------------------
# Catalog helpers
# ---------------------------------------------------------------------------

CATEGORIES = ("phone", "camera", "tablet", "computer", "scanner", "drone")

REGION_LABELS: dict[str, str] = {
    "US": "United States",
    "GB": "United Kingdom",
    "DE": "Germany",
    "FR": "France",
    "RU": "Russia",
    "CN": "China",
    "JP": "Japan",
    "KR": "South Korea",
    "KP": "North Korea",
    "VN": "Vietnam",
    "PT": "Portugal",
    "BR": "Brazil",
    "IN": "India",
    "AE": "United Arab Emirates",
    "AU": "Australia",
    "MX": "Mexico",
    "ZA": "South Africa",
    "IT": "Italy",
    "ES": "Spain",
    "CA": "Canada",
    "NL": "Netherlands",
    "SE": "Sweden",
    "PL": "Poland",
    "TR": "Turkey",
    "SG": "Singapore",
    "TH": "Thailand",
    "EG": "Egypt",
    "AR": "Argentina",
    "NZ": "New Zealand",
    "CH": "Switzerland",
}


def all_masks() -> list[DeviceMask]:
    return list(MASKS)


def mask_by_id(mask_id: str) -> DeviceMask | None:
    for m in MASKS:
        if m.id == mask_id:
            return m
    return None


def filter_masks(
    *,
    category: str | None = None,
    region: str | None = None,
) -> list[DeviceMask]:
    out = MASKS
    if category and category != "all":
        out = [m for m in out if m.category == category]
    if region and region != "all":
        out = [m for m in out if m.region == region]
    return list(out)


def regions_present() -> list[str]:
    return sorted({m.region for m in MASKS}, key=lambda r: REGION_LABELS.get(r, r))


def pick_random_mask(
    *,
    category: str | None = None,
    region: str | None = None,
    rng: random.Random | None = None,
) -> DeviceMask:
    rng = rng or random.Random()
    pool = filter_masks(category=category, region=region)
    if not pool:
        pool = list(MASKS)
    return rng.choice(pool)


# ---------------------------------------------------------------------------
# Scramble generation
# ---------------------------------------------------------------------------


@dataclass
class ScrambleOptions:
    """Controls how much noise is added around a base mask."""

    randomize_gps: bool = True
    gps_jitter_km: float = 3.0
    randomize_datetime: bool = True
    days_back_min: int = 1
    days_back_max: int = 400
    randomize_exposure: bool = True
    set_artist: bool = False
    artist_name: str = ""
    user_comment: str = ""
    pdf_title: str = ""
    pdf_subject: str = ""
    pdf_keywords: str = ""
    pdf_author: str = ""


@dataclass
class ScramblePayload:
    """Ready-to-apply EXIF quick fields + PDF metadata from a mask."""

    mask: DeviceMask
    exif_fields: dict[str, str] = field(default_factory=dict)
    pdf_fields: dict[str, str] = field(default_factory=dict)
    summary: str = ""


def _jitter_gps(lat: float, lon: float, km: float, rng: random.Random) -> tuple[float, float]:
    """Rough km jitter (not geodesic-perfect; fine for spoofing)."""
    if km <= 0:
        return lat, lon
    # ~111 km per degree latitude
    dlat = rng.uniform(-km, km) / 111.0
    # longitude shrinks by cos(lat)
    import math

    cos_lat = max(0.2, abs(math.cos(math.radians(lat))))
    dlon = rng.uniform(-km, km) / (111.0 * cos_lat)
    nlat = max(-90.0, min(90.0, lat + dlat))
    nlon = ((lon + dlon + 180.0) % 360.0) - 180.0
    return nlat, nlon


def _format_exif_datetime(dt: datetime) -> str:
    return dt.strftime("%Y:%m:%d %H:%M:%S")


def _format_pdf_datetime(dt: datetime, tz_offset: str) -> str:
    # PDF: D:YYYYMMDDHHmmSS+HH'mm'
    raw = dt.strftime("%Y%m%d%H%M%S")
    off = tz_offset.strip()
    if off.startswith(("+", "-")) and ":" in off:
        sign = off[0]
        hh, mm = off[1:].split(":", 1)
        return f"D:{raw}{sign}{hh}'{mm}'"
    if off.startswith(("+", "-")) and len(off) >= 3:
        return f"D:{raw}{off}"
    return f"D:{raw}"


def _fake_exposure(rng: random.Random) -> dict[str, str]:
    shutters = ["1/30", "1/60", "1/125", "1/250", "1/500", "1/1000", "1/2000"]
    apertures = ["1.4", "1.8", "2.0", "2.8", "4.0", "5.6", "8.0"]
    isos = ["100", "200", "400", "800", "1600", "3200"]
    focals = ["24", "28", "35", "50", "70", "85", "105", "135", "200"]
    return {
        "ExposureTime": rng.choice(shutters),
        "FNumber": rng.choice(apertures),
        "ISOSpeedRatings": rng.choice(isos),
        "FocalLength": rng.choice(focals),
    }


def build_scramble(
    mask: DeviceMask,
    options: ScrambleOptions | None = None,
    *,
    rng: random.Random | None = None,
) -> ScramblePayload:
    """Build EXIF + PDF field dicts that impersonate the given device mask."""
    options = options or ScrambleOptions()
    rng = rng or random.Random()

    # Timestamps
    if options.randomize_datetime:
        days = rng.randint(options.days_back_min, options.days_back_max)
        seconds = rng.randint(0, 86399)
        dt = datetime.now() - timedelta(days=days, seconds=seconds)
    else:
        dt = datetime.now()

    lat, lon = mask.gps_lat, mask.gps_lon
    if options.randomize_gps and (lat != 0.0 or lon != 0.0):
        lat, lon = _jitter_gps(lat, lon, options.gps_jitter_km, rng)

    lat_ref = "N" if lat >= 0 else "S"
    lon_ref = "E" if lon >= 0 else "W"
    abs_lat = abs(lat)
    abs_lon = abs(lon)

    stamp = _format_exif_datetime(dt)
    software = mask.software
    # Light software version noise so two scrambles aren't identical
    if options.randomize_datetime and rng.random() < 0.35:
        software = f"{software}.{rng.randint(0, 9)}"

    exif: dict[str, str] = {
        "Make": mask.make,
        "Model": mask.model,
        "Software": software,
        "DateTime": stamp,
        "DateTimeOriginal": stamp,
        "DateTimeDigitized": stamp,
        "GPSLatitude": f"{abs_lat:.6f}",
        "GPSLatitudeRef": lat_ref,
        "GPSLongitude": f"{abs_lon:.6f}",
        "GPSLongitudeRef": lon_ref,
        "GPSAltitude": f"{rng.randint(5, 420)}",
        "GPSAltitudeRef": "0",
    }

    if mask.lens_model:
        exif["LensModel"] = mask.lens_model
    if mask.lens_make:
        # LensMake lives outside quick fields sometimes; put into UserComment fallback
        pass

    if options.randomize_exposure and mask.category in ("phone", "camera", "drone", "tablet"):
        exif.update(_fake_exposure(rng))

    if options.set_artist and options.artist_name.strip():
        exif["Artist"] = options.artist_name.strip()
        exif["Copyright"] = f"© {dt.year} {options.artist_name.strip()}"
    elif mask.artist:
        exif["Artist"] = mask.artist

    comment_parts = [
        f"Captured in {mask.city}, {mask.country}",
        f"Device mask: {mask.label}",
    ]
    if options.user_comment.strip():
        comment_parts.insert(0, options.user_comment.strip())
    exif["UserComment"] = " · ".join(comment_parts)
    exif["ImageDescription"] = f"{mask.city} · {mask.model}"

    # PDF document metadata
    author = options.pdf_author.strip() or options.artist_name.strip() or mask.make
    title = options.pdf_title.strip() or f"Document · {mask.city}"
    subject = options.pdf_subject.strip() or f"Authored on {mask.label}"
    keywords = options.pdf_keywords.strip() or f"{mask.region}, {mask.category}, {mask.model}"

    pdf_dt = _format_pdf_datetime(dt, mask.timezone_offset)
    pdf: dict[str, str] = {
        "Title": title,
        "Author": author,
        "Subject": subject,
        "Keywords": keywords,
        "Creator": mask.creator or mask.software,
        "Producer": mask.producer or mask.software,
        "CreationDate": pdf_dt,
        "ModDate": pdf_dt,
        "Trapped": "False",
    }

    summary = (
        f"{mask.label}  ·  {mask.city}, {mask.country}  ·  "
        f"GPS {lat_ref}{abs_lat:.4f} {lon_ref}{abs_lon:.4f}  ·  {stamp}"
    )

    return ScramblePayload(mask=mask, exif_fields=exif, pdf_fields=pdf, summary=summary)


def random_scramble(
    *,
    category: str | None = None,
    region: str | None = None,
    options: ScrambleOptions | None = None,
    seed: int | None = None,
) -> ScramblePayload:
    rng = random.Random(seed if seed is not None else uuid.uuid4().int)
    mask = pick_random_mask(category=category, region=region, rng=rng)
    return build_scramble(mask, options, rng=rng)
