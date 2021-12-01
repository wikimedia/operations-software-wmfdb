"""wmfdb."""
from setuptools import setup

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="wmfdb",
    description="wmfdb",
    version="0.0.1",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://gerrit.wikimedia.org/r/admin/repos/operations%2Fsoftware%2Fwmfdb",
    packages=("wmfdb",),
    install_requires=["pymysql>=0.9.3"],
    test_suite="wmfdb.tests",
    entry_points={
        "console_scripts": [
            # cli_admin
            "db-mysql = wmfdb.cli_admin.db_mysql:main",
        ]
    },
)
