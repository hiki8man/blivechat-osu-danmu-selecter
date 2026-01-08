#!/usr/bin/env python
# -*- coding: utf-8 -*-
import asyncio
import logging.handlers
import os
import signal
import sys
from typing import *

import blcsdk
import config
import listener
from osu_irc import AsyncIRCClient

logger = logging.getLogger('osu-requests-bot')

shut_down_event: Optional[asyncio.Event] = None
irc_client: Optional[AsyncIRCClient] = None
irc_task: Optional[asyncio.Task] = None

async def main():
    try:
        await init()
        await run()

    finally:
        await shut_down()
    return 0


async def init():
    init_signal_handlers()

    init_logging()

    await blcsdk.init()
    if not blcsdk.is_sdk_version_compatible():
        raise RuntimeError('SDK version is not compatible')
  # 初始化 IRC 客户端（长连接）
    global irc_client, irc_task
    if getattr(config, 'USER_NAME', None):
        irc_client = AsyncIRCClient(
            host="irc.ppy.sh",
            port=6667,
            nick=config.USER_NAME,
            password=config.PASSWORD
        )
        irc_task = asyncio.create_task(irc_client.connect())
        logger.info("IRC 客户端已启动")

    # 初始化 listener（传入 irc_client）
    await listener.init(irc_client=irc_client, event=shut_down_event)


def init_signal_handlers():
    global shut_down_event
    shut_down_event = asyncio.Event()

    signums = (signal.SIGINT, signal.SIGTERM)
    try:
        loop = asyncio.get_running_loop()
        for signum in signums:
            loop.add_signal_handler(signum, start_shut_down)
    except NotImplementedError:
        # 不太安全，但Windows只能用这个
        for signum in signums:
            signal.signal(signum, start_shut_down)


def start_shut_down(*_args):
    shut_down_event.set()


def init_logging():
    filename = os.path.join(config.LOG_PATH, 'msg-logging.log')
    stream_handler = logging.StreamHandler()
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename, encoding='utf-8', when='midnight', backupCount=7, delay=True
    )
    logging.basicConfig(
        format='{asctime} {levelname} [{name}]: {message}',
        style='{',
        level=logging.INFO,
        # level=logging.DEBUG,
        handlers=[stream_handler, file_handler],
    )


async def run():
    logger.info('Running event loop')
    await shut_down_event.wait()
    logger.info('Start to shut down')


async def shut_down():
    listener.shut_down()
    await blcsdk.shut_down()


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
