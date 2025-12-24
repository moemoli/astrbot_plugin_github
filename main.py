from aiocqhttp import MessageSegment
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
import aiohttp

@register(
    "astrbot_plugin_github",
    "moemoli",
    "一款根据github commit hash 自动审核的插件",
    "0.1.0",
)
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""

    @filter.command("GH审核")
    async def github_audit(self, event: AiocqhttpMessageEvent, repo: str):
        """这是一个 github 审核指令"""  # 这是 handler 的描述，将会被解析方便用户了解插件内容。建议填写。
        info = await event.bot.get_group_member_info(
            group_id=int(event.get_group_id()), user_id=int(event.get_sender_id())
        )
        if info.get("role", "").upper() == "MEMBER" and event.is_admin() is False:
            yield event.plain_result("只有管理员才能设置审核仓库")
            return
        repo = repo.replace("https://github.com/", "")
        repo = repo.replace("http://github.com/", "")
        repo = repo.replace("git@github.com:", "")
        repo = repo.replace(".git", "")
        await self.put_kv_data(event.get_group_id(), repo)
        yield event.plain_result(f"已经设置本群审核仓库为 {repo}")  # 发送一条纯文本消息

    async def get_repo_hash(self, repo: str) -> str | None:
        """获取指定仓库的最新 commit hash"""
        api_url = f"https://api.github.com/repos/{repo}/commits"
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return data[0].get("sha", "")

    async def can_approve(self, repo: str, comment: str | None) -> bool:
        """根据 commit hash 判断是否可以通过审核"""
        hash = await self.get_repo_hash(repo)
        logger.info(f"申请hash为: {comment}, 仓库 {repo} 最新的 commit hash 为 {hash}")
        return comment != None and len(comment) >= 7 and hash != None and (hash).startswith(comment)

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    async def group_audit(self, event: AiocqhttpMessageEvent):
        """监听进群/退群事件"""
        raw = event.message_obj.raw_message
        if isinstance(raw, dict):
            post_type = raw.get("post_type", "")
            if post_type == "request":
                logger.info(f"收到加群请求事件，内容为: {raw}")
                gid = raw.get("group_id", 0)
                repo = await self.get_kv_data(gid, None)
                if repo != None:
                    uid = raw.get("user_id", 0)
                    flag = raw.get("flag", "")
                    sub_type = raw.get("sub_type", "")
                    comment = raw.get("comment", None)
                    if isinstance(comment, str):
                        start = "答案："
                        comment = comment[comment.find(start) + len(start):].strip()
                    if await self.can_approve(repo, comment):
                        logger.info(f"用户 {uid} 通过审核，自动同意加群")
                        await event.bot.set_group_add_request(
                            flag=flag,
                            sub_type=sub_type,
                            approve=True,
                        )
                    else:
                        logger.info(f"用户 {uid} 未能通过审核，自动拒绝加群: {comment}")
                        await event.bot.set_group_add_request(
                            flag=flag,
                            sub_type=sub_type,
                            approve=False,
                            reason="commit hash 错误"
                        )
                        await event.bot.send_group_msg(
                           message=MessageSegment.text(f"用户 {uid}  未能通过审核，拒绝加群。\n申请内容: {comment}"),
                           group_id=gid
                        )

                else:
                    logger.info(f"群 {gid} 未配置审核仓库，忽略")

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
