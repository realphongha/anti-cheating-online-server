import json
import pymongo
from dateutil import parser
from bson.objectid import ObjectId
from bson import json_util
from flask import request
from .. import app, mongo
from ..utils.auth import token_required
from ..utils.constants import *
from ..utils.string import validate_email


def standardize_json_user(user):
    user["id"] = str(user["_id"])
    del user["_id"]


def standardize_json(class_):
    if "supervisor" in class_ and type(class_["supervisor"]) == list:
        class_["supervisor"] = class_["supervisor"][0]
        del class_["supervisor"]["password"]
    class_["id"] = str(class_["_id"])
    del class_["_id"]

    # get students:
    if "students" in class_:
        new_students = dict()
        for student_id in class_["students"]:
            student = mongo.db.users.find_one({
                "_id": student_id,
                "status": USER_STATUS_ACTIVE,
                "role": USER_ROLE_STUDENT
            }, {
                "email": 1,
                "name": 1, 
                "phone": 1,
                "avatar": 1
            })
            if not student:
                continue
            standardize_json_user(student)
            new_students[student["id"]] = student
        class_["students"] = new_students.values()

    # cheatings:
    if "cheatings" in class_:
        new_cheatings = []
        for cheating_id in class_["cheatings"]:
            cheating = mongo.db.cheatings.find_one({
                "_id": cheating_id,
            })
            if cheating is None:
                continue
            cheating["id"] = str(cheating["_id"])
            del cheating["_id"]
            try:
                cheating["student"] = new_students[str(cheating["student_id"])]
            except KeyError:
                continue
            del cheating["student_id"]
            new_cheatings.append(cheating)
        class_["cheatings"] = new_cheatings


@app.route("/classes", methods=["GET"])
@token_required(role=("admin", "supervisor"))
def get_list_classes(current_user):
    query = request.args
    q_sort = query.get("sort")
    if q_sort:
        q_sort = json.loads(q_sort)
        date_i = q_sort[0].index(".$date")
        if date_i != -1:
            q_sort[0] = q_sort[0][:date_i]
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
        if current_user["role"] == USER_ROLE_SUPERVISOR:
            q_filter["supervisor_id"] = current_user["_id"]
        if "q" in q_filter:
            all_search = list()
            all_search.append({"name": {
                "$regex": q_filter["q"],
                "$options": "i",
            }})
            all_search.append({"supervisor.name": {
                "$regex": q_filter["q"],
                "$options": "i",
            }})
            all_search.append({"supervisor.email": {
                "$regex": q_filter["q"],
                "$options": "i",
            }})
            q_filter["$or"] = all_search
            del q_filter["q"]
        for f in q_filter:
            if type(q_filter[f]) == str and q_filter[f].isdigit():
                q_filter[f] = int(q_filter[f])
    else:
        if current_user["role"] == USER_ROLE_SUPERVISOR:
            q_filter = {"supervisor_id": current_user["_id"]}
        else:
            q_filter = {}
    aggregation = [{
        "$lookup": {
            "from": "users",
            "localField": "supervisor_id",
            "foreignField": "_id",
            "as": "supervisor"
        }},
        {'$unwind': '$supervisor_id'},
    ]
    
    if q_filter:
        aggregation.append({'$match': q_filter})
    if q_sort:
        aggregation.append({'$sort': {q_sort[0]: q_sort[1]}})
    if first is not None and last is not None:
        aggregation.append({'$skip': first})
        aggregation.append({'$limit': last-first})
    classes = mongo.db.classes.aggregate(aggregation)
    if current_user["role"] == USER_ROLE_SUPERVISOR:
        count_classes = mongo.db.classes.count_documents({
            "supervisor_id": current_user["_id"]
        })
    else:
        count_classes = mongo.db.classes.count_documents({})
    result = []
    for class_ in classes:
        standardize_json(class_)
        result.append(class_)
    first = first if first else 0
    last = first + len(result)
    return json_util.dumps(result), 200, {
            'Access-Control-Expose-Headers': 'Content-Range',
            'Content-Range': 'user %i-%i/%i' % (first, last, count_classes)
        }


@app.route("/classes/<id>", methods=["GET"])
@token_required(role=("all"))
def get_one_class(current_user, id):
    aggregation = [{
        "$lookup": {
            "from": "users",
            "localField": "supervisor_id",
            "foreignField": "_id",
            "as": "supervisor"
        }},
        {'$unwind': '$supervisor_id'},
        {'$match': {
            "_id": ObjectId(id),
            "supervisor_id": current_user["_id"],
        } if current_user["role"] == USER_ROLE_SUPERVISOR else {
            "_id": ObjectId(id)
        }}
    ]
    res = mongo.db.classes.aggregate(aggregation)
    class_ = None
    for c in res:
        class_ = c
        break
    if class_ is None:
        return {
            "message": "Không tồn tại lớp thi!"
        }, 404
    if current_user["role"] == USER_ROLE_STUDENT and \
        current_user["_id"] not in class_["students"]:
        return {
            "message": "Không thể lấy thông tin lớp thi này!"
        }, 401
    standardize_json(class_)
    return json_util.dumps(class_)


