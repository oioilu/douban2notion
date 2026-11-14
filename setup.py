from setuptools import setup, find_packages

setup(
    version="0.0.14",
    packages=find_packages(),
    install_requires=[
        "requests",
        "pendulum",
        "retrying",
        "notion-client",
        "Pillow",
        "python-dotenv",
        "beautifulsoup4",
        "lxml",
    ],
    entry_points={
        "console_scripts": [
            "douban = douban2notion.douban:main",
            "heatmap = douban2notion.heatmap_png:main",
        ],
    },
    author="oioi",
    author_email="oioi@users.noreply.github.com",
    description="自动将豆瓣电影和豆瓣读书同步到Notion",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/oioilu/douban2notion",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
)
