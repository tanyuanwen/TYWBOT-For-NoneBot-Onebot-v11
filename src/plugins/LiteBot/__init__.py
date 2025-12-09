from nonebot.plugin import PluginMetadata, require

require("menu")
from . import status

__plugin_meta__ = PluginMetadata(
    name="TYWBOT插件",
    description="TYWBOT本体相关功能插件",
    usage="TYWBOT插件",
    type="application",
)
__all__ = [
    "status",
]
