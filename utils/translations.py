#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Translations
"""

from flask import session

TRANSLATIONS = {
    'de': {
        'app_title': 'LKW-Bot Steuerung',
        'logout': 'Abmelden',
        'status': 'Status',
        'btn_start': 'Start',
        'btn_pause': 'Pause',
        'btn_stop': 'Stopp',
        'statistics': 'Statistiken',
        'processed': 'Verarbeitet',
        'shared': 'Geteilt',
        'skipped': 'Übersprungen',
        'settings': 'Einstellungen',
        'login_title': 'LKW-Bot',
        'username': 'Benutzername',
        'password': 'Passwort',
        'login_button': 'Anmelden',
        'invalid_credentials': 'Ungültige Anmeldedaten',
        'running': 'Läuft',
        'stopped': 'Gestoppt',
        'paused': 'Pausiert'
    },
    'en': {
        'app_title': 'LKW-Bot Control',
        'logout': 'Logout',
        'status': 'Status',
        'btn_start': 'Start',
        'btn_pause': 'Pause',
        'btn_stop': 'Stop',
        'statistics': 'Statistics',
        'processed': 'Processed',
        'shared': 'Shared',
        'skipped': 'Skipped',
        'settings': 'Settings',
        'login_title': 'LKW-Bot',
        'username': 'Username',
        'password': 'Password',
        'login_button': 'Login',
        'invalid_credentials': 'Invalid credentials',
        'running': 'Running',
        'stopped': 'Stopped',
        'paused': 'Paused'
    }
}


def get_language():
    return session.get('language', 'de')


def translate(key):
    lang = get_language()
    return TRANSLATIONS.get(lang, TRANSLATIONS['de']).get(key, key)
