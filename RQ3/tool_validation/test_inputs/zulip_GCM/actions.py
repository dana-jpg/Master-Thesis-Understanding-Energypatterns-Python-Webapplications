from typing import (
    AbstractSet, Any, Callable, Dict, Iterable, List, Mapping, MutableMapping,
    Optional, Sequence, Set, Tuple, Union, cast
)
from mypy_extensions import TypedDict

import django.db.utils
from django.db.models import Count
from django.contrib.contenttypes.models import ContentType
from django.utils.html import escape
from django.utils.translation import ugettext as _
from django.conf import settings
from django.core import validators
from django.core.files import File
from analytics.lib.counts import COUNT_STATS, do_increment_logging_stat, \
    RealmCount

from zerver.lib.bugdown import (
    version as bugdown_version,
    url_embed_preview_enabled_for_realm,
    convert as bugdown_convert
)
from zerver.lib.addressee import Addressee
from zerver.lib.bot_config import (
    ConfigError,
    get_bot_config,
    get_bot_configs,
    set_bot_config,
)
from zerver.lib.cache import (
    bot_dict_fields,
    delete_user_profile_caches,
    to_dict_cache_key_id,
    user_profile_by_api_key_cache_key,
)
from zerver.lib.context_managers import lockfile
from zerver.lib.emoji import emoji_name_to_emoji_code, get_emoji_file_name
from zerver.lib.exceptions import StreamDoesNotExistError, \
    StreamWithIDDoesNotExistError
from zerver.lib.hotspots import get_next_hotspots
from zerver.lib.message import (
    access_message,
    MessageDict,
    render_markdown,
    update_first_visible_message_id,
)
from zerver.lib.realm_icon import realm_icon_url
from zerver.lib.realm_logo import realm_logo_url
from zerver.lib.retention import move_messages_to_archive
from zerver.lib.send_email import send_email, FromAddress, send_email_to_admins
from zerver.lib.stream_subscription import (
    get_active_subscriptions_for_stream_id,
    get_active_subscriptions_for_stream_ids,
    get_bulk_stream_subscriber_info,
    get_stream_subscriptions_for_user,
    get_stream_subscriptions_for_users,
    num_subscribers_for_stream_id,
)
from zerver.lib.stream_topic import StreamTopicTarget
from zerver.lib.topic import (
    filter_by_exact_message_topic,
    filter_by_topic_name_via_message,
    save_message_for_edit_use_case,
    update_messages_for_topic_edit,
    ORIG_TOPIC,
    LEGACY_PREV_TOPIC,
    TOPIC_LINKS,
    TOPIC_NAME,
)
from zerver.lib.topic_mutes import (
    get_topic_mutes,
    add_topic_mute,
    remove_topic_mute,
)
from zerver.lib.users import (
    bulk_get_users,
    check_bot_name_available,
    check_full_name,
    get_api_key,
)
from zerver.lib.user_status import (
    update_user_status,
)
from zerver.lib.user_groups import create_user_group, access_user_group_by_id

from zerver.models import Realm, RealmEmoji, Stream, UserProfile, UserActivity, \
    RealmDomain, Service, SubMessage, \
    Subscription, Recipient, Message, Attachment, UserMessage, RealmAuditLog, \
    UserHotspot, MultiuseInvite, ScheduledMessage, UserStatus, \
    Client, DefaultStream, DefaultStreamGroup, UserPresence, \
    ScheduledEmail, MAX_TOPIC_NAME_LENGTH, \
    MAX_MESSAGE_LENGTH, get_client, get_stream, get_personal_recipient, \
    get_user_profile_by_id, PreregistrationUser, \
    get_realm, bulk_get_recipients, get_stream_recipient, get_stream_recipients, \
    email_allowed_for_realm, email_to_username, display_recipient_cache_key, \
    get_user_by_delivery_email, get_stream_cache_key, active_non_guest_user_ids, \
    UserActivityInterval, active_user_ids, get_active_streams, \
    realm_filters_for_realm, RealmFilter, stream_name_in_use, \
    get_old_unclaimed_attachments, is_cross_realm_bot_email, \
    Reaction, EmailChangeStatus, CustomProfileField, \
    custom_profile_fields_for_realm, get_huddle_user_ids, \
    CustomProfileFieldValue, validate_attachment_request, get_system_bot, \
    query_for_ids, get_huddle_recipient, \
    UserGroup, UserGroupMembership, get_default_stream_groups, \
    get_bot_services, get_bot_dicts_in_realm, DomainNotAllowedForRealmError, \
    DisposableEmailError, EmailContainsPlusError, \
    get_user_including_cross_realm, get_user_by_id_in_realm_including_cross_realm, \
    get_stream_by_id_in_realm

