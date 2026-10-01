"""Callables referenced by dotted path from test settings."""


def deny_all(*args, **kwargs):
    return False


def allow_all(*args, **kwargs):
    return True


def always_spam(comment, request):
    return True


def broken_checker(comment, request):
    raise RuntimeError("spam service down")


SENT = []


def keep_comment_reply_only(message):
    return message.event == "comment_reply"
