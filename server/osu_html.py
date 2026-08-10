import json
import re

from info_api import get_response, register_info_server


RE_BEATMAPSET = r'<script id="json-beatmapset" type="application/json">\s*(.*?)\s*</script>'

@register_info_server("osu_html")
async def get_info_osu_html(mapid_type:str, mapid_num:int) -> dict[str,str]|None:
    '''
    解析谱面页面获取谱面信息  
    '''
    map_url, html_text = await get_response(f"https://osu.ppy.sh/{mapid_type}/{mapid_num}")
    # 更换mapid类型尝试二次搜索
    if not map_url:
        mapid_type = "s" if mapid_type == "b" else "b"
        map_url, html_text = await get_response(f"https://osu.ppy.sh/{mapid_type}/{mapid_num}")
    
    if map_url:
        # 从网页获取谱面信息
        match = re.search(RE_BEATMAPSET, html_text, re.IGNORECASE)
        if match:
            json_data = json.loads(match.group(1))
            return  {"server": "osu_html",
                     "artist": json_data["artist"],
                     "title" : json_data["title"],
                     "sid"   : json_data["id"],
                     "url"   : map_url
                    }