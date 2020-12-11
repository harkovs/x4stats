from setuptools import setup, find_packages

with open('requirements.txt') as f:
    requirements = f.readlines()

setup(
    name='x4stats',
    version='0.1',
    packages=find_packages(),
    install_requires=requirements,
    entry_points=dict(console_scripts=[
        'x4stats=stats.app:main'
    ])
)
