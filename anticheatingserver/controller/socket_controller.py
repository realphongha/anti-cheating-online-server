import json
import pymongo
import dateutil
import datetime
from dateutil import parser
from bson.objectid import ObjectId
from bson import json_util
from flask import request
from flask_socketio import join_room, leave_room, close_room, rooms
from .. import app, mongo, socketio
from ..utils.auth import token_required
from ..utils.constants import *


@socketio.on("handle_image")
@token_required(role=("student"))
def handle_image(current_user, json, methods=["GET", "POST"]):
    if json.get("class_id", None) not in rooms(request.sid):
        return {
            'message' : 'Không có quyền!'
        }, 401
    if "supervisor_sid" in json and "image" in json:
        socketio.emit("handle_image", {
                "image": json["image"],
                "student_id": str(current_user["_id"]),
                "class_id": json["class_id"]
            }, to=[json["supervisor_sid"]])


@socketio.on("handle_cheating_image")
@token_required(role=("student"))
def handle_cheating_image(current_user, json, methods=["GET", "POST"]):
    if json.get("class_id", None) not in rooms(request.sid):
        return {
            'message' : 'Không có quyền!'
        }, 401
    if "supervisor_sid" in json and "image" in json \
        and "type" in json:
        socketio.emit("handle_cheating_image", {
                "image": json["image"],
                "student_id": str(current_user["_id"]),
                "class_id": json["class_id"],
                "type": json["type"]
            }, to=[json["supervisor_sid"]])


@socketio.on("handle_end_request")
@token_required(role=("student", "supervisor"))
def handle_end_request(current_user, json, methods=["GET", "POST"]):
    if json.get("class_id", None) not in rooms(request.sid):
        return {
            'message' : 'Không có quyền!'
        }, 401
    if current_user["role"] == USER_ROLE_STUDENT:
        if json.get("type", None) == "request":
            socketio.emit("handle_end_request", {
                "type": "request",
                "student_id": str(current_user["_id"]),
                "sid": request.sid,
                "class_id": json["class_id"]
            }, to=[json["class_id"]])
    elif current_user["role"] == USER_ROLE_SUPERVISOR:
        if json.get("type", None) == "reply" and "accept" in json and \
            "student_id" in json and "sid" in json:
            user = mongo.db.users.find_one_or_404({
                "_id": ObjectId(json["student_id"]),
                "status": USER_STATUS_ACTIVE
            })
            socketio.emit("handle_end_request", {
                "type": "reply",
                "accept": json["accept"]
            }, room=[json["sid"]])


@socketio.on("handle_end_exam")
@token_required(role=("supervisor",))
def handle_end_exam(current_user, json, methods=["GET", "POST"]):
    if json.get("class_id", None) is not None:
        class_ = mongo.db.classes.find_one_or_404({
                "_id": ObjectId(json["class_id"]),
                "supervisor_id": current_user["_id"],
                "status": CLASS_STATUS_ACTIVE
            })
        result = mongo.db.classes.update_one({
            "_id": class_["_id"]
        }, {
            "$set": {
                "end": datetime.datetime.utcnow()
            }
        })
        socketio.emit("handle_end_exam", json_util.dumps({
            "ended": datetime.datetime.utcnow()
        }), room=[json["class_id"]])
        close_room(json["class_id"])


@socketio.on('join')
@token_required(role=("student", "supervisor"))
def on_join(current_user, json, methods=["GET", "POST"]):
    if json.get("class_id", None) is not None:
        if current_user["role"] == USER_ROLE_STUDENT:
            class_ = mongo.db.classes.find_one_or_404({
                    "_id": ObjectId(json["class_id"]),
                    "status": CLASS_STATUS_ACTIVE
                })
            if current_user["_id"] in class_["students"]:
                join_room(json["class_id"])
        elif current_user["role"] == USER_ROLE_SUPERVISOR:
            class_ = mongo.db.classes.find_one_or_404({
                "_id": ObjectId(json["class_id"]),
                "supervisor_id": current_user["_id"],
                "status": CLASS_STATUS_ACTIVE
            })
            join_room(json["class_id"])
            socketio.emit("broadcast_supervisor_sid", {
                "supervisor_sid": request.sid
            }, room=[json["class_id"]])


@socketio.on('leave')
@token_required(role=("student", "supervisor"))
def on_leave(current_user, json):
    if json.get("class_id", None) is not None:
        leave_room(json["class_id"])


@socketio.on('broadcast_supervisor_sid')
@token_required(role=("supervisor",))
def on_broadcast_supervisor_sid(current_user, json, methods=["GET", "POST"]):
    if json.get("class_id", None) is not None:
        class_ = mongo.db.classes.find_one_or_404({
                "_id": ObjectId(json["class_id"]),
                "supervisor_id": current_user["_id"],
                "status": CLASS_STATUS_ACTIVE
            })
        socketio.emit("broadcast_supervisor_sid", {
            "supervisor_sid": request.sid
        }, room=[json["class_id"]])