from zerver.lib.alert_words import alert_words_in_realm
from zerver.lib.avatar import avatar_url, avatar_url_from_dict
from zerver.lib.stream_recipient import StreamRecipientMap
from zerver.lib.validator import check_widget_content
from zerver.lib.widget import do_widget_post_save_actions

from django.db import transaction, IntegrityError, connection
from django.db.models import F, Q, Max, Sum
from django.db.models.query import QuerySet
from django.core.exceptions import ValidationError
from django.utils.timezone import now as timezone_now

from confirmation.models import Confirmation, create_confirmation_link, generate_key, \
    confirmation_url
from confirmation import settings as confirmation_settings

from zerver.lib.bulk_create import bulk_create_users
from zerver.lib.timestamp import timestamp_to_datetime, datetime_to_timestamp
from zerver.lib.queue import queue_json_publish
from zerver.lib.utils import generate_api_key
from zerver.lib.create_user import create_user, get_display_email_address
from zerver.lib import bugdown
from zerver.lib.cache import cache_with_key, cache_set, \
    user_profile_by_email_cache_key, \
    cache_set_many, cache_delete, cache_delete_many
from zerver.decorator import statsd_increment
from zerver.lib.utils import log_statsd_event, statsd
from zerver.lib.i18n import get_language_name
from zerver.lib.alert_words import add_user_alert_words, \
    remove_user_alert_words, set_user_alert_words
from zerver.lib.notifications import clear_scheduled_emails, \
    clear_scheduled_invitation_emails, enqueue_welcome_emails
from zerver.lib.exceptions import JsonableError, ErrorCode, BugdownRenderingException
from zerver.lib.sessions import delete_user_sessions
from zerver.lib.upload import attachment_url_re, attachment_url_to_path_id, \
    claim_attachment, delete_message_image, upload_emoji_image, delete_avatar_image
from zerver.lib.video_calls import request_zoom_video_call_url
from zerver.tornado.event_queue import send_event
from zerver.lib.types import ProfileFieldData

from analytics.models import StreamCount

if settings.BILLING_ENABLED:
    from corporate.lib.stripe import update_license_ledger_if_needed

import ujson
import time
import re
import datetime
import os
import platform
import logging
import itertools
from collections import defaultdict
from operator import itemgetter

# This will be used to type annotate parameters in a function if the function
# works on both str and unicode in python 2 but in python 3 it only works on str.
SizedTextIterable = Union[Sequence[str], AbstractSet[str]]

STREAM_ASSIGNMENT_COLORS = [
    "#76ce90", "#fae589", "#a6c7e5", "#e79ab5",
    "#bfd56f", "#f4ae55", "#b0a5fd", "#addfe5",
    "#f5ce6e", "#c2726a", "#94c849", "#bd86e5",
    "#ee7e4a", "#a6dcbf", "#95a5fd", "#53a063",
    "#9987e1", "#e4523d", "#c2c2c2", "#4f8de4",
    "#c6a8ad", "#e7cc4d", "#c8bebf", "#a47462"]



