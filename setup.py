from setuptools import setup, find_namespace_packages

install_requires = ["astropy", "astroquery"]
tests_require = ["pytest", "pytest-cov", "pytest-flake8", "asynctest"]
dev_requires = install_requires + tests_require + ["documenteer[pipelines]"]
scm_version_template = """# Generated by setuptools_scm
__all__ = ["__version__"]

__version__ = "{version}"
"""

setup(
    name="ts_observatory_control",
    description="Observatory Control library.",
    use_scm_version={
        "write_to": "python/lsst/ts/observatory/control/version.py",
        "write_to_template": scm_version_template,
    },
    setup_requires=["setuptools_scm", "pytest-runner"],
    install_requires=install_requires,
    package_dir={"": "python"},
    packages=find_namespace_packages(where="python"),
    package_data={"": ["*.rst", "*.yaml", "*.pd"]},
    tests_require=tests_require,
    extras_require={"dev": dev_requires},
    scripts=[
        "bin/run_atcs_mock.py",
        "bin/run_comcam_mock.py",
        "bin/run_latiss_mock.py",
        "bin/run_mtcs_mock.py",
    ],
    license="GPL",
    project_urls={
        "Bug Tracker": "https://jira.lsstcorp.org/secure/Dashboard.jspa",
        "Source Code": "https://github.com/lsst-ts/ts_observatory_control",
    },
)
