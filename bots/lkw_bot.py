#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LKW Bot Controller
Version 3.2
"""

import time
import threading
import logging
import cv2
import numpy as np
from PIL import Image
import pytesseract
import os
import re
import json
from datetime import datetime, timedelta
import pytz

from .bot_base import BotBase

logger = logging.getLogger(__name__)


class LKWBotController(BotBase):
    """LKW-Bot mit Auto-Reconnect"""
    
    # Koordinaten
    COORDS_NEW = {
        'esc': (680, 70),
        'share': (564, 1115),
        'share_confirm1': (300, 450),
        'share_confirm2': (400, 750),
    }
    
    COORDS_ALLIANCE = {
        'esc': (680, 70),
        'share': (564, 1115),
        'share_confirm1': (300, 700),
        'share_confirm2': (400, 750),
    }
    
    # OCR Boxen
    STAERKE_BOX = (200, 950, 300, 1000)
    SERVER_BOX = (168, 881, 220, 915)
    
    # Dateien
    TEMPLATE_FILE = 'rentier_template.png'
    STAERKEN_FILE = 'lkw_staerken.txt'
    STATS_FILE = 'truck_stats.json'
    
    def __init__(self, ssh_config):
        super().__init__("LKW-Bot", ssh_config)
        
        self.thread = None
        self.status = "Gestoppt"
        self.last_action = ""
        self.lock = threading.Lock()
        self.current_user = None
        
        # Timer
        self.use_timer = False
        self.timer_duration_minutes = 60
        self.timer_start_time = None
        self.timer_thread = None
        
        # Einstellungen
        self.use_limit = False
        self.strength_limit = 60.0
        self.use_server_filter = False
        self.server_number = "49"
        self.reset_interval = 15
        self.share_mode = "world"
        
        # Statistiken
        self.trucks_processed = 0
        self.trucks_shared = 0
        self.trucks_skipped = 0
        
        self.last_success_time = time.time()
        self.maintenance_mode = False
        self.no_truck_threshold = 300
    
    def ocr_staerke(self):
        """Liest Stärke aus"""
        try:
            img = Image.open('info.png')
            staerke_img = img.crop(self.STAERKE_BOX)
            configs = ['--psm 7', '--psm 8', '--psm 6']
            for config in configs:
                wert = pytesseract.image_to_string(staerke_img, lang='eng', config=config).strip()
                if wert and ('m' in wert.lower() or 'M' in wert):
                    return wert
            return ""
        except Exception as e:
            logger.error(f"{self.bot_name}: OCR-Fehler: {e}")
            return ""
    
    def ocr_server(self):
        """Liest Server aus"""
        try:
            img = Image.open('info.png')
            server_img = img.crop(self.SERVER_BOX)
            server_text = pytesseract.image_to_string(server_img, lang='eng').strip()
            s_txt = re.sub(r'[^0-9]', '', server_text)
            return s_txt if s_txt else "Unknown"
        except Exception as e:
            logger.error(f"{self.bot_name}: Server-OCR-Fehler: {e}")
            return "Unknown"
    
    def ist_server_passend(self):
        """Prüft ob Server passt"""
        try:
            if not os.path.exists('info.png'):
                return False
            img = Image.open('info.png')
            server_img = img.crop(self.SERVER_BOX)
            server_text = pytesseract.image_to_string(server_img, lang='eng').strip()
            
            cleaned_text = server_text.replace('O', '0').replace('o', '0')
            found_numbers = re.findall(r'\d+', cleaned_text)
            target = str(self.server_number)
            
            return target in found_numbers
        except Exception as e:
            logger.error(f"{self.bot_name}: Server-Check-Fehler: {e}")
            return False
    
    def rentier_lkw_finden(self):
        """Findet LKW per Template Matching"""
        try:
            screenshot = cv2.imread('screen.png')
            template = cv2.imread(self.TEMPLATE_FILE)
            if screenshot is None or template is None:
                return None
            result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
            locations = np.where(result >= 0.40)
            matches = [(int(pt[0]), int(pt[1])) for pt in zip(*locations[::-1])]
            return matches if matches else None
        except Exception as e:
            logger.error(f"{self.bot_name}: Template-Matching-Fehler: {e}")
            return None
    
    def staerke_float_wert(self, staerke_text):
        """Konvertiert Stärke zu Float"""
        match = re.search(r"([\d\.,]+)\s*[mM]", staerke_text)
        if match:
            try:
                zahl_str = match.group(1).replace(',', '.')
                zahl = float(zahl_str)
                if zahl >= 100 and '.' not in match.group(1) and ',' not in match.group(1):
                    zahl = zahl / 10
                return zahl
            except ValueError:
                return None
        return None
    
    def load_staerken(self):
        """Lädt geteilte Stärken"""
        if os.path.exists(self.STAERKEN_FILE):
            try:
                with open(self.STAERKEN_FILE, 'r', encoding="utf-8") as f:
                    return f.read().splitlines()
            except Exception as e:
                logger.error(f"{self.bot_name}: Fehler beim Laden: {e}")
                return []
        return []
    
    def save_staerke(self, staerke):
        """Speichert Stärke"""
        try:
            with open(self.STAERKEN_FILE, "a", encoding="utf-8") as f:
                f.write(staerke + "\n")
        except Exception as e:
            logger.error(f"{self.bot_name}: Save-Fehler: {e}")
    
    def reset_staerken(self):
        """Resettet Stärken-Liste"""
        try:
            with open(self.STAERKEN_FILE, "w", encoding="utf-8") as f:
                f.write("")
            logger.info(f"{self.bot_name}: Stärken zurückgesetzt")
        except Exception as e:
            logger.error(f"{self.bot_name}: Reset-Fehler: {e}")
    
    def bot_loop(self):
        """Haupt-Loop"""
        logger.info(f"{self.bot_name}: Bot-Schleife gestartet")
        
        if not self.setup_ssh_tunnel():
            self.status = "Fehler: SSH-Tunnel"
            self.running = False
            return
        
        # Keepalive starten
        self.start_keepalive()
        
        # Reset-Thread
        reset_thread = threading.Thread(target=self._reset_timer, daemon=True)
        reset_thread.start()
        
        while self.running:
            if self.paused:
                self.status = "Pausiert"
                time.sleep(1)
                continue
            
            try:
                self.status = "Läuft - Suche LKWs..."
                
                if not self.make_screenshot('screen.png'):
                    self.last_action = "Screenshot fehlgeschlagen"
                    time.sleep(5)
                    continue
                
                treffer = self.rentier_lkw_finden()
                
                if not treffer:
                    self.click(self.COORDS_NEW['esc'][0], self.COORDS_NEW['esc'][1])
                    self.trucks_processed += 1
                    continue
                
                # LKW gefunden - verarbeiten
                lx = treffer[0][0] + 5
                ly = treffer[0][1] + 5
                self.click(lx, ly)
                
                if not self.make_screenshot('info.png'):
                    continue
                
                # Server prüfen
                if self.use_server_filter and not self.ist_server_passend():
                    self.click(self.COORDS_NEW['esc'][0], self.COORDS_NEW['esc'][1])
                    self.trucks_skipped += 1
                    self.trucks_processed += 1
                    continue
                
                # Stärke prüfen
                staerke = self.ocr_staerke()
                wert = self.staerke_float_wert(staerke)
                
                if wert and self.use_limit and wert > self.strength_limit:
                    self.click(self.COORDS_NEW['esc'][0], self.COORDS_NEW['esc'][1])
                    self.trucks_skipped += 1
                    self.trucks_processed += 1
                    continue
                
                if wert is None or staerke in self.load_staerken():
                    self.click(self.COORDS_NEW['esc'][0], self.COORDS_NEW['esc'][1])
                    self.trucks_skipped += 1
                    self.trucks_processed += 1
                    continue
                
                # LKW teilen
                self.save_staerke(staerke)
                coords = self.COORDS_ALLIANCE if self.share_mode == "alliance" else self.COORDS_NEW
                
                self.click(coords['share'][0], coords['share'][1])
                self.click(coords['share_confirm1'][0], coords['share_confirm1'][1])
                self.click(coords['share_confirm2'][0], coords['share_confirm2'][1])
                self.click(coords['esc'][0], coords['esc'][1])
                
                self.trucks_shared += 1
                self.trucks_processed += 1
                self.last_action = f"LKW geteilt! ({self.trucks_shared} gesamt)"
                self.last_success_time = time.time()
                
            except Exception as e:
                logger.error(f"{self.bot_name}: Fehler: {e}")
                self.consecutive_errors += 1
                time.sleep(5)
        
        self.close_ssh_tunnel()
        self.stop_keepalive()
        self.status = "Gestoppt"
        logger.info(f"{self.bot_name}: Beendet")
    
    def _reset_timer(self):
        """Reset-Timer Thread"""
        while self.running:
            time.sleep(self.reset_interval * 60)
            if self.running:
                self.reset_staerken()
    
    def start(self, username=None):
        """Startet Bot"""
        if not self.running:
            self.running = True
            self.paused = False
            self.consecutive_errors = 0
            self.current_user = username
            self.thread = threading.Thread(target=self.bot_loop, daemon=True)
            self.thread.start()
            logger.info(f"{self.bot_name}: Gestartet")
    
    def pause(self):
        """Pausiert Bot"""
        if self.running:
            self.paused = not self.paused
    
    def stop(self):
        """Stoppt Bot"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=10)
        logger.info(f"{self.bot_name}: Gestoppt")
