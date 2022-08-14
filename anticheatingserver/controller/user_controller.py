import os
import json
import pymongo
import datetime
from bson.objectid import ObjectId
from bson import json_util
from flask import request
from .. import app, mongo
from ..utils.auth import hash_password, check_password
from ..utils.auth import token_required, make_token
from ..utils.constants import *
from ..utils.string import validate_email


def standardize_json(user):
    user["id"] = str(user["_id"])
    del user["_id"]
    user["updated_by"] = str(user["updated_by"])
    del user["password"]


@app.route("/login", methods=["POST"])
def login():
    data = json.loads(request.data)
    email = data.get("email", None)
    password = data.get("password", None)
    if not email or not password:
        return {
            "message": "Vui lòng nhập đầy đủ email và mật khẩu!"
        }, 400
    email = email.strip()
    if not validate_email(email):
        return {
            "message": "Email không hợp lệ!"
        }, 400

    if len(password) < 6 or len(password) > 20:
        return {
            "message": "Password phải dài từ 6 tới 20 ký tự!"
        }, 400
    user = mongo.db.users.find_one({"email": email,
        "status": USER_STATUS_ACTIVE
    })
    if user is None:
        return {
            "message": "Email không tồn tại!"
        }, 401
    true_password = user["password"]
    standardize_json(user)
    if check_password(true_password, password):
        token = make_token(user["id"]).decode('UTF-8')
        return json_util.dumps({
                "user": user,
                "token": token
            })
    return {
        "message": "Sai mật khẩu!"
    }, 401


@app.route("/register", methods=["POST"])
def register():
    data = request.data
    data = json.loads(data)
    email = data.get("email", None)
    password = data.get("password", None)
    c_password = data.get("c_password", None)
    if password != c_password:
        return {
            "message": "Mật khẩu xác nhận không khớp!"
        }, 400
    h_password = hash_password(password) if password else None
    name = data.get("name", None)
    phone = data.get("phone", None)
    role = data.get("role", None)
    if email is None or h_password is None \
        or name is None or phone is None or role is None:
        return {
            "message": "Vui lòng nhập đầy đủ form!"
        }, 400
    email = email.strip()
    if not validate_email(email):
        return {
            "message": "Email không hợp lệ!"
        }, 400
    if len(password) < 6 or len(password) > 20:
        return {
            "message": "Password phải dài từ 6 tới 20 ký tự!"
        }, 400
    name = name.strip()
    if len(name) < 3 or len(name) > 100:
        return {
            "message": "Họ tên phải dài từ 3 tới 100 ký tự!"
        }, 400
    phone = phone.strip()
    if len(phone) != 10:
        return {
            "message": "Số điện thoại phải dài 10 ký tự!"
        }, 400
    role = int(role)
    if role not in (USER_ROLE_STUDENT, USER_ROLE_SUPERVISOR):
        return {
            "message": "Không thể tạo loại tài khoản này!"
        }, 400
    try:
        result = mongo.db.users.insert_one({
            "email": email,
            "password": h_password,
            "name": name,
            "phone": phone,
            "role": role,
            "avatar": "",
            "status": USER_STATUS_ACTIVE,
            "last_updated": datetime.datetime.utcnow(),
            "updated_by": None
        })
    except pymongo.errors.DuplicateKeyError:
        return {
            "message": "Email đã tồn tại!"
        }, 400
    user = mongo.db.users.find_one_or_404({"_id": ObjectId(result.inserted_id)})
    standardize_json(user)
    return json_util.dumps(user)


@app.route("/users/get_current", methods=["GET"])
@token_required(role=("all",))
def get_current_user(current_user):
    standardize_json(current_user)
    return json_util.dumps(current_user)


