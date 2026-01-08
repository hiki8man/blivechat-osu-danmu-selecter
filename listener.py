# -*- coding: utf-8 -*-
import datetime
import logging
import os
import sys
from typing import *

import blcsdk
import blcsdk.models as sdk_models
import config
import asyncio
from osu_irc import send_beatmap_url
import re
from osu_irc import AsyncIRCClient
import subprocess

logger = logging.getLogger('osu-requests-bot.' + __name__)

_msg_handler: Optional['MsgHandler'] = None
_id_room_dict: Dict[int, 'Room'] = {}

_irc_client: Optional[AsyncIRCClient] = None

async def init(irc_client: Optional[AsyncIRCClient] = None, event:asyncio.Event|None = None):
    global _msg_handler
    _msg_handler = MsgHandler()
    blcsdk.set_msg_handler(_msg_handler)

    global _shut_down_event
    _shut_down_event = event
    
    global _irc_client
    _irc_client = irc_client

    # 创建已有的房间。这一步失败了也没关系，只是有消息时才会创建文件
    try:
        blc_rooms = await blcsdk.get_rooms()
        for blc_room in blc_rooms:
            if blc_room.room_id is not None:
                _get_or_add_room(blc_room.room_id)
    except blcsdk.SdkError:
        pass


def shut_down():
    blcsdk.set_msg_handler(None)
    while len(_id_room_dict) != 0:
        room_id = next(iter(_id_room_dict))
        _del_room(room_id)

def get_mapid(danmu_text:str) -> str|None:
    # 收到明确表名为sid或bid
    match = re.match(r"^(?:点歌[\s]?/?)?([bBsS]\d+)",danmu_text)
    if match:
        return match.group(1).lower()

    # 只发了纯数字，处理为bid
    match = re.match(r"^点歌[\s]?/?(\d+)",danmu_text)
    if match:
        return f"b{match.group(1)}"

class MsgHandler(blcsdk.BaseHandler):
    def on_client_stopped(self, client: blcsdk.BlcPluginClient, exception: Optional[Exception]):
        logger.info('blivechat disconnected')
        global _shut_down_event
        _shut_down_event.set()

    def _on_open_plugin_admin_ui(
        self, client: blcsdk.BlcPluginClient, message: sdk_models.OpenPluginAdminUiMsg, extra: sdk_models.ExtraData
    ):
        if sys.platform == 'win32':
            subprocess.run(["notepad.exe", config.CONFIG_PATH])
        else:
            logger.info('Config path is "%s"', config.CONFIG_PATH)

    def _on_room_init(
        self, client: blcsdk.BlcPluginClient, message: sdk_models.RoomInitMsg, extra: sdk_models.ExtraData
    ):
        if extra.is_from_plugin:
            return
        if message.is_success:
            _get_or_add_room(extra.room_id)

    def _on_del_room(self, client: blcsdk.BlcPluginClient, message: sdk_models.DelRoomMsg, extra: sdk_models.ExtraData):
        if extra.is_from_plugin:
            return
        if extra.room_id is not None:
            _del_room(extra.room_id)

    def _on_add_text(self, client: blcsdk.BlcPluginClient, message: sdk_models.AddTextMsg, extra: sdk_models.ExtraData):
        if extra.is_from_plugin:
            return
        map_id = get_mapid(message.content)
        if map_id:
            room = _get_or_add_room(extra.room_id)
            room.log(f"{message.author_name}发送了点歌请求：{map_id}")
            if _irc_client:
                asyncio.create_task(send_beatmap_url(_irc_client, str(map_id), message.author_name))

    def _on_add_super_chat(
        self, client: blcsdk.BlcPluginClient, message: sdk_models.AddSuperChatMsg, extra: sdk_models.ExtraData
    ):
        if extra.is_from_plugin:
            return
        map_id = get_mapid(message.content)
        if map_id:
            room = _get_or_add_room(extra.room_id)
            room.log(f"{message.author_name} 发送了 {message.price} 元的点歌请求：{map_id}")
            if _irc_client:
                asyncio.create_task(send_beatmap_url(_irc_client, str(map_id), message.author_name))

def _get_or_add_room(room_id):
    room = _id_room_dict.get(room_id, None)
    if room is None:
        if room_id is None:
            raise TypeError('room_id is None')
        room = _id_room_dict[room_id] = Room(room_id)
    return room


def _del_room(room_id):
    room = _id_room_dict.pop(room_id, None)
    if room is not None:
        room.close()


class Room:
    def __init__(self, room_id):
        cur_time = datetime.datetime.now()
        time_str = cur_time.strftime('%Y%m%d_%H%M%S')
        filename = f'room_{room_id}-{time_str}.txt'
        self._file = open(os.path.join(config.LOG_PATH, filename), 'a', encoding='utf-8-sig')

    def close(self):
        self._file.close()

    def log(self, content):
        cur_time = datetime.datetime.now()
        time_str = cur_time.strftime('%Y-%m-%d %H:%M:%S')
        text = f'{time_str} {content}\n'
        self._file.write(text)
        self._file.flush()