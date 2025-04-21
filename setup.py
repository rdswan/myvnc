from setuptools import setup, find_packages

setup(
    name="myvnc",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "PyQt6>=6.4.0",
        "python-lsf-api>=1.0.0",
        "pyyaml>=6.0",
        "click>=8.0.0",
        "tabulate>=0.9.0"
    ],
    entry_points={
        'console_scripts': [
            'myvnc=myvnc.main:main',
            'myvnc-cli=myvnc.cli:cli',
        ],
    },
    author="Your Name",
    author_email="your.email@example.com",
    description="A GUI application to manage VNC sessions through LSF",
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