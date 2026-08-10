import asyncio
import logging
import time
from asyncio import Queue
from dataclasses import dataclass
from enum import StrEnum

import config
from info_api import get_info as get_beatmap_info

logger = logging.getLogger('osu-requests-bot.' + __name__)

@dataclass
class IRCMessage:
    target: str
    message: str
    
class IRCCodes(StrEnum):
    WELCOME = "001"
    BAD_AUTH = "464"
    USERNAME_ERROR = "372"

class IRCUserNameError(ValueError):
    pass

class IRCBadAuthError(ValueError):
    pass

class IRCNetWorkError(RuntimeError):
    pass

class AsyncIRCClient:
    def __init__(self, 
                 host: str, port: int, 
                 nick: str, realname: str | None = None, password: str = "",
                 shut_down_event: asyncio.Event | None = None):
        # IRC 服务器配置
        self.host: str = host
        self.port: int = port
        
        # IRC 用户登录信息
        self.nick: str = nick.replace(" ", "_")
        self.realname: str = (realname or nick).replace(" ", "_")
        self.password: str = password

        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None

        self.running: bool = True
        self._connected: asyncio.Event = asyncio.Event()
        self.shut_down_event: asyncio.Event | None = shut_down_event # 关闭事件
        
        self._archive_task: asyncio.Task | None = None
        self._privmsg_task: asyncio.Task | None = None

        self.message_queue: Queue[IRCMessage] = asyncio.Queue()
        self._last_disconnect_warn: float = 0.0  # 断连警告节流时间戳

    async def connect(self):
        """长连接主循环"""
        while self.running:
            try:
                logger.info("IRC: 连接到 %s:%s", self.host, self.port)
                self.reader, self.writer = await asyncio.open_connection(self.host, self.port)

                # 等待欢迎消息（表示登录成功）
                await self._login()

                # 创建私聊消息处理任务循环
                if self._privmsg_task is None or self._privmsg_task.done():
                    self._privmsg_task = asyncio.create_task(self._privmsg_loop())

                # 进入主消息循环
                self._archive_task = asyncio.create_task(self._archive_loop())
                await self._archive_task

            except IRCNetWorkError:
                logger.info("IRC: 断开连接，正在重连...")
                if self.running: await asyncio.sleep(5)
                
            except (IRCUserNameError, IRCBadAuthError):
                logger.error("IRC: 用户名或密码错误，登录失败")
                break

            except Exception:
                logger.exception("IRC: 连接错误")
                if self.running: await asyncio.sleep(5)

            finally:
                self._connected.clear()
                if self.writer:
                    self.writer.close()
                    await self.writer.wait_closed()
        
        # 插件退出
        # [TODO] 改为控制GUI内部状态
        if self.shut_down_event:
            self.shut_down_event.set()
    async def _login(self):
        """尝试登录"""
        
        assert isinstance(self.writer, asyncio.StreamWriter)

        # 认证
        if self.password:
            self.writer.write(f"PASS {self.password}\r\n".encode())
        self.writer.write(f"NICK {self.nick}\r\n".encode())
        self.writer.write(f"USER {self.nick} 0 * :{self.realname}\r\n".encode())
        await self.writer.drain()
        
        while self.running:
            msg = await self._get_msg()

            if IRCCodes.BAD_AUTH in msg:
                raise IRCBadAuthError
            
            if IRCCodes.USERNAME_ERROR in msg:
                raise IRCUserNameError
            
            if IRCCodes.WELCOME in msg:
                logger.info("IRC: 登录成功")
                self._connected.set()
                break

    async def _get_msg(self) -> str:
        assert isinstance(self.reader, asyncio.StreamReader)
        while self.running:
            line = await self.reader.readline()
            if line == b"":
                raise IRCNetWorkError
            
            msg = line.decode(errors='ignore').strip()

            if msg.startswith("PING"):
                logger.debug("IRC: <- %s", msg)
                parts = msg.split()
                if len(parts) >= 2:
                    token = parts[1]
                    await self._send_raw(f"PONG {token}")
                continue

            return msg

        return ""

    async def _archive_loop(self):
        """处理 IRC 消息（保持连接）"""
        while self.running:
            msg = await self._get_msg()
            logger.debug("IRC Get: %s", msg)
                
    async def _privmsg_loop(self):
        """处理消息队列"""
        while self.running:
            try:
                message = await self.message_queue.get()
            except asyncio.CancelledError:
                logger.debug("消息队列已取消")
                break
            try:
                await self._connected.wait()
                await self._send_raw(f"PRIVMSG {message.target} :{message.message}")
            except Exception:
                logger.exception("处理消息队列时出错")
            finally:
                self.message_queue.task_done()
                await asyncio.sleep(0.5)  # 速率限制：ppy说每5秒最多10条消息

    async def _send_raw(self, message: str):
        if self.writer:
            self.writer.write(f"{message}\r\n".encode())
            logger.debug("IRC Post: %s", message)
            await self.writer.drain()

    async def send_privmsg(self, target: str, message: str):
        """发送私聊或频道消息"""
        if not self._connected.is_set():
            now = time.monotonic()
            if now - self._last_disconnect_warn > 10:
                logger.warning("IRC: 尚未连接，无法发送消息")
                self._last_disconnect_warn = now
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
        logger.debug("谱面信息：%s", beatmapinfo)
        map_url:str = beatmapinfo["url"]
        sid = beatmapinfo["sid"]
        beatmap_msg = " ".join([f"【{user_name}】点歌：[{map_url} {beatmapinfo["artist"]} - {beatmapinfo["title"]}]",
                                f"Sayo分流：[https://osu.sayobot.cn/home?search={sid} osu.sayobot.cn]",
                                f"kitsu分流：[https://osu.direct/beatmapsets/{sid} osu.direct]",
                                ])
    else:
        # 如果无法正常获取谱面信息则直接返回链接，不考虑正确性
        beatmap_msg = f"【{user_name}】点歌：https://osu.ppy.sh/{mapid[0]}/{mapid[1:]}"
    logger.debug("正在发送信息到Osu IRC")
    
    target_name = config.USER_NAME if config.SEND_SELF else "BanchoBot"
    await send_msg(irc_client, beatmap_msg, target_name)

async def send_msg(irc_client:AsyncIRCClient, msg:str, target_name:str, is_action:bool=False):
    # 给自己发送消息
    if is_action:
        msg = f"\x01ACTION {msg}\x01"
    await irc_client.send_privmsg(target_name, msg)