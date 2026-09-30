from setuptools import setup, find_packages

setup(
    name="django-flex-blog",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,
    license="MIT",
    description="A flexible, customizable Django blog system",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/django-flex-blog",
    author="Your Name",
    author_email="your.email@example.com",
    classifiers=[
        "Environment :: Web Environment",
        "Framework :: Django",
        "Framework :: Django :: 4.2",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
    ],
    python_requires=">=3.8",
    install_requires=[
        "Django>=3.2",
        "djangorestframework>=3.12.0",
        "django-filter>=21.1",
        "django-taggit>=3.0.0",
        "django-mptt>=0.13.4",  # For hierarchical categories
        "Pillow>=9.0.0",        # For image handling
        "python-slugify>=6.1.1", # For slug generation
    ],
)