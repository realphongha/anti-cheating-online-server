from . import app, socketio, cfg
from .controller import *


if __name__ == "__main__":
    socketio.run(app, host=cfg["HOST"], port=cfg["PORT"], debug=cfg["DEBUG"])
    