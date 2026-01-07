# -*- coding: utf-8 -*-
import os

# ===不要改这三个PATH===
BASE_PATH = os.path.dirname(os.path.realpath(__file__))
LOG_PATH = os.path.join(BASE_PATH, 'log')
CONFIG_PATH = os.path.join(BASE_PATH, 'config.py')

# ===用户配置===
USER_NAME = "set you osu name" # 用户名
PASSWORD = "get your irc password" # irc密码
API_SERVER = "osu_html" # 获取谱面方式，默认从官网获取
SEND_SELF:bool = True # 是否转发给自己，lazer请设置为false让消息转发给BanchoBot