"""
Django Forms Workflows
Enterprise-grade, database-driven form builder with approval workflows
"""

from setuptools import setup, find_packages
import os

# Read the contents of README file
this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="django-forms-workflows",
    version="0.13.2",
    description="Enterprise-grade, database-driven form builder with approval workflows and external data integration",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Django Form Workflows Contributors",
    author_email="",
    url="https://github.com/opensensor/django-forms-workflows",
    license="LGPL-3.0-only",
    packages=find_packages(
        exclude=["tests", "tests.*", "example_project", "example_project.*"]
    ),
    include_package_data=True,
    zip_safe=False,
    # Python version requirement
    python_requires=">=3.10",
    # Core dependencies
    install_requires=[
        "Django>=5.1,<6.0",
        "django-crispy-forms>=2.0",
        "crispy-bootstrap5>=2.0",
        "celery>=5.3",
        "python-decouple>=3.8",
        "requests>=2.31",
    ],
    # Optional dependencies
    extras_require={
        # LDAP/Active Directory integration
        "ldap": [
            "django-auth-ldap>=4.6",
            "python-ldap>=3.4",
        ],
        # Microsoft SQL Server support
        "mssql": [
            "mssql-django>=1.6",
            "pyodbc>=5.0",
        ],
        # PostgreSQL support (recommended)
        "postgresql": [
            "psycopg2-binary>=2.9",
        ],
        # MySQL support
        "mysql": [
            "mysqlclient>=2.2",
        ],
        # Gmail API email backend
        "gmail": [
            "google-auth>=2.20",
            "google-api-python-client>=2.100",
        ],
        # Development dependencies
        "dev": [
            "pytest>=7.4",
            "pytest-django>=4.5",
            "pytest-cov>=4.1",
            "black>=23.0",
            "flake8>=6.0",
            "isort>=5.12",
            "mypy>=1.5",
            "django-stubs>=4.2",
        ],
        # Documentation
        "docs": [
            "sphinx>=7.0",
            "sphinx-rtd-theme>=1.3",
            "sphinx-autodoc-typehints>=1.24",
        ],
        # All optional dependencies
        "all": [
            "django-auth-ldap>=4.6",
            "python-ldap>=3.4",
            "mssql-django>=1.6",
            "pyodbc>=5.0",
            "psycopg2-binary>=2.9",
            "google-auth>=2.20",
            "google-api-python-client>=2.100",
        ],
    },
    # Package classifiers
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Web Environment",
        "Framework :: Django",
        "Framework :: Django :: 5.1",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    # Keywords for PyPI
    keywords=[
        "django",
        "forms",
        "workflows",
        "approval",
        "form-builder",
        "dynamic-forms",
        "ldap",
        "enterprise",
        "audit",
        "database-driven",
    ],
    # Project URLs
    project_urls={
        "Documentation": "https://django-forms-workflows.readthedocs.io/",
        "Source": "https://github.com/opensensor/django-forms-workflows",
        "Tracker": "https://github.com/opensensor/django-forms-workflows/issues",
        "Changelog": "https://github.com/opensensor/django-forms-workflows/blob/main/CHANGELOG.md",
    },
)
