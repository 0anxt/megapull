from setuptools import setup

setup(
    name="megapull",
    version="0.2.0",
    description="Async parallel MEGA.nz downloader without an account",
    packages=[""],
    package_dir={"": "."},
    python_requires=">=3.10",
    install_requires=[
        "httpx[http2]>=0.27",
        "cryptography>=42",
        "rich>=13",
    ],
    entry_points={
        "console_scripts": [
            "megapull=cli:main",
        ],
    },
)
