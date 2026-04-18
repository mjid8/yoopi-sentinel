from setuptools import setup, find_packages
from pathlib import Path

long_description = Path("README.md").read_text(encoding="utf-8")

# Read version from single source of truth
version = {}
exec(Path("sentinel/__init__.py").read_text(encoding="utf-8"), version)

setup(
    name="yoopi-sentinel",
    version=version["__version__"],
    author="Majid",
    author_email="majidbenaboud@gmail.com",
    description="Honest, lightweight server monitoring with Telegram alerts",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/mjid8/yoopi-sentinel",
    license="GPL-3.0-or-later",
    keywords="monitoring telegram server infrastructure devops",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: POSIX :: Linux",
        "Topic :: System :: Monitoring",
        "Topic :: System :: Systems Administration",
        "Intended Audience :: System Administrators",
        "Intended Audience :: Developers",
        "Environment :: No Input/Output (Daemon)",
    ],
    packages=find_packages(),
    python_requires=">=3.7",
    install_requires=[
        "requests>=2.28.0",
        "psutil>=5.9.0",
        "pyyaml>=6.0",
        "click>=8.0.0",
    ],
    extras_require={
        "docker":     ["docker>=6.0.0"],
        "postgresql": ["psycopg2-binary>=2.9.0"],
        "mysql":      ["pymysql>=1.0.0"],
        "redis":      ["redis>=4.0.0"],
        "full":       ["docker>=6.0.0", "psycopg2-binary>=2.9.0", "pymysql>=1.0.0", "redis>=4.0.0"],
    },
    entry_points={
        "console_scripts": [
            "sentinel=sentinel.cli:cli",
        ],
    },
)
