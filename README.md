这是一个Blivechat插件，需要配合Blivechat本地版

## 如何使用
- 下载 [xfgryujk开发的Blivechat](https://github.com/xfgryujk/blivechat/releases)
- 将插件解压放到 Blivechat 的 data\plugins 文件夹里
- 右键编辑打开config.py
- 打开Blivechat，在控制台插件列表启用即可

config.py配置参考如下
```
# ===用户配置===
USER_NAME = "set you osu name" # 用户名
PASSWORD = "get your irc password" # irc密码
API_SERVER = "osu_html" # 获取谱面方式，默认从官网获取
SEND_SELF:bool = True # 是否转发给自己，lazer请设置为False让消息转发给BanchoBot
```


弹幕指令：  
点歌 b(bid)  
点歌 s(sid)   
点歌 (bid/sid)

其他设置：  
api_server可以设置下列api，设置后将会从指定的服务器获取谱面信息   
```
osu_html:从官网爬取页面信息获取谱面信息
sayo：从sayo镜像站api获取谱面信息
kitsu：从kitsu镜像站api获取谱面信息
```
你也可以通过魔改server.py添加其他API支持，只需要给新添加的API函数添加修饰器 @register_info_server(API名称) 即可  
需要注意函数要返回的是字典且必须包含这些信息：
```
{"server": API名称,
"artist": 艺术家名，一般用英文,
"title" : 歌曲名称，一般用英文,
"sid"   : 谱面的beatmapset id,
"url"   : 谱面链接，注意必须使用以 https://osu.ppy.sh/beatmapsets/ 开头的网址格式游戏内才能正常跳转谱面"
}
```

TODO：   
- ~~将IRCAPI修改为消息队列的方式传递信息，使其能保证支持PPY要求的限速~~ 2026.08.04：已实现并完善了错误代码
- 添加OSU API v2的支持，转发模式直接使用OSU API v2
