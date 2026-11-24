"""从用户配置的目录读取新录制，保留原文件。"""

import json
import logging
from pathlib import Path
import sqlite3
from stat import S_ISREG
from threading import Event, Lock, Thread
from uuid import uuid4

from .models import TelemetryError
from .web_service import ImportRejected


def file_stamp(stat):
    return [stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino]


class DirectoryImport:
    def __init__(self, directory, service, driver_id, max_bytes):
        self.settings_file = directory / 'auto-import.json'
        self.archive_files = (directory / 'recordings').resolve()
        self.service = service
        self.driver_id = driver_id
        self.max_bytes = max_bytes
        self.lock = Lock()
        self.stop_event = Event()
        self.worker = None
        self.config = {'directory': None, 'processed': {}}
        self.status = {'state': 'idle'}
        try:
            config = json.loads(self.settings_file.read_text(encoding='utf-8'))
            path = config.get('directory')
            processed = config.get('processed')
            if (path is not None and (not isinstance(path, str) or not Path(path).is_absolute())
                    or not isinstance(processed, dict)):
                raise ValueError('Invalid directory import settings')
            self.config = {'directory': path, 'processed': processed}
        except FileNotFoundError:
            pass
        except (OSError, ValueError, AttributeError):
            logging.exception('读取自动导入设置失败')
            self.status['error'] = '读取自动导入设置失败，请在设置里重新保存目录。'

    def snapshot(self):
        with self.lock:
            return {'directory': self.config['directory'],
                    'scan': {**self.status, 'issues': list(self.status.get('issues', []))}}

    def _store(self, config):
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        staged = self.settings_file.with_suffix(f'.{uuid4().hex}.tmp')
        try:
            staged.write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
            staged.replace(self.settings_file)
        finally:
            staged.unlink(missing_ok=True)
        self.config = config

    def configure(self, value):
        directory = None
        if value:
            path = Path(value).expanduser()
            if not path.is_absolute():
                raise ValueError('请输入完整的遥测目录路径。')
            try:
                path = path.resolve(strict=True)
            except (OSError, RuntimeError) as error:
                raise ValueError('无法打开该路径，请检查目录是否存在及是否有访问权限。') from error
            if not path.is_dir():
                raise ValueError('请选择文件夹。')
            if path.is_relative_to(self.archive_files):
                raise ValueError('请选择游戏遥测目录，软件档案的 recordings 文件夹用于保存导入副本。')
            directory = str(path)
        with self.lock:
            if directory != self.config['directory'] or 'error' in self.status:
                processed = self.config['processed'] if directory == self.config['directory'] else {}
                self._store({'directory': directory, 'processed': processed})
                if self.status['state'] != 'running':
                    self.status = {'state': 'idle'}

    def start(self):
        with self.lock:
            source = self.config['directory']
            if not source:
                raise ValueError('请先保存遥测目录。')
            if self.status['state'] == 'running':
                return
            self.stop_event.clear()
            self.status = dict(state='running', id=uuid4().hex, directory=source, total=0, done=0, current=None,
                               imported=0, duplicate=0, filtered=0, unchanged=0, deferred=0, failed=0, issues=[])
            self.worker = Thread(target=self._scan, args=(Path(source), dict(self.config['processed'])),
                                 daemon=True, name='telemetry-directory-import')
            self.worker.start()

    def stop(self):
        self.stop_event.set()
        if self.worker:
            self.worker.join()

    def _report(self, path, result, message=None):
        with self.lock:
            self.status[result] += 1
            self.status['done'] += 1
            if message and len(self.status['issues']) < 15:
                self.status['issues'].append({'filename': path.name, 'message': message})

    def _scan(self, source, processed):
        remembered = {}
        failure = None
        try:
            paths = []
            for path in source.iterdir():
                if path.suffix.lower() != '.duckdb' or path.is_symlink():
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    paths.append((0, path))
                    continue
                if S_ISREG(stat.st_mode):
                    paths.append((stat.st_mtime_ns, path))
            paths.sort(key=lambda item: (-item[0], item[1].name.casefold()))
            with self.lock:
                self.status['total'] = len(paths)
            self.service.repository.ensure_driver(self.driver_id, '本地车手')
            for _, path in paths:
                if self.stop_event.is_set():
                    break
                with self.lock:
                    self.status['current'] = path.name
                self._process(path, processed, remembered)
        except OSError:
            logging.exception('读取遥测目录失败')
            failure = '无法读取配置的遥测目录，请检查路径和访问权限。'
        except Exception:
            logging.exception('自动导入失败')
            failure = '自动导入未完成，请查看日志或重试。'
        finally:
            with self.lock:
                if not failure and self.config['directory'] == str(source):
                    try:
                        if self.stop_event.is_set():
                            remembered = {**processed, **remembered}
                        if remembered != self.config['processed']:
                            self._store({'directory': str(source), 'processed': remembered})
                    except OSError:
                        logging.exception('保存自动导入记录失败')
                        failure = '当前导入结果已写入档案，但自动导入记录保存失败。'
                self.status.update(state='finished', current=None, error=failure)

    def _process(self, path, processed, remembered):
        """复制仍稳定的记录，再通过和手动导入相同的校验入库。"""
        staging = None
        try:
            stamp = file_stamp(path.stat())
            wal = path.with_name(path.name + '.wal')
            if wal.exists():
                self._report(path, 'deferred', '检测到写入日志，待录制结束后重试。')
                return
            if processed.get(path.name) == stamp:
                remembered[path.name] = stamp
                self._report(path, 'unchanged')
                return
            if not stamp[0] or stamp[0] > self.max_bytes or len(path.name) > 240:
                self._report(path, 'filtered', '文件为空、超过导入大小上限，或文件名过长。')
                remembered[path.name] = stamp
                return
            staging = self.service.blobs.new_staging()
            size = 0
            with path.open('rb') as origin, staging.open('xb') as target:
                while chunk := origin.read(1024 * 1024):
                    size += len(chunk)
                    if size > stamp[0] or self.stop_event.is_set():
                        break
                    target.write(chunk)
            if self.stop_event.is_set():
                return
            if size != stamp[0] or file_stamp(path.stat()) != stamp or wal.exists():
                self._report(path, 'deferred', '文件在读取期间有变化，稍后重试。')
                return
            self.service.import_file(self.driver_id, staging, path.name)
            remembered[path.name] = stamp
            self._report(path, 'imported')
        except ImportRejected as error:
            remembered[path.name] = stamp
            if error.code == 'duplicate':
                self._report(path, 'duplicate')
            else:
                self._report(path, 'filtered', str(error))
        except (OSError, TelemetryError, sqlite3.Error):
            logging.exception('读取目录中的遥测失败 %s', path.name)
            self._report(path, 'failed', '暂时无法解析或读取，检查文件后可重试。')
        finally:
            if staging is not None:
                staging.unlink(missing_ok=True)
