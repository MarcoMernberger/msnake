==============
mbf_anysnake
==============

Welcome to **mbf_anysnake**, which 
abstracts ubuntu, python, R and bioconductor versions.

It's source lives at `github <https://github.com/TyberiusPrime/mbf_anysnake>`_.

Quickstart
==========

Write this to anysnake.toml

::

   [base]
   python="3.7.2"
   R="3.5.2"
   storage_path="global_anysnake_store"
   code_path="code"

   [global_python]
   jupyter=''

   [python]
   pandas=">=0.23"

Install mbf_anysnake via ``pip install mbf_anysnake``.
Get a shell inside you project via ``any_snake shell``

This will create the docker image, install python and R, create three virtual enviroments
(one global, one local, one for the rpy2 matching the R and python version), 
install jupyter and pandas, and get you a shell inside the docker.


Full configuration documentation:
==================================

[base]
------
Basic configuration.

 - python="version": which python to use
 - R="version": which R to use (optional)
 - bioconductor="version": which bioconductor to use (optional, ommit R if specifying
   bioconductor, it will automatically be determined to match)
 - docker_image="mbf_anysnake:18.04": use a custom docker image (not recommended)
 - storage_path="/path": where to store python, R, the global venv, etc
 - code_path="path": local venv and editable libraries storage location
 - global_config="/path/to/filename.toml": import lobal configuration. Local config
   directives beat global ones. Useful to share the storage_path between projects

[run]
------
Configuration for the run command

 - additional_volumes_ro = ["/outside_docker", "/inside_docker"]: map additional docker
   volumes, read only
 - additional_volumes_rw = ["/outside_docker", "/inside_docker"]: map additional docker
   volumes, read write
 - post_run = "cmd.sh": run this after executing any run command

[global_python]
---------------
Python packages to install into the 'global' venv (pth defined by base:storage_path),
optionally with version specification just like pip/requirements.txt

[python]
--------
Python packages to install into the 'local' venv (pth defined by base:storage_path),
optionally with version specification just like pip/requirements.txt

[env]
------
Additional environmental variables set inside the docker.

[bioconductor_whitelist]
------------------------
By default, bioconductor packages that need 'experimental data' or annotation packages
are not included in the install. List them in whitelist like ``chimera=""``.
Note that you will likely get more than just that package, since including it
will remove the installation block on it's prerequisites, which will in turn
possibly allow the installation of other packages that dependend on those.





Command line interface
======================
any_snake understands the following commands:

 - --help - list commands
 - shell - get a shell inside the docker
 - jupyter - run a jupyter server inside the docker (must have jupyter in either venv)
 - run whatever - run an arbitrary command inside the docker
 - rebuild - rebuild one or all all editable python packages 
 - show-config - show the config as actually parsed (including global_config)












Contents
========

.. toctree::
   :maxdepth: 2


   License <license>
   Authors <authors>
   Changelog <changelog>


Indices and tables
==================

* :ref:`genindex`
* :ref:`search`

.. _toctree: http://www.sphinx-doc.org/en/master/usage/restructuredtext/directives.html
.. _reStructuredText: http://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html
.. _references: http://www.sphinx-doc.org/en/stable/markup/inline.html
.. _Python domain syntax: http://sphinx-doc.org/domains.html#the-python-domain
.. _Sphinx: http://www.sphinx-doc.org/
.. _Python: http://docs.python.org/
.. _Numpy: http://docs.scipy.org/doc/numpy
.. _SciPy: http://docs.scipy.org/doc/scipy/reference/
.. _matplotlib: https://matplotlib.org/contents.html#
.. _Pandas: http://pandas.pydata.org/pandas-docs/stable
.. _Scikit-Learn: http://scikit-learn.org/stable
.. _autodoc: http://www.sphinx-doc.org/en/stable/ext/autodoc.html
.. _Google style: https://github.com/google/styleguide/blob/gh-pages/pyguide.md#38-comments-and-docstrings
.. _NumPy style: https://numpydoc.readthedocs.io/en/latest/format.html
.. _classical style: http://www.sphinx-doc.org/en/stable/domains.html#info-field-lists
