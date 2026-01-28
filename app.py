#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LKW Bot Web Interface - Modular
Version 3.2
"""

import os
import json
import logging
from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from flask_login import LoginManager, login_user, logout_user, login_required, current_user

# Import Module
from bots.lkw_bot import LKWBotController
from utils.config import load_ssh_config, save_ssh_config
from utils.users import User, init_users, load_users, save_users, load_user
from utils.translations import TRANSLATIONS, get_language, translate

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('lkw-bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Flask App
app = Flask(__name__)
app.secret_key = 'dein-sehr-geheimer-schluessel-hier-aendern-123!@#'

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.user_loader(load_user)

# Initialisiere Benutzer
init_users()

# Bot Instanzen
ssh_config = load_ssh_config('ssh_config.json')
lkw_bot = LKWBotController(ssh_config)

# Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        from werkzeug.security import check_password_hash
        users = load_users()
        
        if username in users:
            user_data = users[username]
            if user_data.get('blocked', False):
                error = "Benutzer ist gesperrt"
                return render_template('login.html', error=error, t=translate, lang=get_language())
            
            if check_password_hash(user_data['password'], password):
                user = load_user(username)
                login_user(user)
                return redirect(url_for('index'))
        
        error = translate('invalid_credentials')
        return render_template('login.html', error=error, t=translate, lang=get_language())
    
    return render_template('login.html', t=translate, lang=get_language())

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html', t=translate, lang=get_language(), user=current_user)

@app.route('/api/status')
@login_required
def api_status():
    return jsonify({
        'running': lkw_bot.running,
        'paused': lkw_bot.paused,
        'status': lkw_bot.status,
        'last_action': lkw_bot.last_action,
        'trucks_processed': lkw_bot.trucks_processed,
        'trucks_shared': lkw_bot.trucks_shared,
        'trucks_skipped': lkw_bot.trucks_skipped,
        'adb_connected': lkw_bot.adb_connected,
        'current_user': lkw_bot.current_user
    })

@app.route('/api/start', methods=['POST'])
@login_required
def api_start():
    users = load_users()
    if current_user.username in users and users[current_user.username].get('blocked', False):
        return jsonify({'error': 'User is blocked'}), 403
    
    with lkw_bot.lock:
        if lkw_bot.current_user and lkw_bot.current_user != current_user.username:
            if current_user.role != 'admin':
                return jsonify({'error': f'Bot wird bereits von {lkw_bot.current_user} verwendet'}), 409
            lkw_bot.stop()
        
        lkw_bot.start(current_user.username)
    
    return jsonify({'success': True})

@app.route('/api/pause', methods=['POST'])
@login_required
def api_pause():
    lkw_bot.pause()
    return jsonify({'success': True})

@app.route('/api/stop', methods=['POST'])
@login_required
def api_stop():
    with lkw_bot.lock:
        lkw_bot.stop()
        lkw_bot.current_user = None
    return jsonify({'success': True})

@app.route('/api/settings', methods=['GET', 'POST'])
@login_required
def api_settings():
    if request.method == 'POST':
        data = request.json
        lkw_bot.use_limit = data.get('use_limit', False)
        lkw_bot.strength_limit = float(data.get('strength_limit', 60))
        lkw_bot.use_server_filter = data.get('use_server_filter', False)
        lkw_bot.server_number = data.get('server_number', '49')
        lkw_bot.reset_interval = int(data.get('reset_interval', 15))
        lkw_bot.share_mode = data.get('share_mode', 'world')
        
        return jsonify({'success': True})
    else:
        return jsonify({
            'use_limit': lkw_bot.use_limit,
            'strength_limit': lkw_bot.strength_limit,
            'use_server_filter': lkw_bot.use_server_filter,
            'server_number': lkw_bot.server_number,
            'reset_interval': lkw_bot.reset_interval,
            'share_mode': lkw_bot.share_mode
        })

@app.route('/api/reset_stats', methods=['POST'])
@login_required
def api_reset_stats():
    lkw_bot.trucks_processed = 0
    lkw_bot.trucks_shared = 0
    lkw_bot.trucks_skipped = 0
    return jsonify({'success': True})

# Admin Routes
@app.route('/admin')
@login_required
def admin():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    return render_template('admin.html', user=current_user)

@app.route('/api/admin/ssh_config', methods=['GET', 'POST'])
@login_required
def api_admin_ssh_config():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    if request.method == 'POST':
        data = request.json
        ssh_command = data.get('ssh_command', '').strip()
        ssh_password = data.get('ssh_password', '').strip()
        
        if not ssh_command:
            return jsonify({'error': 'SSH-Command ist erforderlich'}), 400
        
        from utils.config import parse_ssh_command
        parsed = parse_ssh_command(ssh_command)
        if not parsed:
            return jsonify({'error': 'Ungültiger SSH-Command'}), 400
        
        config = {
            'ssh_command': ssh_command,
            'ssh_password': ssh_password,
            'local_adb_port': parsed.get('local_port')
        }
        
        if save_ssh_config(config, 'ssh_config.json'):
            lkw_bot.ssh_config = config
            if lkw_bot.running:
                lkw_bot.close_ssh_tunnel()
                import time
                time.sleep(1)
                lkw_bot.setup_ssh_tunnel()
            return jsonify({'success': True, 'message': 'SSH-Konfiguration gespeichert'})
        else:
            return jsonify({'error': 'Fehler beim Speichern'}), 500
    else:
        config = load_ssh_config('ssh_config.json')
        return jsonify({
            'ssh_command': config.get('ssh_command', ''),
            'ssh_password': config.get('ssh_password', ''),
            'local_adb_port': config.get('local_adb_port'),
            'last_updated': config.get('last_updated', None)
        })

@app.route('/api/admin/test_ssh', methods=['POST'])
@login_required
def api_admin_test_ssh():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    try:
        lkw_bot.close_ssh_tunnel()
        import time
        time.sleep(1)
        if lkw_bot.setup_ssh_tunnel():
            return jsonify({'success': True, 'message': 'SSH-Tunnel erfolgreich verbunden'})
        else:
            return jsonify({'success': False, 'message': 'Verbindung fehlgeschlagen'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': f'Fehler: {str(e)}'}), 500

if __name__ == '__main__':
    ssh_config = load_ssh_config('ssh_config.json')
    if ssh_config.get('ssh_command'):
        logger.info("SSH-Konfiguration geladen")
    else:
        logger.warning("⚠️  KEINE SSH-KONFIGURATION VORHANDEN!")
    
    logger.info("Starte LKW-Bot Web-Interface v3.2 (Modular)...")
    app.run(host='0.0.0.0', port=5000, debug=False)
