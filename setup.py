from setuptools import setup, find_packages

setup(
    name='neuronum',
    version = '2026.06.10',
    author='Neuronum Cybernetics',
    author_email='welcome@neuronum.net',
    description='Neuronum SDK',
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://neuronum.net",
    project_urls={
        "GitHub": "https://github.com/neuronumcybernetics/neuronum-sdk-python",
    },
    packages=find_packages(include=["neuronum"]),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    install_requires=[
        'aiohttp',
        'aiofiles',
        'click',
        'questionary',
        'requests',
        'cryptography',
        'bip_utils',
        'fastmcp',
    ],
    entry_points={
        "console_scripts": [
            "neuronum=neuronum.cli:cli",
            "neuronum-mcp=neuronum.mcp:main",
        ]
    },
    python_requires='>=3.8', 
)
