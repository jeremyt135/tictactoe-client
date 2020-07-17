from setuptools import setup, find_packages

setup(
    name='jt.tictactoe',
    version='1.0.0a',
    packages=find_packages(),
    install_requires=[
        'pysimplegui>=4.24.0'
    ],
    scripts=['bin/tictactoe-client']
)
