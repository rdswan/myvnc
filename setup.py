# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
# SPDX-License-Identifier: Apache-2.0
from setuptools import setup, find_packages

setup(
    name="myvnc",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "python-ldap>=3.4.0",
        "jinja2>=3.0.0", 
        "pytz>=2022.1",
        "msal>=1.20.0",
        "Authlib>=1.2.0",
        "requests>=2.28.1",
        "itsdangerous>=2.1.2",
        "psutil>=5.8.0",
    ],
    entry_points={
        'console_scripts': [
            'myvnc-server=myvnc.web.server:run_server',
            'myvnc-cli=myvnc.cli.cli:main',
        ],
    },
    author="Robert Swan",
    author_email="bswan@tenstorrent.com",
    description="A web-based application to manage VNC sessions through LSF",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/rdswan/myvnc",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
    python_requires=">=3.8",
) 
