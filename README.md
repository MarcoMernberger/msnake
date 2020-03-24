# mbf_anysnake
|               |                                                                             |
|---------------|-----------------------------------------------------------------------------|
| Documentation | https://mbf_anysnake.readthedocs.io/en/latest/                              |

Version controlled, per project Python, Python packages, R, Bioconductor and CRAN,
all inside a Docker container.

Python:

 * any version of Python
 * versioned package installation from pypi
 * editable installation of libraries under development (git/mercurial)
 * two virtual environments at once, a local one and a global one for development tools 

R (optional):

 * any version of R
 * any bioconductor version (R version matched to bioconductor)
 * bioconductor version oriented CRAN version control
 * all of CRAN

Rpy2
 * always matching the Python and R version used

All this from simple, [toml](https://github.com/toml-lang/toml) based configuration file. 


This solves the problem of providing a reproducible yet flexible 
environment for bioinformatic and data science projects.


Motivations in brief: 

 * any python -> independent of os packaging -> quick updates
       solved via python-build (pyenv)
 * Bioconductor -> R version -> screen scrapping -> matching rpy2 to python versions
       -> docker volume mounts instead of inside-docker install
 * relocatable projects -> docker volume mounts abstract paths, allow relocatable
       venvs
 * dual venv - install development tools system wide, so you have always the latest jupyter
       without having to rebuild docker containers (fragile)
 * bioconductor dependes on CRAN packages of undefined version -> use microsoft 
       cran snapshot mirror and packages as of release date of bioconductor 
       (that's an approximation that may not always hold up in practice. Sometimes
       bioconductor uses package verisons that were not released when the
       bioconductor release happen. But it's a useful approximation for automatisation) 
 * some bioconductor packages require annotation/experimental data: 
       filter these packages by default, but allow user to request them 
       (this is a space saving measure. Full bioconductor software + full cran: 50 gb,
       Bioconductor minus annotation: 21 GB, Bioconductor minus and minimal cran: 5GB),
 * cran package annotation is somewhat messy (duplicate entries, non existing
       versions, missing dependencies) -> hotfix.
 * install as much of cran/bioconductor as possible: Don't fight with the stuff
       in your daily workflow -> ton of apt-packages in the docker, see
       `_inside_dockfill_bioconductor.py` for list of things that are filted
  * R install.packages (and derivates) suffers from neglect: 
       it can't cache the downloaded files, it ignores the dependencies when installing from files and whenever multi-cores
       are used. 
       It is 2019, installing on a single core is unacceptable. 
       We use a [pypipegraph](https://pypi.org/project/pypipegraph/) to work around this.



mbf_anysnake follows [semver](https://semver.org)
