import os
import sys

sys.path.insert(0, r'e:\Transpulse')
os.environ['FLASK_APP'] = 'app.py'

from app import app, _admin_shell_metrics

with app.app_context():
    metrics = _admin_shell_metrics(include_snapshot=True)
    import pprint
    pprint.pprint(metrics)
