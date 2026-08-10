import importlib
import logging
import pkgutil

logger = logging.getLogger('osu-requests-bot.' + __name__)

def init():
    """导入并注册包内所有 server 子模块（幂等，可重复调用）"""
    for module_info in pkgutil.iter_modules(__path__):
        try:
            importlib.import_module(f"{__name__}.{module_info.name}")
        except Exception as e:
            logger.warning("加载 server 模块 %s 失败: %s", module_info.name, e, exc_info=True)

# import server 即自动注册
init()