import jwt
from flask import request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, timedelta
from bson.objectid import ObjectId
from .constants import TOKEN_EXPIRED_DAYS, USER_ROLE_ADMIN, \
    USER_ROLE_STUDENT, USER_ROLE_SUPERVISOR
from .. import app, mongo


def token_required(role="all"):
    def decorated(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            token = None
            # jwt is passed in the request header
            if 'x-access-token' in request.headers:
                token = request.headers['x-access-token']
            # return 401 if token is not passed
            if not token:
                return jsonify({'message' : 'Chưa có token!'}), 401
            try:
                # decoding the payload to fetch the stored details
                data = decode_token(token)
                if datetime.fromtimestamp(data["exp"]) < datetime.utcnow():
                    return jsonify({
                        'message' : 'Token đã hết hạn!'
                    }), 401
                current_user = mongo.db.users.find_one({
                    "_id": ObjectId(data["user_id"])
                })
                if current_user is None:
                    return jsonify({
                        'message' : 'Token không chính xác!'
                    }), 401
                user_role = int(current_user["role"])
                if ("all" in role):
                    pass
                elif ("admin" not in role and user_role == USER_ROLE_ADMIN) or \
                    ("supervisor" not in role and user_role == USER_ROLE_SUPERVISOR) or \
                    ("student" not in role and user_role == USER_ROLE_STUDENT):
                    print("wrong")
                    return jsonify({
                        'message' : 'No permission!'
                    }), 403
            except Exception as e:
                print(e)
                return jsonify({
                    'message' : 'Token không chính xác!'
                }), 401
            # returns the current logged in users context to the routes
            return f(current_user, *args, **kwargs)
        return wrapper
    return decorated


def make_token(user_id):
    token = jwt.encode({
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(days=TOKEN_EXPIRED_DAYS)
    }, app.config["SECRET_KEY"])
    return token


def decode_token(token):
    data = jwt.decode(token, app.config["SECRET_KEY"])
    return data


def hash_password(password):
    return generate_password_hash(password)


def check_password(true_password, enter_password):
    return check_password_hash(true_password, enter_password)
