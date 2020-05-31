import json
import logging
import os
from typing import Dict, List
from urllib.parse import urljoin
import requests
from itsdangerous import URLSafeTimedSerializer
from src.routes.user_utils import get_user_by_email
from src.new_backend.models import Comment, unsubscribe_table, db

logger = logging.getLogger(__name__)

MAILGUN_KEY = os.environ.get('MAILGUN_KEY')
SERIALIZER_KEY = os.environ.get('SERIALIZER_KEY')
serializer = URLSafeTimedSerializer(SERIALIZER_KEY)

FRONTEND_BASE_URL = os.environ.get('FRONTEND_URL')
BASE_UNSUBSCRIBE_LINK = urljoin(FRONTEND_BASE_URL, '/user/unsubscribe/')


def create_unsubscribe_token(email, paper_id):
    return serializer.dumps([email, paper_id])


def deserialize_token(token):
    return serializer.loads(token)


def has_user_unsubscribed(user_email, paper_id):
    user = get_user_by_email(user_email)
    return paper_id in user.get('mutedPapers', [])


def new_reply_notification(email: str, name: str, paper_id: str, paper_title: str):
    if has_user_unsubscribed(email, paper_id):
        return
    variables = {
        "first_name": name,
        "text": f"You have got a new reply to your comment on '{paper_title}'",
        "link": urljoin(FRONTEND_BASE_URL, '/paper', f'/{paper_id}'),
        "mute_link": urljoin(BASE_UNSUBSCRIBE_LINK, create_unsubscribe_token(email, paper_id))
    }

    send_email(address=email, name=name, variables=variables, template="new_reply",
               subject="You have got a new reply to your comment")


# users is a list of {email, name} dicts
def new_comment_notification(user_id: int, paper_id: str, paper_title: str, comment_id: int):
    unsubscribed_users = db.session.query(unsubscribe_table.c.user_id).filter(
        unsubscribe_table.c.paper_id == paper_id).all()
    unsubscribed_users = [u.user_id for u in unsubscribed_users]
    send_to_users = db.session.query(Comment.user).distinct(Comment.user_id).filter(
        Comment.paper_id == paper_id, Comment.user_id.notin_(unsubscribed_users + [user_id]), Comment.user_id != None).all()

    for u in send_to_users:
        variables = {
            "first_name": u.username,
            "text": f"A new comment was posted on a paper you are following - {paper_title}. Click below to view:",
            "link": urljoin(FRONTEND_BASE_URL, f'/paper/{paper_id}#highlight-{comment_id}'),
            "mute_link": urljoin(BASE_UNSUBSCRIBE_LINK, create_unsubscribe_token(u.email, paper_id))
        }
        shortened_title = paper_title
        max_length = 40
        if len(shortened_title) > max_length:
            shortened_title = shortened_title[:max_length] + '...'
        send_email(address=u.email, name=u.username, variables=variables, template="new_reply",
                   subject=f"New comment on {shortened_title}")


def send_email(address: str, name: str, variables: Dict[str, str], subject: str, template: str):
    try:
        return requests.post(
            "https://api.mailgun.net/v3/email.scihive.org/messages",
            auth=("api", MAILGUN_KEY),
            data={"from": "Scihive <noreply@scihive.org>",
                  "to": f"{name} <{address}>",
                  "subject": subject,
                  "template": template,
                  "h:X-Mailgun-Variables": f'{json.dumps(variables)}'})
    except Exception as e:
        logger.error(f'Failed to send email - {e}')
        return
