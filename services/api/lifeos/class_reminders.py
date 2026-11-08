"""Explicit teaching-session classification and genuine source classroom metadata."""

import re


def is_class_event(event):
    if event.get('all_day'):
        return False
    if event.get('source') == 'timetable':
        return True
    if event.get('source') != 'braude':
        return False
    text = event.get('title', '') + ' ' + event.get('notes', '')
    if re.search(r'בחינה|בחינות|מבחן|מבחנים|מועד\s+[אבג]|exam|examination', text, re.I):
        return False
    return bool(re.search(r'הרצאה|תרגיל|תרגול|מעבדה', event.get('notes', '')))


def class_room(event):
    notes = event.get('notes', '')
    match = re.search(r'(?:^|\n)חדר:\s*([^\n]+)', notes)
    raw = match[1].strip() if match else notes.strip() if event.get('source') == 'timetable' else ''
    match = re.search(r'\b([A-Za-z])\s*[-/]?\s*(\d{3})\b', raw)
    if match:
        return f'{match[1].upper()} {match[2]}'
    match = re.search(r'\b(\d{3})\s*[-/]?\s*([A-Za-z])\b', raw)
    return f'{match[2].upper()} {match[1]}' if match else raw
