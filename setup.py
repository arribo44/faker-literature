from setuptools import find_packages, setup


with open("README.md", "r", encoding="utf-8") as readme_file:
    long_description = readme_file.read()


setup(
    name="faker-literature",
    version="0.1.0",
    description="A Faker provider for generating literature-related data",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="arribo44",
    author_email="pypi-jctranc@mailo.com",
    keywords="faker literature books authors test data",
    packages=find_packages(),
    package_data={"faker_literature": ["DATAS/*.json"]},
    include_package_data=True,
    install_requires=["faker>=20.0.0", "tinydb>=4.0.0"],
    extras_require={
        "test": ["pytest", "pytest-cov"],
    },
    python_requires=">=3.7",
    project_urls={
        "Homepage": "https://github.com/arribo44/faker-literature",
        "Documentation": "https://github.com/arribo44/faker-literature#readme",
        "Source": "https://github.com/arribo44/faker-literature",
        "Bug Tracker": "https://github.com/arribo44/faker-literature/issues",
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
