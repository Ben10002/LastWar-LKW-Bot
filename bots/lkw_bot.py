#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LKW Bot Controller - Verbessert
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
import subprocess

from .bot_base import BotBase

logger = logging.getLogger(__name__)


class LKWBotController(BotBase):
    """LKW-Bot mit verbessertem Screenshot-Handling"""
    
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
        
        # Screenshot retry config
        self.screenshot_retry_delay = 1  # Sekunden zwischen Retries
        self.screenshot_max_wait = 20  # Maximale Wartezeit für Screenshot
    
    def make_screenshot_robust(self, filename='screen.png'):
        """
        Robustes Screenshot-Handling mit mehreren Strategien
        """
        max_attempts = 5
        
        for attempt in range(max_attempts):
            try:
                local_port = self.ssh_config.get('local_adb_port')
                if not local_port:
                    logger.error(f"{self.bot_name}: ADB-Port nicht konfiguriert")
                    return False
                
                adb_device = f'localhost:{local_port}'
                
                # Strategie 1: Normaler Screenshot
                logger.info(f"{self.bot_name}: Screenshot-Versuch {attempt + 1}/{max_attempts}")
                
                # Lösche alte Datei
                if os.path.exists(filename):
                    try:
                        os.remove(filename)
                    except:
                        pass
                
                # Screenshot auf Device erstellen
                screencap_cmd = ['adb', '-s', adb_device, 'shell', 'screencap', '-p', f'/sdcard/{filename}']
                result_screencap = subprocess.run(
                    screencap_cmd,
                    timeout=self.screenshot_max_wait,
                    capture_output=True
                )
                
                if result_screencap.returncode != 0:
                    logger.warning(f"{self.bot_name}: screencap failed: {result_screencap.stderr}")
                    raise Exception("screencap fehlgeschlagen")
                
                # Kurz warten
                time.sleep(0.5)
                
                # Screenshot pullen
                pull_cmd = ['adb', '-s', adb_device, 'pull', f'/sdcard/{filename}', filename]
                result_pull = subprocess.run(
                    pull_cmd,
                    timeout=self.screenshot_max_wait,
                    capture_output=True
                )
                
                if result_pull.returncode != 0:
                    logger.warning(f"{self.bot_name}: pull failed: {result_pull.stderr}")
                    raise Exception("pull fehlgeschlagen")
                
                # Prüfe ob Datei existiert und valide ist
                if os.path.exists(filename):
                    file_size = os.path.getsize(filename)
                    if file_size > 1000:  # Mindestens 1KB
                        self.consecutive_errors = 0
                        logger.info(f"{self.bot_name}: Screenshot erfolgreich ({file_size} bytes)")
                        return True
                    else:
                        logger.warning(f"{self.bot_name}: Screenshot zu klein ({file_size} bytes)")
                        raise Exception("Screenshot zu klein")
                else:
                    raise Exception("Screenshot-Datei nicht erstellt")
                    
            except subprocess.TimeoutExpired:
                logger.warning(f"{self.bot_name}: Screenshot timeout bei Versuch {attempt + 1}")
                self.consecutive_errors += 1
                
                # Bei 3 Fehlern: SSH reconnect
                if self.consecutive_errors >= 3 and attempt < max_attempts - 1:
                    logger.error(f"{self.bot_name}: 3 Fehler - SSH-Reconnect")
                    self.close_ssh_tunnel()
                    time.sleep(3)
                    if self.setup_ssh_tunnel():
                        self.consecutive_errors = 0
                    time.sleep(self.screenshot_retry_delay)
                    continue
                    
            except Exception as e:
                logger.error(f"{self.bot_name}: Screenshot-Fehler (Versuch {attempt + 1}): {e}")
                self.consecutive_errors += 1
                
                # Bei 3 Fehlern: SSH reconnect
                if self.consecutive_errors >= 3 and attempt < max_attempts - 1:
                    logger.error(f"{self.bot_name}: 3 Fehler - SSH-Reconnect")
                    self.close_ssh_tunnel()
                    time.sleep(3)
                    if self.setup_ssh_tunnel():
                        self.consecutive_errors = 0
                    time.sleep(self.screenshot_retry_delay)
                    continue
            
            # Warte vor nächstem Versuch
            if attempt < max_attempts - 1:
                time.sleep(self.screenshot_retry_delay)
        
        # Kompletter Reset bei zu vielen Fehlern
        if self.consecutive_errors >= self.max_consecutive_errors:
            logger.error(f"{self.bot_name}: {self.max_consecutive_errors} Fehler - KOMPLETTER RESET")
            self.close_ssh_tunnel()
            time.sleep(5)
            self.setup_ssh_tunnel()
            self.consecutive_errors = 0
        
        logger.error(f"{self.bot_name}: Screenshot fehlgeschlagen nach {max_attempts} Versuchen")
        return False
    
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
                self.last_action = "Bot pausiert"
                time.sleep(1)
                continue
            
            if self.maintenance_mode:
                self.status = "Wartungsmodus"
                self.last_action = "Wartungsarbeiten aktiv"
                time.sleep(10)
                continue
            
            try:
                self.status = "Läuft - Suche LKWs..."
                self.last_action = "Erstelle Screenshot..."
                
                # Verwende robustes Screenshot-Handling
                if not self.make_screenshot_robust('screen.png'):
                    self.last_action = "Screenshot fehlgeschlagen - Retry..."
                    time.sleep(3)
                    continue
                
                self.last_action = "Suche LKW-Template..."
                treffer = self.rentier_lkw_finden()
                
                if not treffer:
                    self.last_action = "Kein LKW gefunden - ESC"
                    self.click(self.COORDS_NEW['esc'][0], self.COORDS_NEW['esc'][1])
                    self.trucks_processed += 1
                    time.sleep(1)
                    continue
                
                self.last_action = f"LKW gefunden bei {treffer[0]}"
                logger.info(f"{self.bot_name}: Treffer bei: {treffer[0]}")
                
                lx = treffer[0][0] + 5
                ly = treffer[0][1] + 5
                self.click(lx, ly)
                
                self.last_action = "Hole LKW-Details..."
                if not self.make_screenshot_robust('info.png'):
                    self.last_action = "Info-Screenshot fehlgeschlagen"
                    self.click(self.COORDS_NEW['esc'][0], self.COORDS_NEW['esc'][1])
                    continue
                
                # Server prüfen
                if self.use_server_filter:
                    self.last_action = "Prüfe Server..."
                    if not self.ist_server_passend():
                        self.last_action = f"Falscher Server - Skip"
                        self.click(self.COORDS_NEW['esc'][0], self.COORDS_NEW['esc'][1])
                        self.trucks_skipped += 1
                        self.trucks_processed += 1
                        continue
                
                # Stärke prüfen
                self.last_action = "Lese Stärke..."
                staerke = self.ocr_staerke()
                wert = self.staerke_float_wert(staerke)
                
                if wert and self.use_limit and wert > self.strength_limit:
                    self.last_action = f"Stärke {wert}M > {self.strength_limit}M - Skip"
                    self.click(self.COORDS_NEW['esc'][0], self.COORDS_NEW['esc'][1])
                    self.trucks_skipped += 1
                    self.trucks_processed += 1
                    continue
                
                if wert is None or staerke in self.load_staerken():
                    if wert is None:
                        self.last_action = "Stärke nicht erkannt - Skip"
                    else:
                        self.last_action = f"Stärke {staerke} bereits geteilt - Skip"
                    self.click(self.COORDS_NEW['esc'][0], self.COORDS_NEW['esc'][1])
                    self.trucks_skipped += 1
                    self.trucks_processed += 1
                    continue
                
                # LKW teilen
                self.save_staerke(staerke)
                coords = self.COORDS_ALLIANCE if self.share_mode == "alliance" else self.COORDS_NEW
                mode_text = "Allianz" if self.share_mode == "alliance" else "Welt"
                
                self.last_action = f"Teile {staerke} im {mode_text}chat..."
                logger.info(f"{self.bot_name}: Teile LKW {staerke} im {mode_text}chat")
                
                self.click(coords['share'][0], coords['share'][1])
                self.click(coords['share_confirm1'][0], coords['share_confirm1'][1])
                self.click(coords['share_confirm2'][0], coords['share_confirm2'][1])
                self.click(coords['esc'][0], coords['esc'][1])
                
                self.trucks_shared += 1
                self.trucks_processed += 1
                self.last_action = f"✓ LKW {staerke} geteilt! (Gesamt: {self.trucks_shared})"
                self.last_success_time = time.time()
                
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"{self.bot_name}: Fehler: {e}")
                import traceback
                logger.error(traceback.format_exc())
                self.last_action = f"Fehler: {str(e)[:50]}"
                self.consecutive_errors += 1
                time.sleep(5)
        
        self.close_ssh_tunnel()
        self.stop_keepalive()
        self.status = "Gestoppt"
        self.last_action = "Bot gestoppt"
        logger.info(f"{self.bot_name}: Beendet")
    
    def _reset_timer(self):
        """Reset-Timer Thread"""
        while self.running:
            time.sleep(self.reset_interval * 60)
            if self.running:
                self.reset_staerken()
                self.last_action = f"Stärken-Liste zurückgesetzt ({self.reset_interval} Min)"
    
    def start(self, username=None):
        """Startet Bot"""
        if not self.running:
            self.running = True
            self.paused = False
            self.consecutive_errors = 0
            self.current_user = username
            self.thread = threading.Thread(target=self.bot_loop, daemon=True)
            self.thread.start()
            logger.info(f"{self.bot_name}: Gestartet von {username}")
    
    def pause(self):
        """Pausiert Bot"""
        if self.running:
            self.paused = not self.paused
            logger.info(f"{self.bot_name}: {'Pausiert' if self.paused else 'Fortgesetzt'}")
    
    def stop(self):
        """Stoppt Bot"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=10)
        logger.info(f"{self.bot_name}: Gestoppt")