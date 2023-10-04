from setuptools import setup, find_packages

setup(
    name='ephysplus',
    version='0.1',
    python_requires='>=3.10.0',
    install_requires=['numpy',
                      'scipy',
                      'matplotlib',
                      'seaborn',
                      'pandas'],
    packages=find_packages()
)