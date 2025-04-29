# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
# SPDX-License-Identifier: Apache-2.0
from setuptools import setup, find_packages

setup(
    name="myvnc",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        # No GUI dependencies or LSF API required
    ],
    entry_points={
        'console_scripts': [
            'myvnc-server=myvnc.web.server:run_server',
            'myvnc-cli=myvnc.cli.cli:main',
        ],
    },
    author="Your Name",
    author_email="your.email@example.com",
    description="A web-based application to manage VNC sessions through LSF",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/myvnc",
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