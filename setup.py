from setuptools import setup, find_packages


def readme():
  with open('README.md', 'r') as f:
    return f.read()


setup(
  name='partest',
  version='0.1.54',
  author='dec01',
  author_email='parschin.ewg@yandex.ru',
  description='This is a module for the rapid implementation of test cases with coverage tracking. This module contains a call counter for specific endpoints and their methods. As well as the function of determining the types of tests that need to be counted.',
  long_description=readme(),
  long_description_content_type='text/markdown',
  url='https://github.com/Dec01/partest',
  packages=find_packages(exclude=['src']),
  install_requires=['httpx>=0.27.2', 'pyyaml>=6.0.2', 'matplotlib>=3.9.2', 'allure-pytest>=2.8.18', 'pytest-asyncio>=0.23.7', 'pytest==8.3.3'],
  classifiers=[
    'Programming Language :: Python :: 3',
    'License :: OSI Approved :: MIT License',
    'Operating System :: OS Independent'
  ],
  keywords='autotest partest test coverage',
  project_urls={
    'GitHub': 'https://github.com/Dec01/partest'
  },
  python_requires='>=3.8'
)
