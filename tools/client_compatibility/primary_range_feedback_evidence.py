"""Exact installed-client stock range feedback, without game-control dependencies."""


def stock_range_error(value):
    return value.get('code')==265 and value.get('text')=='You are too far away!'
