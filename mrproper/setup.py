from setuptools import setup, find_packages

setup(
    name='mrproper',
    version='1.0',
    scripts=['bin/mrproper-clang-format',
             'bin/mrproper-message',
             'bin/rate-my-mr'],
    packages=find_packages(),
)