@app.route("/classes", methods=["POST"])
@token_required(role=("supervisor",))
def create_class(current_user):
    data = request.data
    data = json.loads(data)
    name = data.get("name", None)
    start = data.get("start", None)
    last = data.get("last", None)
    if name is None or start is None or last is None:
        return {
            "message": "Vui lòng nhập đầy đủ các trường thông tin!"
        }, 400
    name = name.strip()
    if len(name) < 3 or len(name) > 50:
        return {
            "message": "Tên lớp thi phải từ 3 tới 50 ký tự!"
        }, 400
    try:
        start = parser.parse(start)
    except:
        return {
            "message": "Thời gian bắt đầu thi không đúng định dạng!"
        }, 400
    last = int(last)
    if last < 5 and last > 3600:
        return {
            "message": "Thời gian thi phải từ 5 phút tới 3600 phút!"
        }, 400
    result = mongo.db.classes.insert_one({
        "supervisor_id": current_user["_id"],
        "students": list(),
        "name": name,
        "start": start,
        "last": int(last),
        "end": None,
        "cheatings": list(),
        "settings": {
            "track_laptop": True,
            "track_mouse": True,
            "track_keyboard": True,
            "track_person": True
        },
        "status": CLASS_STATUS_ACTIVE
    })
    c = mongo.db.classes.find_one_or_404({"_id": ObjectId(result.inserted_id)})
    standardize_json(c)
    return json_util.dumps(c)


@app.route("/classes/<id>", methods=["PUT"])
@token_required(role=("supervisor",))
def update_class(current_user, id):
    data = request.data
    data = json.loads(data)
    name = data.get("name", None)
    start = data.get("start", None)
    last = data.get("last", None)
    settings = data.get("settings", None)
    name = name.strip() if name else None
    if name and (len(name) < 3 or len(name) > 50):
        return {
            "message": "Tên lớp thi phải từ 3 tới 50 ký tự!"
        }, 400
    if start:
        try:
            start = parser.parse(start)
        except:
            return {
                "message": "Thời gian bắt đầu thi không đúng định dạng!"
            }, 400
    last = int(last) if last else None
    if last and (last < 5 and last > 3600):
        return {
            "message": "Thời gian thi phải từ 5 phút tới 3600 phút!"
        }, 400
    if settings:
        for attr in ('track_laptop', 'track_mouse', 
            'track_keyboard', 'track_person'):
            if type(settings.get(attr, None)) != bool:
                return {
                    "message": "Cấu hình giám sát không hợp lệ!"
                }, 400
    update_obj = dict()
    if name is None and start is None and last is None and settings is None:
        return {
            "message": "Vui lòng nhập thông tin để cập nhật!"
        }, 400
    if name: update_obj["name"] = name
    if start: update_obj["start"] = start
    if last: update_obj["last"] = int(last)
    if settings: update_obj["settings"] = settings
    result = mongo.db.classes.update_one({
            "_id": ObjectId(id),
            "supervisor_id": current_user["_id"]
        }, {
            "$set": update_obj
        })
    class_ = mongo.db.classes.find_one_or_404({
        "_id": ObjectId(id),
        "supervisor_id": current_user["_id"]
    })
    standardize_json(class_)
    return json_util.dumps(class_)


@app.route("/classes/<id>", methods=["DELETE"])
@token_required(role=("supervisor",))
def delete_class(current_user, id):
    # result = mongo.db.classes.delete_one({"_id": ObjectId(id)})
    # deactivate the account instead of actually delete
    class_ = mongo.db.classes.find_one_or_404({
        "_id": ObjectId(id),
        "supervisor_id": current_user["_id"]
    })
    result = mongo.db.classes.update_one({
            "_id": ObjectId(id),
            "supervisor_id": current_user["_id"]
        }, {
            "$set": {
                "status": CLASS_STATUS_DELETED
            }
        })
    return json_util.dumps(result.raw_result)