def do_mark_stream_messages_as_read(user_profile: UserProfile,
                                    client: Client,
                                    stream: Stream,
                                    topic_name: Optional[str]=None) -> int:
    log_statsd_event('mark_stream_as_read')

    msgs = UserMessage.objects.filter(
        user_profile=user_profile
    )

    recipient = get_stream_recipient(stream.id)
    msgs = msgs.filter(message__recipient=recipient)

    if topic_name:
        msgs = filter_by_topic_name_via_message(
            query=msgs,
            topic_name=topic_name,
        )

    msgs = msgs.extra(
        where=[UserMessage.where_unread()]
    )

    message_ids = list(msgs.values_list('message__id', flat=True))

    count = msgs.update(
        flags=F('flags').bitor(UserMessage.flags.read)
    )

    event = dict(
        type='update_message_flags',
        operation='add',
        flag='read',
        messages=message_ids,
        all=False,
    )
    send_event(user_profile.realm, event, [user_profile.id])
    do_clear_mobile_push_notifications_for_ids(user_profile, message_ids)

    statsd.incr("mark_stream_as_read", count)
    return count

def do_clear_mobile_push_notifications_for_ids(user_profile: UserProfile,
                                               message_ids: List[int]) -> None:
    for user_message in UserMessage.objects.filter(
            message_id__in=message_ids,
            user_profile=user_profile).extra(
                where=[UserMessage.where_active_push_notification()]):
        event = {
            "user_profile_id": user_profile.id,
            "message_id": user_message.message_id,
            "type": "remove",
        }
        queue_json_publish("missedmessage_mobile_notifications", event)

def do_update_message_flags(user_profile: UserProfile,
                            client: Client,
                            operation: str,
                            flag: str,
                            messages: List[int]) -> int:
    valid_flags = [item for item in UserMessage.flags if item not in UserMessage.NON_API_FLAGS]
    if flag not in valid_flags:
        raise JsonableError(_("Invalid flag: '%s'" % (flag,)))
    flagattr = getattr(UserMessage.flags, flag)

    assert messages is not None
    msgs = UserMessage.objects.filter(user_profile=user_profile,
                                      message__id__in=messages)
    # This next block allows you to star any message, even those you
    # didn't receive (e.g. because you're looking at a public stream
    # you're not subscribed to, etc.).  The problem is that starring
    # is a flag boolean on UserMessage, and UserMessage rows are
    # normally created only when you receive a message to support
    # searching your personal history.  So we need to create one.  We
    # add UserMessage.flags.historical, so that features that need
    # "messages you actually received" can exclude these UserMessages.
    if msgs.count() == 0:
        if not len(messages) == 1:
            raise JsonableError(_("Invalid message(s)"))
        if flag != "starred":
            raise JsonableError(_("Invalid message(s)"))
        # Validate that the user could have read the relevant message
        message = access_message(user_profile, messages[0])[0]

        # OK, this is a message that you legitimately have access
        # to via narrowing to the stream it is on, even though you
        # didn't actually receive it.  So we create a historical,
        # read UserMessage message row for you to star.
        UserMessage.objects.create(user_profile=user_profile,
                                   message=message,
                                   flags=UserMessage.flags.historical | UserMessage.flags.read)

    if operation == 'add':
        count = msgs.update(flags=F('flags').bitor(flagattr))
    elif operation == 'remove':
        count = msgs.update(flags=F('flags').bitand(~flagattr))
    else:
        raise AssertionError("Invalid message flags operation")

    event = {'type': 'update_message_flags',
             'operation': operation,
             'flag': flag,
             'messages': messages,
             'all': False}
    send_event(user_profile.realm, event, [user_profile.id])

    if flag == "read" and operation == "add":
        do_clear_mobile_push_notifications_for_ids(user_profile, messages)

    statsd.incr("flags.%s.%s" % (flag, operation), count)
    return count

