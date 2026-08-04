import socket
import time
import logging

from info_api import get_info as get_beatmap_info
import asyncio
import config
from typing import Optional
from asyncio import Queue

from dataclasses import dataclass

from enum import StrEnum

logger = logging.getLogger('osu-requests-bot.' + __name__)

@dataclass
class IRCMessage:
    target: str
    message: str
    
class IRCCodes(StrEnum):
    WELCOME = "001"
    BAD_AUTH = "464"
    USERNAME_ERROR = "372"

class AsyncIRCClient:
    def __init__(self, 
                 host: str, port: int, 
                 nick: str, realname: Optional[str] = None, password: str = "", 
                 shut_down_event: Optional[asyncio.Event] = None):
        # IRC 服务器配置
        self.host = host
        self.port = port
        
        # IRC 用户登录信息
        self.nick = nick
        self.realname = realname or nick 
        self.password = password

        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        
        self.running = True
        self._connected = asyncio.Event()
        # 关闭事件
        self.shut_down_event = shut_down_event
        
        self._archive_task: Optional[asyncio.Task] = None
        self._privmsg_task: Optional[asyncio.Task] = None

        self.message_queue: Queue[IRCMessage] = asyncio.Queue()

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

                    elif IRCCodes.WELCOME in msg:
                        logger.info("IRC: 登录成功")
                        self._connected.set()
                        break
                    
                    elif IRCCodes.BAD_AUTH in msg:
                        self.running = False
                        raise ValueError("密码错误")

                    elif IRCCodes.USERNAME_ERROR in msg:
                        self.running = False
                        raise ValueError("用户名错误")

                # 创建私聊消息处理任务循环
                if self._privmsg_task is None or self._privmsg_task.done():
                    self._privmsg_task = asyncio.create_task(self._privmsg_loop())

                # 进入主消息循环
                self._archive_task = asyncio.create_task(self._archive_loop())
                await self._archive_task

            except Exception as e:
                logger.error(f"IRC 连接错误: {e}")
                if self.running:
                    await asyncio.sleep(5)
            finally:
                self._connected.clear()
                if self.writer:
                    self.writer.close()
                    await self.writer.wait_closed()
        
        # 插件退出
        if self.shut_down_event:
            self.shut_down_event.set()

    async def _archive_loop(self):
        """处理 IRC 消息（保持连接）"""
        assert self.reader is not None
        async for line in self.reader:
            msg = line.decode(errors='ignore').strip()
            if msg.startswith("PING"):
                token = msg.split()[1]
                await self._send_raw(f"PONG {token}")
                
    async def _privmsg_loop(self):
        """处理消息队列"""
        while self.running:
            try:
                message = await self.message_queue.get()
            except asyncio.CancelledError:
                logger.info("消息队列已取消")
                break
            try:
                await self._connected.wait()
                await self._send_raw(f"PRIVMSG {message.target} :{message.message}")
                logger.info(f"IRC: -> {message.target}: {message.message}")
            except Exception as e:
                logger.error(f"处理消息队列时出错: {e}")
            finally:
                self.message_queue.task_done()
                await asyncio.sleep(0.5)  # 速率限制：ppy说每5秒最多10条消息
            

    async def _send_raw(self, message: str):
        if self.writer:
            self.writer.write(f"{message}\r\n".encode())
            await self.writer.drain()

    async def send_privmsg(self, target: str, message: str):
        """发送私聊或频道消息"""
        if not self._connected.is_set():
            logger.warning("IRC: 尚未连接，无法发送消息")
            return
        await self.message_queue.put(IRCMessage(target=target, message=message)) 

    async def close(self):
        self.running = False
        task_list = [self._archive_task, self._privmsg_task]
        for task in task_list:
            if task: task.cancel()
        
        # 等待所有任务完成取消
        await asyncio.gather(*[task for task in task_list if task], return_exceptions=True)

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