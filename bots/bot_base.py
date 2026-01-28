#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot Base Class mit Auto-Reconnect
Version 3.2
"""

import subprocess
import time
import logging
import threading

logger = logging.getLogger(__name__)


class BotBase:
    """Basis-Klasse für Bots mit SSH-Tunnel und Auto-Reconnect"""
    
    def __init__(self, bot_name, ssh_config):
        self.bot_name = bot_name
        self.ssh_config = ssh_config
        self.running = False
        self.paused = False
        self.ssh_process = None
        self.adb_connected = False
        
        # Auto-Reconnect Variablen
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5
        self.last_ssh_refresh = time.time()
        self.ssh_refresh_interval = 1800  # 30 Minuten
        self.keepalive_thread = None
    
    def ssh_keepalive_loop(self):
        """Hält SSH-Tunnel durch periodischen Refresh aktiv"""
        logger.info(f"{self.bot_name}: SSH-Keepalive-Thread gestartet")
        while self.running:
            time.sleep(60)
            if not self.running:
                break
            
            elapsed = time.time() - self.last_ssh_refresh
            if elapsed >= self.ssh_refresh_interval:
                logger.info(f"{self.bot_name}: Preventiver SSH-Tunnel Refresh (30 Min)")
                try:
                    self.close_ssh_tunnel()
                    time.sleep(3)
                    if self.setup_ssh_tunnel():
                        self.last_ssh_refresh = time.time()
                        self.consecutive_errors = 0
                        logger.info(f"{self.bot_name}: SSH-Tunnel erfolgreich refreshed")
                    else:
                        logger.warning(f"{self.bot_name}: SSH-Tunnel Refresh fehlgeschlagen")
                except Exception as e:
                    logger.error(f"{self.bot_name}: Fehler beim SSH-Refresh: {e}")
        logger.info(f"{self.bot_name}: SSH-Keepalive-Thread beendet")
    
    def setup_ssh_tunnel(self):
        """Baut SSH-Tunnel auf"""
        ssh_command_str = self.ssh_config.get('ssh_command')
        ssh_password = self.ssh_config.get('ssh_password')
        local_port = self.ssh_config.get('local_adb_port')

        if not ssh_command_str or not local_port:
            logger.error(f"{self.bot_name}: SSH-Command oder Local Port fehlt")
            self.adb_connected = False
            return False
        
        self.close_ssh_tunnel()
        
        # Parse SSH Command
        import re
        user_host_match = re.search(r'([\w\.\-_]+)@([\d\.]+)', ssh_command_str)
        port_match = re.search(r'-p\s+(\d+)', ssh_command_str)
        remote_port_match = re.search(r':(\d+)\s+-Nf', ssh_command_str)
        
        if not user_host_match or not port_match or not remote_port_match:
            logger.error(f"{self.bot_name}: Konnte SSH-Command nicht parsen")
            return False
        
        ssh_username = user_host_match.group(1)
        ssh_host = user_host_match.group(2)
        ssh_port = int(port_match.group(1))
        remote_port = int(remote_port_match.group(1))
        
        logger.info(f"{self.bot_name}: Starte SSH-Tunnel auf Port {local_port}...")
        
        try:
            from sshtunnel import SSHTunnelForwarder
            
            self.ssh_process = SSHTunnelForwarder(
                (ssh_host, ssh_port),
                ssh_username=ssh_username,
                ssh_password=ssh_password,
                remote_bind_address=('adb-proxy', remote_port),
                local_bind_address=('127.0.0.1', int(local_port)),
                set_keepalive=10.0,
                ssh_config_file=None,
                allow_agent=False,
                host_pkey_directories=[]
            )
            
            self.ssh_process.start()
            logger.info(f"{self.bot_name}: SSH-Tunnel erfolgreich gestartet")
            
            time.sleep(2)
            
            # ADB verbinden
            adb_cmd = ['adb', 'connect', f'localhost:{local_port}']
            adb_result = subprocess.run(adb_cmd, capture_output=True, text=True, timeout=10)
            
            if 'connected' in adb_result.stdout.lower() or 'already' in adb_result.stdout.lower():
                logger.info(f"{self.bot_name}: ADB erfolgreich verbunden")
                self.adb_connected = True
                self.last_ssh_refresh = time.time()
                return True
            else:
                logger.warning(f"{self.bot_name}: ADB-Verbindung fehlgeschlagen")
                self.close_ssh_tunnel()
                self.adb_connected = False
                return False

        except Exception as e:
            logger.error(f"{self.bot_name}: Fehler beim SSH-Tunnel: {e}")
            self.close_ssh_tunnel()
            self.adb_connected = False
            return False
    
    def close_ssh_tunnel(self):
        """Schließt SSH-Tunnel"""
        try:
            local_port = self.ssh_config.get('local_adb_port')
            if local_port:
                logger.info(f"{self.bot_name}: Trenne ADB von localhost:{local_port}")
                subprocess.run(['adb', 'disconnect', f'localhost:{local_port}'], 
                             timeout=5, capture_output=True)
            
            if self.ssh_process:
                logger.info(f"{self.bot_name}: Beende SSH-Tunnel-Prozess")
                if hasattr(self.ssh_process, 'stop'):
                    self.ssh_process.stop()
                else:
                    self.ssh_process.terminate()
                    self.ssh_process.wait(timeout=5)
                self.ssh_process = None

            self.adb_connected = False
            logger.info(f"{self.bot_name}: SSH-Tunnel sauber getrennt")
        except Exception as e:
            logger.error(f"{self.bot_name}: Fehler beim Schließen: {e}")
    
    def make_screenshot(self, filename='screen.png'):
        """Screenshot mit Auto-Retry"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                local_port = self.ssh_config.get('local_adb_port')
                if not local_port:
                    return False
                
                adb_device = f'localhost:{local_port}'
                
                # Screenshot erstellen
                result_screencap = subprocess.run(
                    ['adb', '-s', adb_device, 'shell', 'screencap', '-p', f'/sdcard/{filename}'], 
                    timeout=15, 
                    capture_output=True
                )
                
                if result_screencap.returncode != 0:
                    raise Exception("screencap fehlgeschlagen")
                
                # Screenshot pullen
                result_pull = subprocess.run(
                    ['adb', '-s', adb_device, 'pull', f'/sdcard/{filename}', filename], 
                    timeout=15, 
                    capture_output=True
                )
                
                import os
                if result_pull.returncode == 0 and os.path.exists(filename):
                    self.consecutive_errors = 0
                    return True
                else:
                    raise Exception("pull fehlgeschlagen")
                    
            except subprocess.TimeoutExpired:
                logger.warning(f"{self.bot_name}: Screenshot timeout, Versuch {attempt+1}/{max_retries}")
                self.consecutive_errors += 1
                
                if attempt < max_retries - 1:
                    if self.consecutive_errors >= 3:
                        logger.error(f"{self.bot_name}: 3 Fehler - SSH-Reconnect")
                        self.close_ssh_tunnel()
                        time.sleep(3)
                        self.setup_ssh_tunnel()
                        self.consecutive_errors = 0
                    time.sleep(2)
                    
            except Exception as e:
                logger.error(f"{self.bot_name}: Screenshot-Fehler: {e}")
                self.consecutive_errors += 1
                
                if attempt < max_retries - 1:
                    if self.consecutive_errors >= 3:
                        logger.error(f"{self.bot_name}: 3 Fehler - SSH-Reconnect")
                        self.close_ssh_tunnel()
                        time.sleep(3)
                        self.setup_ssh_tunnel()
                        self.consecutive_errors = 0
                    time.sleep(2)
        
        # Kompletter Reset bei zu vielen Fehlern
        if self.consecutive_errors >= self.max_consecutive_errors:
            logger.error(f"{self.bot_name}: {self.max_consecutive_errors} Fehler - KOMPLETTER RESET")
            self.close_ssh_tunnel()
            time.sleep(5)
            self.setup_ssh_tunnel()
            self.consecutive_errors = 0
        
        return False
    
    def click(self, x, y):
        """ADB Click"""
        try:
            local_port = self.ssh_config.get('local_adb_port')
            if not local_port:
                return False
            adb_device = f'localhost:{local_port}'
            subprocess.run(['adb', '-s', adb_device, 'shell', 'input', 'tap', 
                          str(x), str(y)], capture_output=True, timeout=5)
            time.sleep(2)
            return True
        except Exception as e:
            logger.error(f"{self.bot_name}: Klick-Fehler: {e}")
            return False
    
    def start_keepalive(self):
        """Startet Keepalive-Thread"""
        if not self.keepalive_thread or not self.keepalive_thread.is_alive():
            self.keepalive_thread = threading.Thread(
                target=self.ssh_keepalive_loop, 
                daemon=True
            )
            self.keepalive_thread.start()
    
    def stop_keepalive(self):
        """Stoppt Keepalive-Thread"""
        if self.keepalive_thread:
            self.keepalive_thread.join(timeout=5)
