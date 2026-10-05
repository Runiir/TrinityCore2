"""Restrict passive endpoint decoding to TCP sockets held by the owned game."""
from pathlib import Path


def ports(pid):
    process=Path(f'/proc/{pid}')
    inodes=set()
    for entry in (process/'fd').iterdir():
        try:link=entry.readlink().as_posix()
        except FileNotFoundError:continue
        if link.startswith('socket:['):inodes.add(link[8:-1])
    endpoint='394AFF33:1F95' # 51.255.74.57:8085, /proc little-endian IPv4
    result=set()
    for line in (process/'net/tcp').read_text().splitlines()[1:]:
        fields=line.split()
        if fields[9] in inodes and fields[2]==endpoint and fields[3]=='01':
            result.add(int(fields[1].split(':')[1],16))
    return result
