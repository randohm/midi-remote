#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

def read_requirements(file):
    with open(file) as f:
        return f.read().splitlines()

setup(
    name = "midiremote",
    version = "0.1.0",
    license = "Apache License v2.0",
    url = "https://github.com/randohm/midi-remote.git",
    description = "MIDI utility to send CC/PC messages",
    long_description = open("README.md").read(),
    packages = find_packages(),
    install_requires=read_requirements("requirements.txt"),
    scripts = ['bin/midiremote'],
    #data_files = [ ('share/mpdfront', [ 'style.css', 'logging.yml' ]) ],
)
