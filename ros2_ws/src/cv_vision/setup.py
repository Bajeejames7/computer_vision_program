from glob import glob

from setuptools import find_packages, setup

package_name = 'cv_vision'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
        ('share/' + package_name + '/config', glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Bajeejames7',
    maintainer_email='bajeejames3@outlook.com',
    description='Motion + hand detection ROS2 nodes',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'motion_node = cv_vision.motion_node:main',
            'hand_node = cv_vision.hand_node:main',
            'overlay_node = cv_vision.overlay_node:main',
        ],
    },
)
