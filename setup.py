from setuptools import setup, find_packages

setup(
    name='jt.tictactoe',
    version='1.0.0',
    packages=find_packages(),
    install_requires=[
        'pysimplegui>=4.24.0'
    ],
    entry_points={
        'console_scripts': [
            'tictactoe-client=tictactoe.app:main',
        ],
    },
)
