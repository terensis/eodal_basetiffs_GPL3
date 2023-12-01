
from setuptools import setup


setup(
    author='Lukas Valentin Graf, Terensis, Zurich, Switzerland',
    name='eodal_basetiffs',
    version=0.1,
    packages=['eodal_basetiffs'],
    entry_points={
        'console_scripts': [
            'eodal_basetiffs = eodal_basetiffs.main:cli'
        ]
    },
    license='GPLv3',
    long_description=open('README.md').read(),
    description='A tool to download satellite data, pre-process it and store it as cloud-optimized GeoTIFFs based on EOdal.',
    install_requires=[
        'eodal==0.2.4',
        'rio-cogeo'
    ],
)
