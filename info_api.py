import json
import logging
import re
from collections.abc import Callable
from typing import Any

import aiohttp

logger = logging.getLogger('osu-requests-bot.' + __name__)

RE_BEATMAPSET = r'<script id="json-beatmapset" type="application/json">\n        (.*?)\n    </script>'

GET_INFO_COMMON: dict[str, Callable[[str, int], Any]] = {}
TIMEOUT = 5

async def get_url_json(url:str) -> dict:
    """
    使用aiohttp获取json信息  
    如果没有信息就返回空字典  
    由于sayo镜像站使用的json返回有问题，因此需要解析为text再解析回json
    """
    async with (
        aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as session,
        session.get(url=url) as response,
    ):
        if response.status == 200:
            data_text = await response.text()
            return json.loads(data_text)
        return {}

async def get_response(source_url:str) -> tuple[str, str]:
    '''
    使用aiohttp获取重定向一次后的链接与网页信息  
    如果没有重定向则直接返回response的链接  
    只适用于OSU这种只重定向一次的情况，其他情况需要考虑更改代码
    '''
    async with (
        aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as session,
        session.get(source_url, allow_redirects=False) as response,
    ):
        if response.status == 302 and "Location" in response.headers:
            target_url = response.headers["Location"]
            async with session.get(target_url) as response:
                html_text = await response.text()

        elif response.status == 200:
            target_url = str(response.url)
            html_text = await response.text()

        elif response.status == 404:
            target_url = ""
            html_text  = ""

    return (target_url, html_text)

def register_info_server(server_name:str):
    '''
    注册表装饰器，用于添加各类获取谱面信息的api函数
    '''
    def decorator(func):
        GET_INFO_COMMON[server_name] = func
        return func
    return decorator

async def get_info(mapid_type:str, mapid_num:int, server_name:str = "auto") -> dict|None:
    """
    获取谱面信息，如果获取失败将会返回None  
    返回的字典：  
    {"server": 所使用的API
     "artist": 艺术家信息,  
     "title" : 歌曲标题，
     "sid"   : BeatMapSetID  
     "url"   : 谱面链接"}  
    """
    if server_name == "auto":
        for name, getter in GET_INFO_COMMON.items():
            logger.debug("正在尝试从%s获取谱面信息", name)
            info = await getter(mapid_type, mapid_num)
            if info:
                return info
    else:
        logger.debug("正在获取谱面信息")
        info = await GET_INFO_COMMON[server_name](mapid_type, mapid_num)
        if info or server_name == "osu_html":
            return info
        else:
            return await GET_INFO_COMMON["osu_html"](mapid_type, mapid_num)

import server