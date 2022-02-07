import asyncio
from typing import Union, Optional, Callable

from app.applications.schemas import SlackEventHook, SlackMentionHook, SlackChallengeHook, SlackEvent, \
    SlackMentionEvent, CommandType, SlackChallengeHookResponse
from app.applications.services.reaction_services import ReactionAppService
from app.applications.services.user_services import UserAppService
from app.domains.reactions.entities import SlackEventType
from app.utils.slack_message_format import get_command_error_msg, get_help_msg, get_best_user_format
from app.utils.utils import slack_command_exception_handler, mapping_slack_command_to_dict, send_slack_msg
from conf import settings


class SlackService:
    _user_app_service = UserAppService
    _reaction_app_service = ReactionAppService

    @classmethod
    async def slack_web_hook_handler(
        cls,
        slack_event: Union[SlackEventHook, SlackMentionHook, SlackChallengeHook]
    ) -> Optional[SlackChallengeHookResponse]:
        # 슬랙 웹훅 인증
        if type(slack_event) == SlackChallengeHook:
            return SlackChallengeHookResponse(challenge=slack_event.challenge)
        else:
            await cls.slack_event_handler(event=slack_event.event)

    @classmethod
    @slack_command_exception_handler()
    async def slack_event_handler(cls, event: [SlackEvent, SlackMentionEvent]):
        """
        슬랙 이벤트를 받아서 type 별로 처리하는 함수
        """
        slack_event = SlackEventType(event.type)

        # 이모지 업데이트
        if slack_event in [SlackEventType.ADDED_REACTION, SlackEventType.REMOVED_REACTION]:
            if event.item_user == event.user or event.reaction not in settings.config.REACTION_LIST:
                return
            await cls._reaction_app_service.update_sending_reaction(event)

        # 앱 맨션, 메세지 핸들링
        elif slack_event in [SlackEventType.APP_MENTION_REACTION, SlackEventType.APP_MESSAGE]:
            await cls.mention_command_handler(event)

    @classmethod
    async def mention_command_handler(cls, event: SlackMentionEvent):
        mention_functions = {
            CommandType.HELP_COMMAND: cls.send_help_command,
            CommandType.CREATE_USER_COMMAND: cls.add_user,
            CommandType.UPDATE_USER_COMMAND: cls.update_user,
            CommandType.HIDE_USER_COMMAND: cls.hide_user,
            CommandType.SHOW_USER_COMMAND: cls.show_user,
            CommandType.SHOW_BEST_MEMBER_COMMAND: cls.send_best_user_list_to_slack
        }
        cmd, mapped_attr = mapping_slack_command_to_dict(event)
        func: Callable[[dict, SlackMentionEvent], None] = mention_functions.get(cmd)

        if func is None:
            send_slack_msg(channel=event.channel, blocks=get_command_error_msg())
            return

        kwargs = {'mapped_attr': mapped_attr, 'event': event}
        if asyncio.iscoroutinefunction(func):
            await func(**kwargs)
        else:
            func(**kwargs)

    @classmethod
    async def add_user(cls, **kwargs):
        await cls._user_app_service.create_user(kwargs.get('mapped_attr'))

    @classmethod
    async def update_user(cls, **kwargs):
        await cls._user_app_service.update_user(kwargs.get('mapped_attr'))

    @classmethod
    async def hide_user(cls, **kwargs):
        await cls._user_app_service.hide_user(kwargs.get('mapped_attr'))

    @classmethod
    async def show_user(cls, **kwargs):
        await cls._user_app_service.show_user(kwargs.get('mapped_attr'))

    @classmethod
    async def send_best_user_list_to_slack(cls, **kwargs):
        mapped_attr = kwargs.get('mapped_attr')
        event = kwargs.get('event')
        year = int(mapped_attr.get('year'))
        month = int(mapped_attr.get('month'))

        try:
            best_users = await cls._reaction_app_service.get_this_month_best_users(year, month)
            send_slack_msg(
                channel=event.channel,
                blocks=get_best_user_format(f"{year}년 {month}월 베스트 멤버", best_users)
            )
        except Exception as err:
            print(err)
            return

    @classmethod
    def send_help_command(cls, **kwargs):
        event = kwargs.get('event')
        send_slack_msg(event.channel, get_help_msg())