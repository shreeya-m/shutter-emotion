from glob import glob

from setuptools import setup

package_name = 'shutter_emotion'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'README.md']),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
        ('share/' + package_name + '/config', glob('config/*')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='shutter-emotion team',
    maintainer_email='noreply@example.com',
    description='Shutter mirrors human affect with 9 scripted behaviors.',
    license='MIT',
    entry_points={
        'console_scripts': [
            'fake_affect = shutter_emotion.fake_affect:main',
            'behavior_controller = shutter_emotion.behavior_controller:main',
        ],
    },
)
