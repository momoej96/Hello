# -*- coding: utf-8 -*-
"""مشغّل البرنامج: يشغّل الخادم المحلي ثم يفتح نافذة المتصفح (وضع تطبيق إن توفر Edge/Chrome)."""
import os, sys, shutil, socket, subprocess, threading, time, webbrowser
APP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP)
import server
from netutil import lan_ips

def port_open(p):
    try:
        socket.create_connection(('127.0.0.1', p), 0.3).close(); return True
    except OSError:
        return False

def open_window(url):
    cands = [shutil.which('msedge'), shutil.which('chrome'), shutil.which('google-chrome'),
             r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
             r'C:\Program Files\Google\Chrome\Application\chrome.exe', r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe']
    for c in cands:
        if c and os.path.exists(c):
            try:
                subprocess.Popen([c, '--app=' + url, '--window-size=1366,850']); return
            except OSError:
                pass
    webbrowser.open(url)

def main():
    demo = '--demo' in sys.argv
    lan = '--lan' in sys.argv
    port = 8766 if demo else 8765
    url = 'http://127.0.0.1:%d/' % port
    if port_open(port):
        print('Already running - opening window.'); open_window(url); return
    data = os.path.join(APP, 'demo_data' if demo else 'data')
    srv = server.make_server(data, port, demo, lan)
    if demo:
        import seed_demo; seed_demo.seed_if_empty(srv.clinic)
    print('=' * 60)
    print(' Dental clinic program is running (DO NOT close this window)')
    print(' Address:', url)
    print(' Data folder:', srv.clinic.data_dir)
    if lan:
        print(' NETWORK MODE: other laptops/phones on the same Wi-Fi can open:')
        for ip in lan_ips():
            print('     http://%s:%d/' % (ip, port))
        print(' (If Windows asks about the firewall, allow access on PRIVATE networks.)')
    print(' Close this window to stop the program.')
    print('=' * 60, flush=True)
    threading.Thread(target=lambda: (time.sleep(0.6), open_window(url)), daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()
