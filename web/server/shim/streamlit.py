"""Stand-in for Streamlit on the web server: data_store.py and weather.py import `streamlit` only for its
cache and its session state. This gives them both, so the same analysis code runs unchanged behind the website."""

import functools
import time

session_state = {}
_memos = []


def cache_data(func=None, *, ttl=None, max_entries=64, **_ignored):
    def wrap(f):
        memo = {}
        _memos.append(memo)

        @functools.wraps(f)
        def inner(*args):
            hit = memo.get(args)
            if hit and (ttl is None or time.time() - hit[0] < ttl):
                return hit[1]
            value = f(*args)
            if len(memo) >= (max_entries or 64):
                memo.pop(next(iter(memo)))          # drop the oldest entry
            memo[args] = (time.time(), value)
            return value
        return inner
    return wrap(func) if func else wrap


cache_data.clear = lambda: [m.clear() for m in _memos]
