#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Define the setup options."""

import os
import re
from setuptools import setup, find_packages

with open(os.path.join(os.path.dirname(__file__), "pyrga", "__init__.py")) as f:
    version = re.search("__version__ = '([^']+)'", f.read()).group(1)

with open("requirements.txt", "r") as f:
    requires = [x.strip() for x in f if x.strip()]

with open("README.md", "r") as f:
    readme = f.read()

setup(
    name="pyrga",
    version=version,
    description="Serial interface driver for SRS RGA (residual gas analyzer) mass-spectrometer",
    long_description=readme,
    long_description_content_type="text/markdown",
    keywords=["RGA", "mass spectrometry", "vacuum"],
    url="https://github.com/nagimov/pyrga",
    license="MIT License",
    packages=find_packages(),
    install_requires=requires,
    author="Ruslan Nagimov",
    author_email="nagimov@outlook.com",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Topic :: Scientific/Engineering",
        "Topic :: Scientific/Engineering :: Chemistry",
        "Topic :: Scientific/Engineering :: Interface Engine/Protocol Translator",
        "Topic :: Scientific/Engineering :: Physics",
    ],
)
