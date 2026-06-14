from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="超级管理员群管插件",
    description="基于NoneBot2的超级管理员群管插件，支持远程禁言管理",
    usage="""命令格式：
/admin mute <群号> <QQ号|all> - 禁言指定成员或全体禁言
/admin_unmute <群号> <QQ号|all> - 解除禁言
    
示例：
/admin mute 123456789 987654321  # 禁言用户987654321
/admin mute 123456789 all        # 全体禁言
/admin mute 123456789            # 禁言自己(超级管理员)
/admin_unmute 123456789 all      # 解除全体禁言""",
    type="application",
    homepage="https://github.com/your-repo/admin-plugin",
    supported_adapters={"~onebot.v11"},
)