@app.route("/classes/add_students/<id>", methods=["PUT"])
@token_required(role=("supervisor",))
def add_students_to_class(current_user, id):
    data = request.data
    data = json.loads(data)
    class_ = mongo.db.classes.find_one({
        "_id": ObjectId(id),
        "supervisor_id": current_user["_id"],
        "status": CLASS_STATUS_ACTIVE
    })
    if class_ is None:
        return {
            "message": "Không tìm được lớp!"
        }, 404
    emails = data.get("emails", None)
    if not emails or type(emails) != list:
        return {
            "message": "Danh sách email học sinh cần thêm không đúng định dạng!"
        }, 400
    ids = list()
    for email in emails:
        if not validate_email(email):
            return {
                "message": "Email %s không đúng định dạng!" % (email)
            }, 400
        student = mongo.db.users.find_one({
                "email": email,
                "status": USER_STATUS_ACTIVE,
                "role": USER_ROLE_STUDENT
            }, {
                "_id": 1
            })
        if student is None:
            return {
                "message": "Không tìm thấy học sinh với email %s!" % (email)
            }, 404
        ids.append(student["_id"]);
    ids.extend(class_["students"])
    ids = list(set(ids))
    if ids == class_["students"]:
        return {
            "message": "Các email đã tồn tại!"
        }, 401
    result = mongo.db.classes.update_one({
            "_id": ObjectId(id),
            "supervisor_id": current_user["_id"],
            "status": CLASS_STATUS_ACTIVE
        }, {
            "$set": {
                "students": ids
            }
        })
    return {
        "message": "Thành công!"
    }, 200


@app.route("/classes/delete_student", methods=["DELETE"])
@token_required(role=("supervisor",))
def delete_students_in_class(current_user):
    data = request.data
    data = json.loads(data)
    class_id = data.get("class_id", None)
    student_id = data.get("student_id", None)
    if class_id is None or student_id is None:
        return {
            "message": "Vui lòng nhập đủ thông tin!"
        }, 400
    class_ = mongo.db.classes.find_one({
        "_id": ObjectId(class_id),
        "supervisor_id": current_user["_id"],
        "status": CLASS_STATUS_ACTIVE
    })
    if class_ is None:
        return {
            "message": "Không tìm được lớp!"
        }, 404
    if ObjectId(student_id) in class_["students"]:
        class_["students"].remove(ObjectId(student_id))
        result = mongo.db.classes.update_one({
            "_id": ObjectId(class_id),
            "supervisor_id": current_user["_id"],
            "status": CLASS_STATUS_ACTIVE
        }, {
            "$set": {
                "students": class_["students"]
            }
        })
    else:
        return {
            "message": "Không tìm được học sinh!"
        }, 404
    return {
        "message": "Thành công!"
    }, 200


@app.route("/student/classes", methods=["GET"])
@token_required(role=("student"))
def get_list_classes_student(current_user):
    query = request.args
    first, last = None, None
    q_range = query.get("range")
    if q_range:
        q_range = json.loads(q_range)
        first, last = q_range
    q_search = None
    q_filter = query.get("filter")
    if q_filter:
        q_filter = json.loads(q_filter)
        if "q" in q_filter:
            q_search = q_filter["q"]
    aggregation = [{
        "$lookup": {
            "from": "classes",
            "localField": "class_id",
            "foreignField": "_id",
            "as": "class"
        }},
        {"$lookup": {
            "from": "users",
            "localField": "class.supervisor_id",
            "foreignField": "_id",
            "as": "supervisor"
        }},
        {'$match': {
            'student_id': current_user["_id"],
            'class.status': CLASS_STATUS_ACTIVE
        }}
    ]
    classes = mongo.db.student_class.aggregate(aggregation)
    return_classes = list()
    for class_ in classes:
        class_["class"] = class_["class"][0]
        class_["supervisor"] = class_["supervisor"][0]
        if (q_search is None) or \
           (class_["class"]["name"].lower().find(q_search.lower()) != -1) or \
           (class_["supervisor"]["name"].lower().find(q_search.lower()) != -1) or \
           (class_["supervisor"]["email"].lower().find(q_search.lower()) != -1):
            class_["supervisor"]["id"] = str(class_["supervisor"]["_id"])
            del class_["supervisor"]["_id"]
            del class_["supervisor"]["last_updated"]
            del class_["supervisor"]["password"]
            del class_["supervisor"]["updated_by"]
            return_classes.append({
                "id": str(class_["class"]["_id"]),
                "supervisor": class_["supervisor"],
                "start": class_["class"]["start"],
                "last": class_["class"]["last"],
                "end": class_["class"]["end"] if class_["class"]["end"] else None,
                "settings": class_["class"]["settings"],
                "name": class_["class"]["name"]
            })     
    count_classes = len(return_classes)
    if first is not None and last is not None:
        return_classes = return_classes[first:last]
    return json_util.dumps({
        "data": return_classes,
        "count": count_classes
    })