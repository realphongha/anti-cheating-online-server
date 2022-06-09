import yaml
from flask import Flask
from flask_pymongo import PyMongo
from flask_cors import CORS
from flask_socketio import SocketIO

app = Flask("anti_cheating_server")

with open("./anticheatingserver/config/config.yaml") as config_file:
    cfg = yaml.load(config_file, Loader=yaml.FullLoader)
    
app.config["SECRET_KEY"] = cfg["SECRET_KEY"]
app.config["MONGO_URI"] = cfg["MONGODB_URI"]
mongo = PyMongo(app)
cors = CORS(app)
app.config['CORS_HEADERS'] = 'Content-Type'
socketio = SocketIO(app, cors_allowed_origins="*", logger=True)
