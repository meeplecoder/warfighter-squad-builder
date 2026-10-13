"""Development server:  python run.py   (http://127.0.0.1:5000)

For production use a WSGI server instead — see INSTALL.md (e.g. `gunicorn -w 1 --threads 4 run:app`).
HOST / PORT / DEBUG come from the environment (.env).
"""
import os
from dotenv import load_dotenv
load_dotenv()
from app import create_app

app = create_app()

if __name__ == '__main__':
    # Bound to localhost by default: the Flask debugger must never be reachable from the network.
    app.run(debug=app.config['DEBUG'], port=int(os.environ.get('PORT', 5000)), host=os.environ.get('HOST', '127.0.0.1'))
