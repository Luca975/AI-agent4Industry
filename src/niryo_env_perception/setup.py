import os
from glob import glob

from setuptools import find_packages, setup

package_name = 'niryo_env_perception'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Luca',
    maintainer_email='lu.cardellicchio@studenti.unina.it',
    description='Environmental perception publisher (mocked vision stage).',
    license='BSD-3-Clause',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'env_perception = niryo_env_perception.env_perception_node:main',
        ],
    },
)