# -*- coding: utf-8 -*-
"""أدوات الشبكة المحلية."""
import re, socket, ipaddress


def lan_ips():
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        ips.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    out = []
    for i in ips:
        try:
            if ipaddress.ip_address(i).is_private and not i.startswith('127.'):
                out.append(i)
        except ValueError:
            pass
    return sorted(out)


def host_allowed(hostheader, lan):
    h = re.sub(r':\d+$', '', (hostheader or '').strip()).strip('[]')
    if h in ('127.0.0.1', 'localhost', '::1'):
        return True
    if lan:
        try:
            return ipaddress.ip_address(h).is_private
        except ValueError:
            return False
    return False
