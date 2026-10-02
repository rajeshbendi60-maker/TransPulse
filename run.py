import sys
import os

# Ensure Python can find our new folders
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from backend.app import app

if __name__ == '__main__':
    app.run(debug=True, port=5000)
