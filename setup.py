from setuptools import setup, find_packages

setup(
    name="flezen",
    version="1.0.0",
    description="Python client SDK for Flezen API (flezen.com)",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Flezen Community",
    packages=find_packages(),
    install_requires=[
        "requests>=2.25.0",
    ],
    python_requires=">=3.8",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
