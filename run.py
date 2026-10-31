"""BIKA FYP2 Flask development entrypoint.

Do not preload the SAM3 model in the Windows dev server.
Disable the debug reloader to avoid duplicate Flask processes.
This changes neither the Inspection pipeline nor production WSGI imports.
"""

import os

# Set before importing the Flask app, which triggers create_app().
if __name__ == "__main__":
    os.environ.setdefault("BIKA_PRELOAD_MODEL", "0")

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
