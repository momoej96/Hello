# -*- coding: utf-8 -*-
"""المزامنة بين لابتوبين في نفس العيادة: كل لابتوب يعمل وحده بنسخة كاملة من البيانات، ويسحب تغييرات الآخر كل 5 ثوانٍ.

- كل تعديل محلي يُسجَّل في sync_changes بمشغّلات (triggers)، مع وقته ورقم الجهاز في sync_meta.
- اللابتوب يسحب من الآخر ما تغيّر منذ آخر سحب، ويطبّقه؛ عند تعديل نفس السجل في الجهازين يُعتمد الأحدث.
- الأرقام الجديدة من مجال كل جهاز (core.SyncConn) فلا تتكرر؛ وصور الأشعة تُنسخ ملفاتها أيضاً.
- الإعداد المحلي (رقم الجهاز، الرمز، عنوان الآخر) في data/sync.json ولا يُزامَن؛ وكذلك مجلدات الأشعة.
"""
import os, json, time, secrets, sqlite3, tempfile, threading, urllib.request, urllib.parse, urllib.error
from core import ApiError, connect, audit, SYNC_DEVICE, ID_TABLES
from api import route, Response
from netutil import lan_ips

SYNCED = dict.fromkeys(ID_TABLES, 'id')
SYNCED.update({'settings': 'key', 'import_rows': 'fingerprint', 'patient_aliases': 'name_key'})
LOCAL_SETTINGS = ('xray_folder', 'xray_folder2')     # لكل لابتوب جهاز أشعته
INTERVAL = 5.0
BATCH = 500
NOW_MS = "CAST((julianday('now') - 2440587.5) * 86400000 AS INTEGER)"


class SyncError(Exception):
    pass


# ---------- الإعداد المحلي ----------
def cfg_path(clinic):
    return os.path.join(clinic.data_dir, 'sync.json')


