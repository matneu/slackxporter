#!/usr/bin/env python

# prereq: python slack client, https://github.com/slackapi/python-slackclient
# pip install slackclient

import os
import re
import sys
import time
import datetime
from slackclient import SlackClient
from collections import defaultdict

# get token from
# https://api.slack.com/custom-integrations/legacy-tokens
slack_token = None
sc = SlackClient(slack_token)

history_limit = 150

all_conversations = "public_channel, private_channel, mpim, im"

user_mention = re.compile("<@\w+>")

users = dict()

class message:
    def add_child_message(self, child):
        self.child_msg[child.timestamp] = child

    def add_attachment(self, attachment):
        self.attachments.append(attachment)

    # allow initialization without any parameters for defaultdict
    def __init__(self, timestamp=None, sender=None, text=None):
        self.sender = sender
        self.text = text
        self.timestamp = timestamp
        self.parent_ts = None
        self.child_msg = dict()
        self.attachments = list()

    def __str__(self):
        str_repr = ""
        if not self.timestamp:
            str_repr = "No parent"
        else:
            date = datetime.datetime.fromtimestamp(self.timestamp)
            str_repr = date.strftime("%Y-%m-%d %H:%M:%S") + " " + self.sender.encode('utf-8').ljust(user_maxlen()) + "# " + self.text.encode('utf-8')
            #separator = "\n" + ''.join(["-" for x in str_repr])
            #str_repr = separator + str_repr + separator
            #str_repr += "\n" + self.text.encode('utf-8')
        for attachment in self.attachments:
            str_repr += "\n\t"
            str_repr += str(attachment)
        for child in sorted(self.child_msg):
            str_repr += "\n\t"
            str_repr += str(self.child_msg[child])
        return str_repr

def get_user(user_id):
    if user_id not in users:
        res = sc.api_call("users.info", user=user_id)
        if not res['ok']:
            print "Error retrieving user info:", res['error']
            return "unknown"
        if 'real_name' in res['user']:
            users[user_id] = res['user']['real_name']
        else:
            users[user_id] = res['user']['name']

    return users[user_id]

def user_maxlen():
    return max([len(x) for x in users.values()])

def substitute_users(text):
    substitutions = list()
    for mention in user_mention.findall(text):
        user = get_user(mention[2:-1])
        if user != "unknown":
            substitutions.append((mention, user))
    for mention, user in substitutions:
        text = text.replace(mention, user)
    return text

def get_conversations(conversation_types):
    conv_cursor = None
    channels = list()
    pulled = 0
    while True:
        if conv_cursor:
            res = sc.api_call("conversations.list", types=conversation_types, limit=1000, cursor=conv_cursor)
        else:
            res = sc.api_call("conversations.list", types=conversation_types, limit=1000)

        if not res["ok"] and res["headers"]["Retry-After"]:
            delay = int(res["headers"]["Retry-After"])
            print "Pausing for", delay, "seconds"
            time.sleep(delay)
        elif not res['ok']:
            print "Error pulling conversations:", res['error']
            return channels

        pulled += len(res['channels'])
        print "Pulled", pulled, "conversations"

        for c in res['channels']:
            if 'is_channel' in c and c['is_channel'] and not c['is_member']:
                continue
            channels.append(c)

        # more conversations?
        conv_cursor = res['response_metadata']['next_cursor']
        if len(conv_cursor) == 0:
            break

    return channels

def get_conversation_history(conversation_id):
    msg_cursor = None
    messages = defaultdict(message)
    pulled = 0
    while True:
        # fetch messages
        if msg_cursor:
            res = sc.api_call("conversations.history", channel=conversation_id, limit=history_limit, cursor=msg_cursor)
        else:
            res = sc.api_call("conversations.history", channel=conversation_id, limit=history_limit)
        if not res["ok"] and res["headers"]["Retry-After"]:
            delay = int(res["headers"]["Retry-After"])
            print "Pausing for", delay, "seconds"
            time.sleep(delay)
            continue
        elif not res['ok']:
            print "Error pulling messages:", res['error']
            break
        pulled += len(res['messages'])
        print "Pulled", pulled, "messages"
        # process messages
        for msg in res['messages']:
            if msg['type'] != "message":
                continue
            if 'subtype' in msg:
                continue
            sender = get_user(msg['user'])
            text = msg['text']
            text = substitute_users(text)
            timestamp = float(msg['ts'])
            new_msg = message(timestamp, sender, text)
            # take care of attachments
            if 'attachments' in msg:
                pass
                #https://api.slack.com/docs/message-attachments
                #for attachment in msg['attachments']:
                #    new_msg.add_attachment()

            # take care of threads
            if 'replies' in msg:
                parent_ts = float(msg['thread_ts'])
                reply_cursor = None
                while True:
                    # fetch replies
                    if reply_cursor:
                        res2 = sc.api_call("conversations.replies", channel=conversation_id, limit=history_limit, ts=msg['thread_ts'], cursor=reply_cursor)
                    else:
                        res2 = sc.api_call("conversations.replies", channel=conversation_id, limit=history_limit, ts=msg['thread_ts'])
                    if not res2["ok"] and res2["headers"]["Retry-After"]:
                        delay = int(res2["headers"]["Retry-After"])
                        print "Pausing for", delay, "seconds"
                        time.sleep(delay)
                        continue
                    elif not res2['ok']:
                        print "Error pulling replies:", res2['error']
                        break
                    for reply in res2['messages']:
                        reply_ts = float(reply['ts'])
                        if reply_ts == timestamp: continue # skip parent
                        reply_sender = get_user(reply['user'])
                        reply_text = reply['text']
                        reply_text = substitute_users(reply_text)
                        reply_msg = message(reply_ts, reply_sender, reply_text)
                        new_msg.add_child_message(reply_msg)
                    # more replies?
                    if 'response_metadata' in res2:
                        reply_cursor = res2['response_metadata']['next_cursor']
                        if len(reply_cursor) == 0:
                            break
                    else:
                        break
                    

            messages[timestamp] = new_msg

        # more messages?
        if 'response_metadata' in res:
            msg_cursor = res['response_metadata']['next_cursor']
            if len(msg_cursor) == 0:
                break
        else:
            break

    return messages

def main():
    conversations = get_conversations("private_channel")
    print "Conversations:", len(conversations)
    for conversation in conversations:
        if len(sys.argv) == 1 or conversation['name_normalized'] == sys.argv[1]:
            messages = get_conversation_history(conversation['id'])
            conv_title = None
            if 'name_normalized' in conversation:
                conv_title = conversation['name_normalized']
            elif 'name' in conversation:
                conv_title = conversation['name']
            elif 'is_im' in conversation and conversation['is_im']:
                conv_title = "im_" + get_user(conversation['user']).lower().replace(" ", "_")
            else:
                print "no title for conversation"
                print conversation
                break
            f = open(conv_title + ".log", "w")
            for ts in sorted(messages):
                f.write(str(messages[ts]) + "\n")
            f.close()


if __name__ == '__main__':
    main()
