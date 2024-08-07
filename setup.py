"""wmfdb."""
from setuptools import setup

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="wmfdb",
    description="wmfdb",
    version="0.1.5",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://gitlab.wikimedia.org/repos/sre/wmfdb",
    packages=["wmfdb"],
    install_requires=["pymysql>=0.9.3"],
    test_suite="wmfdb.tests",
    entry_points={
        "console_scripts": [
            # cli_admin
            "db-mysql = wmfdb.cli_admin.db_mysql:main",
        ]
    },
)
