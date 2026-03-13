import base64
import binascii
import logging
import lxml.html
import re
import time

from typing import Any, Dict, List, Optional, Tuple, Union, cast

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils.timezone import now as timezone_now
from django.utils.translation import ugettext as _
import gcm
import requests
import ujson

from zerver.decorator import statsd_increment
from zerver.lib.avatar import absolute_avatar_url
from zerver.lib.exceptions import JsonableError
from zerver.lib.message import access_message, huddle_users
from zerver.lib.queue import retry_event
from zerver.lib.remote_server import send_to_push_bouncer, send_json_to_push_bouncer
from zerver.lib.timestamp import datetime_to_timestamp
from zerver.models import PushDeviceToken, Message, Realm, Recipient, UserProfile, \
    get_display_recipient, receives_offline_push_notifications, \
    receives_online_notifications, get_user_profile_by_id, \
    ArchivedMessage

def get_base_payload(realm: Realm) -> Dict[str, Any]:
    '''Common fields for all notification payloads.'''
    data = {}  # type: Dict[str, Any]

    # These will let the app support logging into multiple realms and servers.
    data['server'] = settings.EXTERNAL_HOST
    data['realm_id'] = realm.id
    data['realm_uri'] = realm.uri

    return data

def get_remove_payload_gcm(
        user_profile: UserProfile, message_id: int,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    '''A `remove` payload + options, for Android via GCM/FCM.'''
    gcm_payload = get_base_payload(user_profile.realm)
    gcm_payload.update({
        'event': 'remove',
        'zulip_message_id': message_id,  # message_id is reserved for CCS
    })
    gcm_options = {'priority': 'normal'}
    return gcm_payload, gcm_options

def get_message_payload_gcm(
        user_profile: UserProfile, message: Message,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    '''A `message` payload + options, for Android via GCM/FCM.'''
    data = get_message_payload(message)
    content, truncated = truncate_content(get_mobile_push_content(message.rendered_content))
    data.update({
        'user': user_profile.email,
        'event': 'message',
        'alert': get_gcm_alert(message),
        'zulip_message_id': message.id,  # message_id is reserved for CCS
        'time': datetime_to_timestamp(message.pub_date),
        'content': content,
        'content_truncated': truncated,
        'sender_full_name': message.sender.full_name,
        'sender_avatar_url': absolute_avatar_url(message.sender),
    })
    gcm_options = {'priority': 'high'}
    return data, gcm_options

def send_notifications_to_bouncer(user_profile_id: int,
                                  apns_payload: Dict[str, Any],
                                  gcm_payload: Dict[str, Any],
                                  gcm_options: Dict[str, Any]) -> None:
    post_data = {
        'user_id': user_profile_id,
        'apns_payload': apns_payload,
        'gcm_payload': gcm_payload,
        'gcm_options': gcm_options,
    }
    # Calls zilencer.views.remote_server_notify_push
    send_json_to_push_bouncer('POST', 'push/notify', post_data)

def handle_remove_push_notification(user_profile_id: int, message_id: int) -> None:
    """This should be called when a message that had previously had a
    mobile push executed is read.  This triggers a mobile push notifica
    mobile app when the message is read on the server, to remove the
    message from the notification.

    """
    user_profile = get_user_profile_by_id(user_profile_id)
    message, user_message = access_message(user_profile, message_id)
    gcm_payload, gcm_options = get_remove_payload_gcm(user_profile, message_id)

    if uses_notification_bouncer():
        try:
            send_notifications_to_bouncer(user_profile_id,
                                          {},
                                          gcm_payload,
                                          gcm_options)
        except requests.ConnectionError:  # nocoverage
            def failure_processor(event: Dict[str, Any]) -> None:
                logger.warning(
                    "Maximum retries exceeded for trigger:%s event:push_notification" % (
                        event['user_profile_id']))
    else:
        android_devices = list(PushDeviceToken.objects.filter(
            user=user_profile, kind=PushDeviceToken.GCM))
        if android_devices:
            send_android_push_notification(android_devices, gcm_payload, gcm_options)

    user_message.flags.active_mobile_push_notification = False
    user_message.save(update_fields=["flags"])

@statsd_increment("push_notifications")
def handle_push_notification(user_profile_id: int, missed_message: Dict[str, Any]) -> None:
    """
    missed_message is the event received by the
    zerver.worker.queue_processors.PushNotificationWorker.consume function.
    """
    if not push_notifications_enabled():
        return
    user_profile = get_user_profile_by_id(user_profile_id)
    if not (receives_offline_push_notifications(user_profile) or
            receives_online_notifications(user_profile)):
        return

    user_profile = get_user_profile_by_id(user_profile_id)
    try:
        (message, user_message) = access_message(user_profile, missed_message['message_id'])
    except JsonableError:
        if ArchivedMessage.objects.filter(id=missed_message['message_id']).exists():
            # If the cause is a race with the message being deleted,
            # that's normal and we have no need to log an error.
            return
        logging.error("Unexpected message access failure handling push notifications: %s %s" % (
            user_profile.id, missed_message['message_id']))
        return

    if user_message is not None:
        # If the user has read the message already, don't push-notify.
        #
        # TODO: It feels like this is already handled when things are
        # put in the queue; maybe we should centralize this logic with
        # the `zerver/tornado/event_queue.py` logic?
        if user_message.flags.read:
            return

        # Otherwise, we mark the message as having an active mobile
        # push notification, so that we can send revocation messages
        # later.
        user_message.flags.active_mobile_push_notification = True
        user_message.save(update_fields=["flags"])
    else:
        # Users should only be getting push notifications into this
        # queue for messages they haven't received if they're
        # long-term idle; anything else is likely a bug.
        if not user_profile.long_term_idle:
            logger.error("Could not find UserMessage with message_id %s and user_id %s" % (
                missed_message['message_id'], user_profile_id))
            return

    message.trigger = missed_message['trigger']

    apns_payload = get_message_payload_apns(user_profile, message)
    gcm_payload, gcm_options = get_message_payload_gcm(user_profile, message)
    logger.info("Sending push notifications to mobile clients for user %s" % (user_profile_id,))

    if uses_notification_bouncer():
        try:
            send_notifications_to_bouncer(user_profile_id,
                                          apns_payload,
                                          gcm_payload,
                                          gcm_options)
        except requests.ConnectionError:
            def failure_processor(event: Dict[str, Any]) -> None:
                logger.warning(
                    "Maximum retries exceeded for trigger:%s event:push_notification" % (
                        event['user_profile_id']))
            retry_event('missedmessage_mobile_notifications', missed_message,
                        failure_processor)
        return

    android_devices = list(PushDeviceToken.objects.filter(user=user_profile,
                                                          kind=PushDeviceToken.GCM))

    apple_devices = list(PushDeviceToken.objects.filter(user=user_profile,
                                                        kind=PushDeviceToken.APNS))

    if apple_devices:
        send_apple_push_notification(user_profile.id, apple_devices,
                                     apns_payload)

    if android_devices:
        send_android_push_notification(android_devices, gcm_payload, gcm_options)