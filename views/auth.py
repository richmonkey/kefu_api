# -*- coding: utf-8 -*-
from flask import request, Blueprint, g
import random
import json
import time
import requests
import urllib
import logging
import base64
import md5
from datetime import datetime
from functools import wraps

from libs.util import make_response

from models import user
from models import token
from models.seller import Seller
import config

app = Blueprint('auth', __name__)


def INVALID_PARAM():
    e = {"error":"非法输入"}
    logging.warn("非法输入")
    return make_response(400, e)


def INVALID_USER():
    e = {"error":"非法的用户名或密码"}
    logging.warn("非法的用户名或密码")
    return make_response(400, e)
    
def INVALID_REFRESH_TOKEN():
    e = {"error":"非法的refresh token"}
    logging.warn("非法的refresh token")
    return make_response(400, e)
 
    
def CAN_NOT_GET_TOKEN():
    e = {"error":"获取imsdk token失败"}
    logging.warn("获取imsdk token失败")
    return make_response(400, e)

    
@app.route("/auth/token", methods=["POST"])
def access_token():
    if not request.data:
        return INVALID_PARAM()

    obj = json.loads(request.data)
    username = obj["username"]
    password = obj["password"]

    if not username or not password:
        return INVALID_PARAM()

    password = md5.new(password).hexdigest()
    db = g._db

    uid = None
    store_id = None
    seller = Seller.get_seller_with_number(db, username)
    if seller and seller['password'] == password:
        uid = seller['id']
        store_id = seller['store_id']
    else:
        try:
            seller_id = int(username)
            seller = Seller.get_seller(db, seller_id)
            if seller and seller['password'] == password:
                uid = seller['id']
                store_id = seller['store_id']
        except ValueError:
            pass
            
    if not uid:
        return INVALID_USER()

    access_token = login_gobelieve(uid, "", config.APP_ID, config.APP_SECRET)
        
    if not access_token:
        return CAN_NOT_GET_TOKEN()

    u0 = user.get_user(g.rds, uid)
    u = user.User()
    u.uid = uid
    user.save_user(g.rds, u)

    tok = create_token(3600, True)
    tok['uid'] = uid
    tok['store_id'] = store_id
    tok['access_token'] = access_token
    tok['name'] = seller['name']

    t = token.AccessToken(**tok)
    t.save(g.rds)
    t = token.RefreshToken(**tok)
    t.save(g.rds)

    print "token:", tok
    return make_response(200, tok)


@app.route("/auth/refresh_token", methods=["POST"])
def refresh_token():
    if not request.data:
        return INVALID_PARAM()

    db = g._db
    obj = json.loads(request.data)
    refresh_token = obj["refresh_token"]
    rt = token.RefreshToken()
    if not rt.load(g.rds, refresh_token):
        return INVALID_REFRESH_TOKEN()

    access_token = login_gobelieve(int(rt.user_id), "", config.APP_ID, config.APP_SECRET)
        
    if not access_token:
        return CAN_NOT_GET_TOKEN()

    seller = Seller.get_seller(db, rt.user_id)
    tok = create_token(3600, False)
    tok["refresh_token"] = obj["refresh_token"]
    tok["access_token"] = access_token
    tok['uid'] = rt.user_id
    tok['store_id'] = seller['store_id']
    tok['name'] = seller['name']

    t = token.AccessToken(**tok)
    t.user_id = rt.user_id
    t.save(g.rds)
    
    return make_response(200, tok)



def login_gobelieve(uid, uname, appid, appsecret):
    url = config.GOBELIEVE_URL + "/auth/grant"
    obj = {"uid":uid, "user_name":uname}

    m = md5.new(appsecret)
    secret = m.hexdigest()
    basic = base64.b64encode(str(appid) + ":" + secret)

    headers = {'Content-Type': 'application/json; charset=UTF-8',
               'Authorization': 'Basic ' + basic}
     
    res = requests.post(url, data=json.dumps(obj), headers=headers)
    if res.status_code != 200:
        logging.warning("login error:%s %s", res.status_code, res.text)
        return None

    obj = json.loads(res.text)
    return obj["data"]["token"]



UNICODE_ASCII_CHARACTER_SET = ('abcdefghijklmnopqrstuvwxyz'
                               'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
                               '0123456789')

def random_token_generator(length=30, chars=UNICODE_ASCII_CHARACTER_SET):
    rand = random.SystemRandom()
    return ''.join(rand.choice(chars) for x in range(length))

def create_token(expires_in, refresh_token=False):
    """Create a BearerToken, by default without refresh token."""

    token = {
        'access_token': random_token_generator(),
        'expires_in': expires_in,
        'token_type': 'Bearer',
    }
    if refresh_token:
        token['refresh_token'] = random_token_generator()

    return token
