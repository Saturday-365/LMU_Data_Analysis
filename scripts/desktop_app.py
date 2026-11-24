"""Windows 桌面入口，在独立 WebView2 窗口中显示本机遥测工作台。"""

import argparse
from contextlib import contextmanager
import ctypes
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import os
import socket
import sys
from threading import Thread
from time import monotonic, sleep

import uvicorn
import webview

if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from lmu_data_analysis.web_app import create_app

TITLE = 'LMU 个人遥测工作台 V0.6'
APP_DIR = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local') / 'LMU Data Analysis'


@contextmanager
def lock_data(directory):
    import msvcrt

    directory.mkdir(parents=True, exist_ok=True)
    with (directory / '.instance.lock').open('a+b') as lock:
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise RuntimeError('此档案已在另一个窗口中打开。请使用已打开的窗口。') from error
        yield


def run_window(data_dir, report):
    if getattr(sys, 'frozen', False):
        resources = Path(sys._MEIPASS) / 'web'
    else:
        resources = Path(__file__).resolve().parents[1] / 'web'
    app = create_app(data_dir, web_dir=resources)
    smoke_result = {}
    with socket.socket() as listener:
        # 由系统分配空闲端口，同一个套接字直接交给服务，避免重复绑定。
        listener.bind(('127.0.0.1', 0))
        url = f'http://127.0.0.1:{listener.getsockname()[1]}'
        server = uvicorn.Server(uvicorn.Config(app, loop='asyncio', http='h11', ws='none',
                                               log_config=None, access_log=False, timeout_graceful_shutdown=8))
        worker = Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
        worker.start()
        try:
            deadline = monotonic() + 15
            while worker.is_alive() and not server.started and monotonic() < deadline:
                sleep(.05)
            if not server.started:
                raise RuntimeError('本地服务启动失败，请查看日志。')

            window = webview.create_window(TITLE, url, width=1460, height=920, min_size=(860, 650),
                                           background_color='#121517', hidden=report is not None)

            def choose_telemetry_directory():
                selected = window.create_file_dialog(webview.FileDialog.FOLDER)
                return selected[0] if selected else None

            window.expose(choose_telemetry_directory)

            def check_window():
                try:
                    if webview.renderer != 'edgechromium':
                        raise RuntimeError('需要 Microsoft Edge WebView2 Runtime。')
                    if report is None:
                        return
                    if not window.events.loaded.wait(20):
                        raise RuntimeError('桌面页面加载超时。')
                    deadline = monotonic() + 15
                    while monotonic() < deadline:
                        # 等首页从本地服务读完档案，避免把空白页面视为启动成功。
                        info = window.evaluate_js("""(() => {
                          const loading = document.getElementById('archive-loading');
                          const canChoose = typeof window.pywebview?.api?.choose_telemetry_directory === 'function';
                          return loading?.hidden && canChoose ? {
                            title: document.title,
                            archive: document.getElementById('archive-title').textContent,
                            sessions: Number(document.getElementById('session-count').textContent),
                            folder_picker: canChoose
                          } : null;
                        })()""")
                        if info:
                            smoke_result.update(info, renderer=webview.renderer)
                            return
                        sleep(.15)
                    raise RuntimeError('本地档案未能加载。')
                except Exception as error:
                    smoke_result['error'] = str(error)
                    if report is None:
                        window.destroy()
                finally:
                    if report is not None:
                        window.destroy()

            # 由 WebView2 通过 Windows 保存对话框导出档案。
            webview.settings['ALLOW_DOWNLOADS'] = True
            webview.start(check_window, gui='edgechromium', private_mode=True,
                          storage_path=str(data_dir / 'webview'))
        finally:
            server.should_exit = True
            worker.join(timeout=10)
    if report is not None:
        smoke_result['frozen'] = getattr(sys, 'frozen', False)
        smoke_result['passed'] = smoke_result.get('renderer') == 'edgechromium' and not worker.is_alive()
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(smoke_result, ensure_ascii=False, indent=2), encoding='utf-8')
        return 0 if smoke_result['passed'] else 1
    if 'error' in smoke_result:
        raise RuntimeError(smoke_result['error'])
    return 0


def main():
    parser = argparse.ArgumentParser(description=TITLE)
    parser.add_argument('--data-dir', type=Path, default=APP_DIR, help='会话档案目录')
    parser.add_argument('--smoke-test', type=Path, metavar='报告路径', help='验证桌面窗口后退出')
    args = parser.parse_args()
    directory = args.data_dir.resolve()
    log = directory / 'desktop.log'
    try:
        with lock_data(directory):
            handler = RotatingFileHandler(log, maxBytes=500_000, backupCount=2, encoding='utf-8')
            logging.basicConfig(handlers=[handler], level=logging.INFO,
                                format='%(asctime)s %(levelname)s %(name)s %(message)s')
            return run_window(directory, args.smoke_test)
    except Exception as error:
        logging.exception('桌面启动失败')
        if args.smoke_test is None:
            ctypes.windll.user32.MessageBoxW(None, f'{error}\n\n日志位置\n{log}', TITLE, 0x10)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
