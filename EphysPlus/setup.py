from setuptools import setup, find_packages

setup(
    name='ephysplus',
    version='0.1.0',
    description="Ephys analysis and visaulization tool for MaxWell MEA",
    python_requires='>=3.10.0',
    install_requires=['numpy',
                      'scipy',
                      'matplotlib',
                      'seaborn',
                      'pandas',
                      'plotly',
                      'braingeneers[iot, analysis, data]'
                    #   "braingeneerspy @ git+https://github.com/braingeneers/braingeneerspy.git#egg=braingeneerspy[iot,analysis,data]"
                    ],
    author="Sury@Braingeneers",
    packages=find_packages()
)