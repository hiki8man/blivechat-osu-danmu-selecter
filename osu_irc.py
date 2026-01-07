import socket
import time
import logging

from info_api import get_info as get_beatmap_info
import asyncio
import config
from typing import Optional


logger = logging.getLogger('osu-irc-client')

class AsyncIRCClient:
    def __init__(self, host: str, port: int, nick: str, realname: str = None, password: str = None):
        self.host = host
        self.port = port
        self.nick = nick
        self.realname = realname or nick
        self.password = password
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.running = True
        self._connected = asyncio.Event()

    async def connect(self):
        """长连接主循环"""
        while self.running:
            try:
                logger.info(f"IRC: 连接到 {self.host}:{self.port}")
                self.reader, self.writer = await asyncio.open_connection(self.host, self.port)

                # 认证
                if self.password:
                    self.writer.write(f"PASS {self.password}\r\n".encode())
                self.writer.write(f"NICK {self.nick}\r\n".encode())
                self.writer.write(f"USER {self.nick} 0 * :{self.realname}\r\n".encode())
                await self.writer.drain()

                # 等待欢迎消息（表示登录成功）
                async for line in self.reader:
                    msg = line.decode(errors='ignore').strip()
                    if msg.startswith("PING"):
                        token = msg.split()[1]
                        await self._send_raw(f"PONG {token}")
                    elif "001" in msg:  # RPL_WELCOME
                        logger.info("IRC: 登录成功")
                        self._connected.set()
                        break

                # 进入主消息循环
                await self._message_loop()

            except Exception as e:
                logger.error(f"IRC 连接错误: {e}")
                if self.running:
                    await asyncio.sleep(5)
            finally:
                self._connected.clear()
                if self.writer:
                    self.writer.close()
                    await self.writer.wait_closed()

    async def _message_loop(self):
        """处理 IRC 消息（保持连接）"""
        assert self.reader is not None
        async for line in self.reader:
            msg = line.decode(errors='ignore').strip()
            if msg.startswith("PING"):
                token = msg.split()[1]
                await self._send_raw(f"PONG {token}")

    async def _send_raw(self, message: str):
        if self.writer:
            self.writer.write(f"{message}\r\n".encode())
            await self.writer.drain()

    async def send_privmsg(self, target: str, message: str):
        """发送私聊或频道消息"""
        if not self._connected.is_set():
            logger.warning("IRC: 尚未连接，无法发送消息")
            return
        # 速率限制：ppy说每5秒最多10条消息
        await asyncio.sleep(0.5)
        await self._send_raw(f"PRIVMSG {target} :{message}")
        logger.info(f"IRC: -> {target}: {message}")

    async def close(self):
        self.running = False
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()

async def send_beatmap_url(irc_client:AsyncIRCClient, mapid:str, user_name:str) -> None:
    beatmapinfo:dict|None = await get_beatmap_info(mapid[0], int(mapid[1:]), config.API_SERVER)
    if beatmapinfo:
        logger.info(f"谱面信息：{beatmapinfo}")
        map_url:str = beatmapinfo["url"]
        sid = beatmapinfo["sid"]
        beatmap_msg = " ".join([f"【{user_name}】点歌：[{map_url} {beatmapinfo["artist"]} - {beatmapinfo["title"]}]",
                                f"Sayo分流：[https://osu.sayobot.cn/home?search={sid} osu.sayobot.cn]",
                                f"kitsu分流：[https://osu.direct/beatmapsets/{sid} osu.direct]",
                                ])
    else:
        # 如果无法正常获取谱面信息则直接返回链接，不考虑正确性
        beatmap_msg = f"【{user_name}】点歌：https://osu.ppy.sh/{mapid[0]}/{mapid[1:]}"
    logger.info("正在发送信息")
    
    target_name = config.USER_NAME if config.SEND_SELF else "BanchoBot"
    await send_msg(irc_client, beatmap_msg, target_name)

async def send_msg(irc_client:AsyncIRCClient, msg:str, target_name:str, is_action:bool=False):
    # 给自己发送消息
    if is_action:
        msg = f"\x01ACTION {msg}\x01"
    await irc_client.send_privmsg(target_name, msg)