@app.route("/users/edit", methods=["PUT"])
@token_required(role=("all",))
def edit_current_user(current_user):
    data = request.data
    data = json.loads(data)
    email = data.get("email", None)
    o_password = data.get("o_password", None);
    password = data.get("password", None)
    c_password = data.get("c_password", None)
    h_password = None
    if c_password is not None:
        if not check_password(current_user["password"], o_password):
            return {
                "message": "Mật khẩu cũ không đúng!"
            }, 400
        if password != c_password:
            return {
                "message": "Mật khẩu xác nhận không khớp!"
            }, 400
        h_password = hash_password(password)
    name = data.get("name", None)
    phone = data.get("phone", None)
    email = email.strip() if email else None
    if email and not validate_email(email):
        return {
            "message": "Email không hợp lệ!"
        }, 400
    if password and (len(password) < 6 or len(password) > 20):
        return {
            "message": "Password phải dài từ 6 tới 20 ký tự!"
        }, 400
    name = name.strip() if name else None
    if name and (len(name) < 3 or len(name) > 100):
        return {
            "message": "Họ tên phải dài từ 3 tới 100 ký tự!"
        }, 400
    phone = phone.strip() if phone else None
    if phone and len(phone) != 10:
        return {
            "message": "Số điện thoại phải dài 10 ký tự!"
        }, 400
    update_obj = {
        "last_updated": datetime.datetime.utcnow(),
        "updated_by": current_user["_id"]
    }
    if not email and not h_password and not name and not phone:
        return {
            "message": "Không có gì để cập nhật!"
        }, 400
    if email: update_obj["email"] = email
    if h_password: update_obj["password"] = h_password
    if name: update_obj["name"] = name
    if phone: update_obj["phone"] = phone
    try:
        result = mongo.db.users.update_one({
                "_id": current_user["_id"]
            }, {
                "$set": update_obj
            })
    except pymongo.errors.DuplicateKeyError:
        return {
            "message": "Email đã tồn tại!"
        }, 400
    user = mongo.db.users.find_one_or_404({"_id": current_user["_id"]})
    standardize_json(user)
    return json_util.dumps(user)


@app.route("/users/avatar", methods=["PUT"])
@token_required(role=("all",))
def change_avatar(current_user):
    data = request.files
    img = data.get("img", None)
    if img:
        img.seek(0, os.SEEK_END)
        size = img.tell()
        if size > MAX_SIZE_AVATAR:
            return {
                "message": "Ảnh đại diện phải nhỏ hơn 1MB!"
            }, 400
        img.seek(0)
        raw_img = img.read()
        result = mongo.db.users.update_one({
            "_id": current_user["_id"]
        }, {
            "$set": {
                "avatar": raw_img
            }
        })
        user = mongo.db.users.find_one_or_404({"_id": current_user["_id"]})
        standardize_json(user)
        return json_util.dumps(user)
    else:
        return {
            "message": "Vui lòng upload ảnh đại diện mới!"
        }, 400


@app.route("/users", methods=["GET"])
@token_required(role=("admin",))
def get_list_users(current_user):
    query = request.args
    q_sort = query.get("sort")
    if q_sort:
        q_sort = json.loads(q_sort)
        if q_sort[1].lower() == "asc":
            q_sort[1] = pymongo.ASCENDING
        elif q_sort[1].lower() == "desc":
            q_sort[1] = pymongo.DESCENDING
    first, last = None, None
    q_range = query.get("range")
    if q_range:
        q_range = json.loads(q_range)
        first, last = q_range
    q_filter = query.get("filter")
    if q_filter:
        q_filter = json.loads(q_filter)
        if "q" in q_filter:
            q_filter["$text"] = {
                "$search": q_filter["q"]
            }
            del q_filter["q"]
        for f in q_filter:
            if type(q_filter[f]) == str and q_filter[f].isdigit():
                q_filter[f] = int(q_filter[f])
    users = mongo.db.users.find(q_filter if q_filter else {})
    count_users = mongo.db.users.count_documents({})
    if q_sort:
        users = users.sort(*q_sort)
    if first is not None and last is not None:
        users = users.skip(first).limit(last-first+1)
    result = []
    for user in users:
        standardize_json(user)
        result.append(user)
    first = first if first else 0
    last = first + len(result)
    return json_util.dumps(result), 200, {
            'Access-Control-Expose-Headers': 'Content-Range',
            'Content-Range': 'user %i-%i/%i' % (first, last, count_users)
        }


@app.route("/users/<id>", methods=["GET"])
@token_required(role=("admin",))
def get_one_user(current_user, id):
    user = mongo.db.users.find_one_or_404({"_id": ObjectId(id)})
    standardize_json(user)
    return json_util.dumps(user)