def load_cfg(clinic):
    try:
        with open(cfg_path(clinic), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_cfg(clinic, cfg):
    tmp = cfg_path(clinic) + '.part'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
    os.replace(tmp, cfg_path(clinic))


# ---------- المشغّلات ----------
def install_triggers(db):
    for t, pk in SYNCED.items():
        for op, ref in (('INSERT', 'NEW'), ('UPDATE', 'NEW'), ('DELETE', 'OLD')):
            name = 'sync_%s_%s' % (t, op[0].lower())
            db.execute('DROP TRIGGER IF EXISTS %s' % name)
            when = '(SELECT applying FROM sync_flag) = 0'
            if t == 'settings':
                when += ' AND %s.key NOT IN (%s)' % (ref, ','.join("'%s'" % k for k in LOCAL_SETTINGS))
            db.execute('''CREATE TRIGGER %s AFTER %s ON %s WHEN %s BEGIN
                INSERT INTO sync_changes(tbl, key) VALUES('%s', %s.%s);
                INSERT INTO sync_meta(tbl, key, ts, dev) VALUES('%s', %s.%s, %s, (SELECT dev FROM sync_flag))
                  ON CONFLICT(tbl, key) DO UPDATE SET ts=excluded.ts, dev=excluded.dev;
              END''' % (name, op, t, when, t, ref, pk, t, ref, pk, NOW_MS))


def drop_triggers(db):
    for t in SYNCED:
        for o in 'iud':
            db.execute('DROP TRIGGER IF EXISTS sync_%s_%s' % (t, o))


# ---------- التشغيل ----------
def attach(clinic):
    clinic.sync = {'cfg': load_cfg(clinic), 'last_ok': None, 'error': None, 'files': set(), 'thread': None,
                   'stop': threading.Event(), 'interval': float(os.environ.get('CLINIC_SYNC_INTERVAL') or INTERVAL),
                   'conflicts': 0}
    if clinic.sync['cfg'].get('enabled'):
        activate(clinic)


def activate(clinic):
    st, cfg = clinic.sync, clinic.sync['cfg']
    SYNC_DEVICE[os.path.realpath(clinic.db_path)] = int(cfg['device'])
    db = connect(clinic.db_path)
    try:
        install_triggers(db)
        db.execute('UPDATE sync_flag SET dev=?, applying=0', (int(cfg['device']),))
        queue_missing_files(clinic, db)
    finally:
        db.close()
    st['stop'] = threading.Event()
    st['thread'] = threading.Thread(target=loop, args=(clinic,), daemon=True, name='clinic-sync')
    st['thread'].start()


def deactivate(clinic):
    st = clinic.sync
    st['stop'].set()
    SYNC_DEVICE.pop(os.path.realpath(clinic.db_path), None)
    db = connect(clinic.db_path)
    try:
        drop_triggers(db)
    finally:
        db.close()


def queue_missing_files(clinic, db):
    import xray_api
    root = xray_api.xray_dir(clinic)
    for r in db.execute("SELECT file_name FROM xrays WHERE file_name != ''"):
        if not os.path.exists(os.path.join(root, r['file_name'])):
            clinic.sync['files'].add(r['file_name'])


# ---------- الاتصال باللابتوب الآخر ----------
def peer_call(clinic, path, data=None, raw=False, timeout=15, peer=None, key=None):
    cfg = clinic.sync['cfg']
    peer = peer or cfg.get('peer')
    if not peer:
        raise SyncError('بانتظار أول اتصال من اللابتوب الآخر')
    req = urllib.request.Request('http://%s:%d%s' % (peer['host'], int(peer['port']), path),
                                 data=json.dumps(data).encode() if data is not None else None, method='POST' if data is not None else 'GET')
    req.add_header('X-Sync-Key', key or cfg.get('key') or '')
    req.add_header('X-Sync-Port', str(getattr(clinic, 'port', 0)))
    req.add_header('X-Requested-With', 'clinic')
    if data is not None:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            return (body, dict(r.headers)) if raw else json.loads(body.decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise SyncError('رمز الربط غير صحيح، أو المزامنة متوقفة في اللابتوب الآخر')
        if e.code == 404:
            raise SyncError('غير موجود', 404) if raw else SyncError('اللابتوب الآخر يعمل بنسخة قديمة من البرنامج — حدّثه')
        raise SyncError('خطأ من اللابتوب الآخر (%d)' % e.code)
    except (urllib.error.URLError, OSError, ValueError):
        raise SyncError('اللابتوب الآخر غير متصل (%s:%s)' % (peer['host'], peer['port']))


def loop(clinic):
    st = clinic.sync
    stop = st['stop']
    while not stop.is_set():
        more = False
        try:
            more = sync_once(clinic)
            st['last_ok'], st['error'] = time.time(), None
        except SyncError as e:
            st['error'] = str(e.args[0])
        except Exception as e:                       # لا يتوقف الخيط بصمت
            st['error'] = 'خطأ في المزامنة: %s' % e
        if not more:
            stop.wait(st['interval'])


def sync_once(clinic):
    st, cfg = clinic.sync, clinic.sync['cfg']
    since = int(cfg.get('since') or 0)
    d = peer_call(clinic, '/api/sync/changes?since=%d' % since)
    if d['changes']:
        with clinic.lock:
            apply_changes(clinic, d['changes'])
    if int(d['last']) != since:
        cfg['since'] = int(d['last'])
        save_cfg(clinic, cfg)
    fetch_files(clinic)
    return bool(d.get('more'))


def apply_changes(clinic, changes):
    """تطبيق تغييرات اللابتوب الآخر؛ السجل الأحدث (وقت التعديل ثم رقم الجهاز) هو المعتمد."""
    db = connect(clinic.db_path)
    cols = {}
    try:
        db.execute('PRAGMA foreign_keys=OFF')       # قد يصل السجل قبل السجل الذي يتبعه
        db.execute('BEGIN IMMEDIATE')
        db.execute('UPDATE sync_flag SET applying=1')
        for ch in changes:
            t, key = ch['t'], str(ch['k'])
            if t not in SYNCED or (t == 'settings' and key in LOCAL_SETTINGS):
                continue
            pk = SYNCED[t]
            m = db.execute('SELECT ts, dev FROM sync_meta WHERE tbl=? AND key=?', (t, key)).fetchone()
            if m and (m['ts'], m['dev']) > (ch['ts'], ch['dev']):
                continue                                  # النسخة المحلية أحدث
            if t not in cols:
                cols[t] = [r['name'] for r in db.execute('PRAGMA table_info(%s)' % t)]
            kv = int(key) if pk == 'id' else key
            db.execute('SAVEPOINT ch')
            try:
                row = ch['row']
                if row is None:
                    db.execute('DELETE FROM %s WHERE %s=?' % (t, pk), (kv,))
                else:
                    cs = [c for c in cols[t] if c in row]
                    db.execute('INSERT INTO %s(%s) VALUES(%s) ON CONFLICT(%s) DO UPDATE SET %s' % (
                        t, ','.join(cs), ','.join('?' * len(cs)), pk, ','.join('%s=excluded.%s' % (c, c) for c in cs if c != pk) or '%s=%s' % (pk, pk)),
                        [row[c] for c in cs])
                db.execute('INSERT INTO sync_meta(tbl,key,ts,dev) VALUES(?,?,?,?) ON CONFLICT(tbl,key) DO UPDATE SET ts=excluded.ts, dev=excluded.dev',
                           (t, key, ch['ts'], ch['dev']))
                db.execute('RELEASE ch')
            except sqlite3.IntegrityError as e:
                # تعارض نادر (مثل نفس اسم المستخدم في الجهازين): يبقى المحلي ويُسجَّل للمراجعة
                db.execute('ROLLBACK TO ch')
                db.execute('RELEASE ch')
                clinic.sync['conflicts'] += 1
                audit(db, 'sync', 'sync', None, 'conflict', None, {'table': t, 'key': key}, str(e)[:300])
                continue
            if t == 'xrays' and row and row.get('file_name'):
                clinic.sync['files'].add(row['file_name'])
        db.execute('UPDATE sync_flag SET applying=0')
        db.execute('COMMIT')
    except BaseException:
        if db.in_transaction:
            db.execute('ROLLBACK')
        raise
    finally:
        db.close()


def fetch_files(clinic, limit=10):
    """نسخ ملفات صور الأشعة التي وصلت سجلاتها من اللابتوب الآخر"""
    import xray_api
    root = os.path.realpath(xray_api.xray_dir(clinic))
    for name in list(clinic.sync['files'])[:limit]:
        path = os.path.realpath(os.path.join(root, name))
        if not path.startswith(root + os.sep) or os.path.exists(path):
            clinic.sync['files'].discard(name)
            continue
        try:
            data, _ = peer_call(clinic, '/api/sync/file?' + urllib.parse.urlencode({'name': name}), raw=True, timeout=60)
        except SyncError as e:
            if len(e.args) > 1 and e.args[1] == 404:
                clinic.sync['files'].discard(name)        # غير موجود عند الآخر أيضاً
                continue
            raise
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + '.part', 'wb') as f:
            f.write(data)
        os.replace(path + '.part', path)
        clinic.sync['files'].discard(name)


# ---------- المسارات ----------
def sync_auth(c):
    """طلب من اللابتوب الآخر: الرمز صحيح؟ ونحفظ عنوانه الحالي (يتغير عنوان الواي فاي أحياناً)"""
    cfg = c.clinic.sync['cfg']
    k = c.headers.get('X-Sync-Key') or ''
    if not cfg.get('enabled') or not cfg.get('key') or not secrets.compare_digest(k, cfg['key']):
        raise ApiError('مرفوض', 403, 'forbidden')
    try:
        port = int(c.headers.get('X-Sync-Port') or 0)
    except ValueError:
        port = 0
    if port and cfg.get('peer') != {'host': c.ip, 'port': port}:
        cfg['peer'] = {'host': c.ip, 'port': port}
        save_cfg(c.clinic, cfg)


def new_key():
    a = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    s = ''.join(secrets.choice(a) for _ in range(8))
    return s[:4] + '-' + s[4:]


@route('GET', '/api/sync/status', tx=False)
def sync_status(c):
    st, cfg = c.clinic.sync, c.clinic.sync['cfg']
    out = {'enabled': bool(cfg.get('enabled')), 'lan': bool(c.clinic.lan)}
    if out['enabled']:
        ago = time.time() - st['last_ok'] if st['last_ok'] else None
        out.update({'device': cfg.get('device'), 'peer': cfg.get('peer'), 'connected': ago is not None and ago < max(20, st['interval'] * 4) and not st['error'],
                    'last_ok_ago': int(ago) if ago is not None else None, 'error': st['error'], 'pending_files': len(st['files']),
                    'conflicts': st['conflicts']})
        if c.user and c.user['role'] == 'admin':
            out.update({'key': cfg.get('key'), 'addresses': ['%s:%d' % (ip, c.clinic.port) for ip in lan_ips()]})
    return out


@route('POST', '/api/sync/enable', perm='settings', tx=False)
def sync_enable(c):
    """هذا اللابتوب فيه البيانات: نفعّل المزامنة ونعطي رمز الربط للابتوب الآخر"""
    cl = c.clinic
    if cl.sync['cfg'].get('enabled'):
        raise ApiError('المزامنة مفعّلة مسبقاً')
    if not cl.lan:
        raise ApiError('شغّل البرنامج بوضع الشبكة (من أيقونة سطح المكتب) حتى يصل له اللابتوب الآخر')
    cl.sync['cfg'] = {'enabled': True, 'key': cl.sync['cfg'].get('key') or new_key(), 'device': 0, 'peer': None, 'since': 0}
    save_cfg(cl, cl.sync['cfg'])
    audit(c.db, c.user['username'], 'sync', None, 'enable', None, {'device': 0})
    activate(cl)
    return sync_status(c)


@route('POST', '/api/sync/pair', public=True, tx=False)
def sync_pair(c):
    """اللابتوب الآخر يطلب الربط بالرمز: نعطيه رقم جهازه ونبدأ نسحب منه"""
    sync_auth(c)
    cfg = c.clinic.sync['cfg']
    cfg['since'] = 0
    save_cfg(c.clinic, cfg)
    return {'device': 1 if int(cfg['device']) == 0 else 0}


@route('GET', '/api/sync/changes', public=True, tx=False)
def sync_changes(c):
    sync_auth(c)
    since = int(c.q.get('since') or 0)
    c.db.execute('DELETE FROM sync_changes WHERE seq <= ?', (since,))      # وصلت للآخر
    rows = c.db.execute('SELECT tbl, key, MAX(seq) AS s FROM sync_changes WHERE seq > ? GROUP BY tbl, key ORDER BY s LIMIT ?',
                        (since, BATCH)).fetchall()
    out = []
    for r in rows:
        t, key = r['tbl'], r['key']
        if t not in SYNCED:
            continue
        pk = SYNCED[t]
        row = c.db.execute('SELECT * FROM %s WHERE %s=?' % (t, pk), (int(key) if pk == 'id' else key,)).fetchone()
        m = c.db.execute('SELECT ts, dev FROM sync_meta WHERE tbl=? AND key=?', (t, key)).fetchone()
        out.append({'t': t, 'k': key, 'row': dict(row) if row else None, 'ts': m['ts'] if m else 0, 'dev': m['dev'] if m else 0})
    return {'changes': out, 'last': rows[-1]['s'] if rows else since, 'more': len(rows) == BATCH}


@route('GET', '/api/sync/file', public=True, tx=False)
def sync_file(c):
    sync_auth(c)
    import xray_api
    root = os.path.realpath(xray_api.xray_dir(c.clinic))
    path = os.path.realpath(os.path.join(root, c.q.get('name') or ''))
    if not path.startswith(root + os.sep) or not os.path.isfile(path):
        raise ApiError('غير موجود', 404, 'not_found')
    with open(path, 'rb') as f:
        return Response(body=f.read(), ctype='application/octet-stream')


@route('GET', '/api/sync/snapshot', public=True, tx=False)
def sync_snapshot(c):
    """نسخة كاملة من قاعدة البيانات للابتوب الذي يُربط لأول مرة"""
    sync_auth(c)
    fd, tmp = tempfile.mkstemp(suffix='.db', dir=c.clinic.data_dir)
    os.close(fd)
    try:
        dst = sqlite3.connect(tmp)
        try:
            c.db.backup(dst)
        finally:
            dst.close()
        seq = c.db.execute('SELECT COALESCE(MAX(seq), 0) FROM sync_changes').fetchone()[0]
        with open(tmp, 'rb') as f:
            data = f.read()
    finally:
        os.remove(tmp)
    return Response(body=data, ctype='application/octet-stream', headers=[('X-Sync-Seq', str(seq))])


@route('POST', '/api/sync/join', perm='settings', tx=False)
def sync_join(c):
    """ربط هذا اللابتوب بلابتوب فيه البيانات: تُستبدل بيانات هذا اللابتوب بنسخة منه (مع نسخة احتياطية قبلها)"""
    cl = c.clinic
    if cl.sync['cfg'].get('enabled'):
        raise ApiError('المزامنة مفعّلة مسبقاً في هذا اللابتوب')
    if not cl.lan:
        raise ApiError('شغّل البرنامج بوضع الشبكة (من أيقونة سطح المكتب) حتى يصل له اللابتوب الآخر')
    host = (c.body.get('host') or '').strip()
    key = (c.body.get('key') or '').strip().upper()
    port = 8765
    if ':' in host:
        host, p = host.rsplit(':', 1)
        try:
            port = int(p)
        except ValueError:
            raise ApiError('عنوان اللابتوب الآخر غير صحيح')
    host = host.replace('http://', '').strip('/ ')
    if not host or not key:
        raise ApiError('اكتب عنوان اللابتوب الآخر ورمز الربط')
    peer = {'host': host, 'port': port}
    try:
        dev = int(peer_call(cl, '/api/sync/pair', {}, peer=peer, key=key)['device'])
        data, headers = peer_call(cl, '/api/sync/snapshot', raw=True, timeout=300, peer=peer, key=key)
    except SyncError as e:
        raise ApiError(str(e.args[0]))
    seq = int({k.lower(): v for k, v in headers.items()}.get('x-sync-seq') or 0)
    local = {r['key']: r['value'] for r in c.db.execute('SELECT key, value FROM settings WHERE key IN (%s)' % ','.join('?' * len(LOCAL_SETTINGS)), LOCAL_SETTINGS)}
    username = c.user['username']
    c.db.close()
    c.db = None
    fd, tmp = tempfile.mkstemp(suffix='.db', dir=cl.data_dir)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        safety = cl.restore_from_file(tmp)            # يتحقق من الملف ويحفظ نسخة احتياطية مما كان هنا
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    db = connect(cl.db_path)
    try:
        db.execute('UPDATE sync_flag SET applying=1')  # الإعدادات المحلية لا تُرسل للآخر
        for k, v in local.items():
            db.execute('UPDATE settings SET value=? WHERE key=?', (v, k))
        db.execute('UPDATE sync_flag SET applying=0, dev=?', (dev,))
        db.execute('DELETE FROM sync_changes')
        audit(db, username, 'sync', None, 'join', None, {'device': dev, 'peer': peer, 'safety_backup': safety['name']})
    finally:
        db.close()
    cl.sync['cfg'] = {'enabled': True, 'key': key, 'device': dev, 'peer': peer, 'since': seq}
    save_cfg(cl, cl.sync['cfg'])
    activate(cl)
    return {'ok': True, 'relogin': True, 'safety_backup': safety['name']}


@route('POST', '/api/sync/disable', perm='settings', tx=False)
def sync_disable(c):
    cl = c.clinic
    if not cl.sync['cfg'].get('enabled'):
        return {'ok': True}
    cl.sync['cfg']['enabled'] = False
    save_cfg(cl, cl.sync['cfg'])
    audit(c.db, c.user['username'], 'sync', None, 'disable', None, None)
    deactivate(cl)
    return {'ok': True}


@route('PUT', '/api/sync/peer', perm='settings')
def sync_peer(c):
    cfg = c.clinic.sync['cfg']
    if not cfg.get('enabled'):
        raise ApiError('المزامنة غير مفعّلة')
    host = (c.body.get('host') or '').strip().replace('http://', '').strip('/ ')
    port = 8765
    if ':' in host:
        host, p = host.rsplit(':', 1)
        port = int(p) if p.isdigit() else 8765
    if not host:
        raise ApiError('اكتب عنوان اللابتوب الآخر')
    cfg['peer'] = {'host': host, 'port': port}
    save_cfg(c.clinic, cfg)
    return {'ok': True}
