# coding: utf-8

# This file is part of Supysonic.
#
# Supysonic is a Python implementation of the Subsonic server API.
# Copyright (C) 2013  Alban 'spl0k' Féron
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import string, random, hashlib
import uuid

from db import User, session
from web import app

class UserManager:
    SUCCESS = 0
    INVALID_ID = 1
    NO_SUCH_USER = 2
    NAME_EXISTS = 3
    WRONG_PASS = 4

    @staticmethod
    def get(uid):
        if type(uid) in (str, unicode):
            try:
                uid = uuid.UUID(uid)
            except:
                return UserManager.INVALID_ID, None
        elif type(uid) is uuid.UUID:
            pass
        else:
            return UserManager.INVALID_ID, None

        user = session.query(User).get(uid)
        if user is None:
            return UserManager.NO_SUCH_USER, None

        return UserManager.SUCCESS, user

    @staticmethod
    def add(name, password, mail, admin):
        if session.query(User).filter(User.name == name).first():
            return UserManager.NAME_EXISTS

        password = UserManager.__decode_password(password)
        crypt = UserManager.__encrypt_password(password)
        user = User(name = name, mail = mail, password = crypt, admin = admin)
        session.add(user)
        session.commit()

        return UserManager.SUCCESS

    @staticmethod
    def delete(uid):
        status, user = UserManager.get(uid)
        if status != UserManager.SUCCESS:
            return status

        session.delete(user)
        session.commit()

        return UserManager.SUCCESS

    @staticmethod
    def try_auth(name, password):
        password = UserManager.__decode_password(password)
        user = session.query(User).filter(User.name == name).first()
        if not user:
            return UserManager.NO_SUCH_USER, None
        elif hashlib.sha1(password).digest() != user.password:
            return UserManager.WRONG_PASS, None
        else:
            return UserManager.SUCCESS, user

    @staticmethod
    def change_password(uid, old_pass, new_pass):
        status, user = UserManager.get(uid)
        if status != UserManager.SUCCESS:
            return status

        old_pass = UserManager.__decode_password(old_pass)
        new_pass = UserManager.__decode_password(new_pass)

        if UserManager.__encrypt_password(old_pass) != user.password:
            return UserManager.WRONG_PASS

        user.password = UserManager.__encrypt_password(new_pass)
        session.commit()
        return UserManager.SUCCESS

    @staticmethod
    def change_password2(name, new_pass):
        user = session.query(User).filter(User.name == name).first()
        if not user:
            return UserManager.NO_SUCH_USER

        new_pass = UserManager.__decode_password(new_pass)
        user.password = UserManager.__encrypt_password(new_pass)
        session.commit()
        return UserManager.SUCCESS

    @staticmethod
    def error_str(err):
        if err == UserManager.SUCCESS:
            return 'No error'
        elif err == UserManager.INVALID_ID:
            return 'Invalid user id'
        elif err == UserManager.NO_SUCH_USER:
            return 'No such user'
        elif err == UserManager.NAME_EXISTS:
            return 'There is already a user with that name'
        elif err == UserManager.WRONG_PASS:
            return 'Wrong password'
        else:
            return 'Unkown error'

    @staticmethod
    def __encrypt_password(password):
        return hashlib.sha1(password).digest()

    @staticmethod
    def __decode_password(password):
        if not password.startswith('enc:'):
            return password

        enc = password[4:]
        ret = ''
        while enc:
            ret = ret + chr(int(enc[:2], 16))
            enc = enc[2:]

        return ret