@app.route("/users", methods=["POST"])
@token_required(role=("admin",))
def create_user(current_user):
    data = request.data
    data = json.loads(data)
    email = data.get("email", None)
    password = data.get("password", None)
    c_password = data.get("c_password", None)
    if password != c_password:
        return {
            "message": "Mật khẩu xác nhận không khớp!"
        }, 400
    h_password = hash_password(password) if password else None
    name = data.get("name", None)
    phone = data.get("phone", None)
    role = data.get("role", None)
    if email is None or h_password is None \
        or name is None or phone is None or role is None:
        return {
            "message": "Vui lòng nhập đầy đủ form!"
        }, 400
    email = email.strip()
    if not validate_email(email):
        return {
            "message": "Email không hợp lệ!"
        }, 400
    if len(password) < 6 or len(password) > 20:
        return {
            "message": "Password phải dài từ 6 tới 20 ký tự!"
        }, 400
    name = name.strip()
    if len(name) < 3 or len(name) > 100:
        return {
            "message": "Họ tên phải dài từ 3 tới 100 ký tự!"
        }, 400
    phone = phone.strip()
    if len(phone) != 10:
        return {
            "message": "Số điện thoại phải dài 10 ký tự!"
        }, 400
    role = int(role)
    if role not in (USER_ROLE_STUDENT, USER_ROLE_SUPERVISOR, USER_ROLE_ADMIN):
        return {
            "message": "Không thể tạo loại tài khoản này!"
        }, 400
    try:
        result = mongo.db.users.insert_one({
            "email": email,
            "password": h_password,
            "name": name,
            "phone": phone,
            "role": int(role),
            "avatar": "",
            "status": USER_STATUS_ACTIVE,
            "last_updated": datetime.datetime.utcnow(),
            "updated_by": ObjectId("6284a2371e3a28c2d8418e0e")
        })
    except pymongo.errors.DuplicateKeyError:
        return {
            "message": "Email đã tồn tại!"
        }, 400
    user = mongo.db.users.find_one_or_404({"_id": ObjectId(result.inserted_id)})
    standardize_json(user)
    return json_util.dumps(user)


@app.route("/users/<id>", methods=["PUT"])
@token_required(role=("admin",))
def update_user(current_user, id):
    data = request.data
    data = json.loads(data)
    email = data.get("email", None)
    password = data.get("password", None)
    c_password = data.get("c_password", None)
    h_password = None
    if c_password is not None:
        if password != c_password:
            return {
                "message": "Mật khẩu xác nhận không khớp!"
            }, 400
        h_password = hash_password(password)
    name = data.get("name", None)
    phone = data.get("phone", None)
    role = data.get("role", None)
    status = data.get("status", None)
    avatar = data.get("avatar", None)
    email = email.strip() if email else None
    if email and not validate_email(email):
        return {
            "message": "Email không hợp lệ!"
        }, 400
    if password and (len(password) < 6 or len(password) > 20):
        return {
            "message": "Password phải dài từ 6 tới 20 ký tự!"
        }, 400
    name = name.strip() if name else None
    if name and (len(name) < 3 or len(name) > 100):
        return {
            "message": "Họ tên phải dài từ 3 tới 100 ký tự!"
        }, 400
    phone = phone.strip() if phone else None
    if phone and len(phone) != 10:
        return {
            "message": "Số điện thoại phải dài 10 ký tự!"
        }, 400
    role = int(role) if role else None
    if role not in (USER_ROLE_ADMIN, USER_ROLE_STUDENT,
        USER_ROLE_SUPERVISOR):
        return {
            "message": "Không thể tạo loại tài khoản này!"
        }, 400
    update_obj = {
        "last_updated": datetime.datetime.utcnow(),
        "updated_by": ObjectId("6284a2371e3a28c2d8418e0e")
    }
    if email: update_obj["email"] = email
    if h_password: update_obj["password"] = h_password
    if name: update_obj["name"] = name
    if phone: update_obj["phone"] = phone
    if role: update_obj["role"] = int(role)
    if status: update_obj["status"] = status
    if avatar: update_obj["avatar"] = avatar
    try:
        result = mongo.db.users.update_one({
                "_id": ObjectId(id)
            }, {
                "$set": update_obj
            })
    except pymongo.errors.DuplicateKeyError:
        return {
            "message": "Email đã tồn tại!"
        }, 400
    user = mongo.db.users.find_one_or_404({"_id": ObjectId(id)})
    standardize_json(user)
    return json_util.dumps(user)


@app.route("/users/<id>", methods=["DELETE"])
@token_required(role=("admin",))
def delete_user(current_user, id):
    # result = mongo.db.users.delete_one({"_id": ObjectId(id)})
    # deactivate the account instead of actually delete
    user = mongo.db.users.find_one_or_404({"_id": ObjectId(id)})
    status = user["status"]
    new_status = USER_STATUS_LOCKED if status == USER_STATUS_ACTIVE else USER_STATUS_ACTIVE
    result = mongo.db.users.update_one({
            "_id": ObjectId(id)
        }, {
            "$set": {
                "status": new_status
            }
        })
    return json_util.dumps(result.raw_result)
