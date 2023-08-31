"""
    SiteCookie：读取浏览器cookie以供操作BWiki API
"""
import os
import json
import sqlite3
import warnings
from pathlib import Path

from base64 import b64decode
from win32crypt import CryptUnprotectData
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class CookieGetter:
    """
    读取浏览器cookie以供操作BWiki API。仅支持Windows下的Chrome和新版Edge

    从浏览器获取 .biligame.com 的SESSDATA Cookie，者可以用于操作API。

    相当于自动化了用户手动复制Cookie的步骤。

    *注意*：此Cookie关系BWiki账号安全，请勿泄露给任何人，包括B站工作人员。

    *注意*：这不是值得提倡的做法。由于BWiki没提供常规API登录方式，决定用此下策。
    另一种方案是账户密码登陆，这会使用B站账户密码，我们更不提倡模拟登录B站
    """

    @staticmethod
    def get(browser: str, wiki: str = ""):
        """ 从浏览器数据库提取cookie
            目标是：".biligame.com" 下 / 中的cookie

            可选：
            - wiki.biligame.com 下 /wiki_name/ 中的cookie
        """
        if not browser:
            raise ValueError("parameter 'browser' cannot be empty")

        cookies = {}
        cookies |= CookieGetter._get_cookie(browser, ".biligame.com", "/", "SESSDATA")

        # 可选，获取目标 wiki 的 cookie。但是实测仅需biligame的SESSDATA
        # cookies.update(_get_cookie(browser, "wiki.biligame.com", f"/{wiki}/"))
        return cookies

    # noinspection SqlResolve
    @staticmethod
    def _get_cookie(browser: str, host: str, path: str, name: str):
        """ 从浏览器数据库读取cookie，这不是值得提倡的方法。
        由于BWiki没提供常规API登录方式，相比于手动复制cookie，决定用此下策。
        :param browser: 浏览器
        :param host: 要获取cookie的域名
        :param path: 要获取那个路径下的cookie
        :param name: 要获取的cookie名
        :return: cookie dict
        """
        cookie_path = CookieGetter._get_cookie_path(browser)

        # query data from browser database
        # only query SESSDATA from "host/path"
        with sqlite3.connect(cookie_path) as conn:
            cursor = conn.cursor()
            sql = f"select name,encrypted_value from cookies where host_key=? and path=? and name='{name}'"
            data = cursor.execute(sql, [host, path]).fetchall()
            cursor.close()

        name, encrypted_value = data[0]
        value = CookieGetter._decode_cookie(browser, encrypted_value)

        return {name: value}

    @staticmethod
    def _decode_cookie(browser, encrypted_value):
        """ 解密 cookie 内容
        :param browser: 浏览器
        :param encrypted_value: Local State 数据库 cookies 表中的 encrypted_value
        :return: str：解密内容
        """
        if encrypted_value[:3] != b'v10':  # data is bytes
            warnings.warn(f"未知cookie编码。这可能导致cookie解析失败。详情：cookie 中的 encrypted_value 预期v10开头，实际是{encrypted_value[:5]}。")

        result = AESGCM(CookieGetter._get_key(browser)).decrypt(encrypted_value[3:15], encrypted_value[15:], None)
        result = result.decode("UTF8")
        return result

    @staticmethod
    def _get_key(browser):
        """ 从特定浏览器获取解密 cookie 的 key """
        local_state = CookieGetter._get_local_state_path(browser)
        state_data = Path(local_state).read_text("UTF8")
        key = json.loads(state_data)['os_crypt']['encrypted_key']
        key = CryptUnprotectData(b64decode(key)[5:])[1]
        return key

    @staticmethod
    def _get_cookie_path(browser: str):
        """ 获取指定浏览器的 Cookies 路径 """
        data = {
            "edge": r'\Microsoft\Edge\User Data\Default\Network\Cookies',
            "chrome": r'\Google\Chrome\User Data\Default\Network\Cookies',
        }
        return os.environ['LOCALAPPDATA'] + data[browser.lower()]

    @staticmethod
    def _get_local_state_path(browser: str):
        """ 获取指定浏览器的 Local State 路径 """
        data = {
            "edge": r'\Microsoft\Edge\User Data\Local State',
            "chrome": r'\Google\Chrome\User Data\Local State',
        }
        return os.environ['LOCALAPPDATA'] + data[browser.lower()]