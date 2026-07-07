import os
import sys

sys.path.insert(0, r'e:\Transpulse')
os.environ['FLASK_APP'] = 'app.py'

from app import app
from flask import Flask
import json

app.config['WTF_CSRF_ENABLED'] = False

with app.app_context():
    client = app.test_client()
    
    print("Authenticating driver...")
    login_res = client.post('/login', data={
        'email': 'driver@transpulse.com',
        'password': 'driver@tp',
        'login_type': 'driver',
        'driver_id': 'DTP-001'
    })
    print(f"Login Status Code: {login_res.status_code}")
    
    print("\nTesting /api/buses/live")
    live_res = client.get('/api/buses/live')
    print(f"Status Code: {live_res.status_code}")
    if live_res.status_code != 200:
        print(live_res.get_data(as_text=True))
    else:
        live_data = live_res.get_json()
        buses = live_data.get('buses', [])
        print(f"Total live buses: {len(buses)}")
        completed_in_live = [b for b in buses if b.get('service_status') == 'completed']
        print(f"Completed buses in live fleet: {len(completed_in_live)}")
    
    print("\nTesting /api/tracking/completed/APSRTC-101")
    comp_res = client.get('/api/tracking/completed/APSRTC-101')
    print(f"Status Code: {comp_res.status_code}")
    if comp_res.status_code == 200:
        comp_data = comp_res.get_json()
        bus = comp_data.get('bus', {})
        print(f"Bus found: {bus.get('bus_number')}, Status: {bus.get('status')}, Trip Status: {bus.get('trip_status')}")
    else:
        print(f"Error: {comp_res.get_data(as_text=True)}")

