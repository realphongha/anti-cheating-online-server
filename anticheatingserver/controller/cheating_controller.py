import json
import datetime
import os
from bson.objectid import ObjectId
from bson import json_util
from flask import request
from .. import app, mongo
from ..utils.auth import token_required
from ..utils.constants import *


@app.route("/cheatings", methods=["POST"])
@token_required(role=("supervisor",))
def create_cheating(current_user):
    data = request.form
    student_id = data.get("student_id", None)
    class_id = data.get("class_id", None)
    note = data.get("note", None)
    image = None
    file_data = request.files
    image = file_data.get("img", None)
    if image:
        image.seek(0, os.SEEK_END)
        size = image.tell()
        if size > MAX_SIZE_IMAGE:
            return {
                "message": "Ảnh phải nhỏ hơn 512KB!"
            }, 400 
        image.seek(0)
        image = image.read()
    if student_id is None or class_id is None or \
        note is None:
        return {
            "message": "Vui lòng nhập đầy đủ các trường thông tin!"
        }, 400
    note = note.strip()
    if len(note) < 5:
        return {
            "message": "Ghi chú phải nhiều hơn 5 ký tự!"
        }, 400
    student = mongo.db.users.find_one_or_404({
        "_id": ObjectId(student_id),
        "status": USER_STATUS_ACTIVE,
        "role": USER_ROLE_STUDENT
    })
    class_ = mongo.db.classes.find_one_or_404({
        "_id": ObjectId(class_id),
        "supervisor_id": current_user["_id"],
        "status": CLASS_STATUS_ACTIVE
    })
    if student["_id"] not in class_["students"]:
        return {
            "message": "Học sinh không trong lớp thi!"
        }, 400
    start = class_["start"]
    last = class_["last"]
    end = start + datetime.timedelta(minutes=last)
    now = datetime.datetime.utcnow()
    if not start < now < end:
        return {
            "message": "Không thể thêm khi không trong giờ thi!"
        }, 403
    result = mongo.db.cheatings.insert_one({
        "student_id": student_id,
        "image": image,
        "note": note,
        "time": datetime.datetime.utcnow()
    })
    c = mongo.db.cheatings.find_one_or_404({
        "_id": ObjectId(result.inserted_id)
    })
    cheatings_list = class_["cheatings"]
    cheatings_list.append(ObjectId(result.inserted_id))
    result2 = mongo.db.classes.update_one({
            "_id": ObjectId(class_id)
        }, {
            "$set": {
                "cheatings": cheatings_list
            }
        })
    return json_util.dumps(c)


@app.route("/cheatings/<id>", methods=["DELETE"])
@token_required(role=("supervisor",))
def delete_cheating(current_user, id):
    data = request.data
    data = json.loads(data)
    class_id = data.get("class_id", None)
    if class_id is None or id is None:
        return {
            "message": "Vui lòng nhập đủ thông tin!"
        }, 400
    class_ = mongo.db.classes.find_one_or_404({
        "_id": ObjectId(class_id),
        "supervisor_id": current_user["_id"],
        "status": CLASS_STATUS_ACTIVE
    })
    if ObjectId(id) not in class_["cheatings"]:
        return {
            "message": "Không thể xóa bản ghi này!"
        }, 403
    start = class_["start"]
    last = class_["last"]
    end = start + datetime.timedelta(minutes=last)
    now = datetime.datetime.utcnow()
    if not start < now < end:
        return {
            "message": "Không thể xóa khi không trong giờ thi!"
        }, 403
    result = mongo.db.cheatings.delete_one({"_id": ObjectId(id)})
    cheatings_list = class_["cheatings"]
    cheatings_list.remove(ObjectId(id))
    result2 = mongo.db.classes.update_one({
            "_id": ObjectId(class_id)
        }, {
            "$set": {
                "cheatings": cheatings_list
            }
        })
    return json_util.dumps(result.raw_result)
