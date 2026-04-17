from setuptools import setup, find_packages

setup(
    name="yoopi-sentinel",
    version="0.1.0",
    author="Yoopi Technologies",
    description="Honest, lightweight server monitoring with Telegram alerts",
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
