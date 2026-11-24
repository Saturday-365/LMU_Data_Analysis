"""将 Windows 发行包中的第三方许可从构建环境复制到包内。"""

from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from shutil import copyfile
import sys


PACKAGES = (
    'annotated-doc', 'annotated-types', 'anyio', 'bottle', 'cffi', 'click',
    'clr-loader', 'duckdb', 'fastapi', 'h11', 'idna', 'packaging',
    'pycparser', 'pydantic', 'pydantic-core', 'pyinstaller',
    'pythonnet', 'pywebview', 'setuptools', 'starlette',
    'typing-extensions', 'typing-inspection', 'uvicorn',
)
OPTIONAL_PACKAGES = ('certifi', 'httpcore', 'httpx')


def copy_notice(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    copyfile(source, target)


def copy_package_notices(name, target):
    package = distribution(name)
    package_dir = target / f'{name}-{package.version}'
    for entry in package.files or []:
        if not entry.name.upper().startswith(('LICENSE', 'LICENCE', 'COPYING', 'NOTICE')):
            continue
        # 保留 dist-info 和 vendored 组件的目录，避免同名 LICENSE 相互覆盖。
        if entry.parts[0].endswith('.dist-info') or entry.parts[:2] == ('setuptools', '_vendor'):
            copy_notice(package.locate_file(entry), package_dir / entry)


def main():
    target = Path(sys.argv[1])
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    copy_notice(python_license, target / 'CPython' / python_license.name)
    for name in PACKAGES:
        copy_package_notices(name, target)
    for name in OPTIONAL_PACKAGES:
        try:
            copy_package_notices(name, target)
        except PackageNotFoundError:
            pass


if __name__ == '__main__':
    main()
