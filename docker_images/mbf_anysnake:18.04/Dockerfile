FROM ubuntu:18.04 
RUN sed -Ei 's/^# deb-src /deb-src /' /etc/apt/sources.list
RUN apt-get update
ENV DEBIAN_FRONTEND noninteractive

RUN addgroup --gid 2000 g2000

RUN useradd --uid 1000 --gid 2000 --home=/home/u1000 --create-home -p "$1$/wnlZvR6$/5QtKalJDVsM4lVvsmgMy0"--shell=/bin/bash u1000
RUN useradd --uid 1001 --gid 2000 --home=/home/u1001 --create-home -p "$1$/wnlZvR6$/5QtKalJDVsM4lVvsmgMy0"--shell=/bin/bash u1001
RUN useradd --uid 1002 --gid 2000 --home=/home/u1002 --create-home -p "$1$/wnlZvR6$/5QtKalJDVsM4lVvsmgMy0"--shell=/bin/bash u1002
RUN useradd --uid 1003 --gid 2000 --home=/home/u1003 --create-home -p "$1$/wnlZvR6$/5QtKalJDVsM4lVvsmgMy0"--shell=/bin/bash u1003
RUN useradd --uid 1004 --gid 2000 --home=/home/u1004 --create-home -p "$1$/wnlZvR6$/5QtKalJDVsM4lVvsmgMy0" --shell=/bin/bash u1004

RUN apt-get install -y \
  adduser\
  apt\
  autoconf\
  automake autopoint bash-completion bison \
  base-files\
  base-passwd\
  bash\
  blt-dev\
  bsdmainutils\
  bsdutils\
  build-essential\
  build-essential\
  bzip2\
  ca-certificates\
  coreutils\
  cpp-8\
  curl\
  dash\
  debconf\
  debhelper \
  debianutils\
  default-jdk\
  default-jdk-headless\
  default-jre\
  default-jre-headless\
  dh-autoreconf\
  dh-strip-nondeterminism\
  diffutils\
  docutils-common\
  dpkg\
  e2fsprogs\
  fdisk\
  findutils\
  fish \
  fonts-lmodern\
  g++-8\
  gcc-8\
  gcc-8-base\
  gettext\
  gettext-base\
  gfortran\
  gir1.2-freedesktop\
  gir1.2-pango-1.0\
  git\
  gpgv\
  grep\
  groff-base\
  gsl-bin \
  gzip\
  hostname\
  init-system-helpers\
  intltool-debian\
  jags \
  libacl1\
  libapt-pkg5.0\
  libarchive-zip-perl\
  libasan5\
  libattr1\
  libaudit1\
  libaudit-common\
  libbison-dev\
  libblas3\
  libblas-dev\
  libblkid1\
  libbz2-1.0\
  libbz2-dev \
  libc6\
  libcairo2-dev\
  libcairo-script-interpreter2\
  libcap-ng0\
  libc-bin\
  libcom-err2\
  libcupsimage2\
  libcurl4-openssl-dev\
  libdb5.3\
  libdb5.3-dev\
  libdb-dev\
  libdebconfclient0\
  libext2fs2\
  libfdisk1\
  libffi6\
  libfile-stripnondeterminism-perl\
  libgcc1\
  libgcc-8-dev\
  libgcrypt20\
  libgdbm-dev\
  libgmp10\
  libgnutls30\
  libgpg-error0\
  libgraphicsmagick1-dev \
  libgs9\
  libgs9-common\
  libgsl0-dev \
  libgsl23 \
  libhogweed4\
  libidn11\
  libidn2-0\
  libijs-0.35\
  libjbig2dec0\
  libjbig-dev\
  libjpeg8-dev\
  libjpeg-dev\
  libjpeg-turbo8-dev\
  libkpathsea6\
  liblapack3\
  liblapack-dev\
  liblz4-1\
  liblzma5\
  liblzma-dev \
  liblzo2-2\
  libmagick++-dev \
  libmime-charset-perl\
  libmount1\
  libmpdec-dev\
  libmpfr-dev \
  libncurses5\
  libncurses5-dev \
  libncursesw5\
  libncursesw5-dev\
  libnetcdf-dev \
  libnettle6\
  libopenbabel-dev \
  libopenblas-base \
  libopenblas-base \
  libopenblas-dev \
  libopenmpi-dev \
  libp11-kit0\
  libpam0g\
  libpam-modules\
  libpam-modules-bin\
  libpam-runtime\
  libpango1.0-dev\
  libpangoxft-1.0-0\
  libpaper1\
  libpaper-utils\
  libpcre2-dev \
  libpcre2-posix0 \
  libpcre3\
  libpixman-1-dev\
  libpoppler73\
  libpotrace0\
  libprocps6\
  libpython2.7-minimal\
  libpython2.7-stdlib\
  libpython-stdlib\
  libreadline-dev \
  libsasl2-dev \
  libseccomp2\
  libselinux1\
  libsemanage1\
  libsemanage-common\
  libsepol1\
  libsigsegv2\
  libsmartcols1\
  libsombok3\
  libsqlite3-dev\
  libsqlite3-dev \
  libss2\
  libssl1.0.0\
  libssl1.1\
  libssl-dev\
  libssl-dev \
  libstdc++6\
  libstdc++-8-dev\
  libsystemd0\
  libtasn1-6\
  libtext-unidecode-perl\
  libtiff5-dev\
  libtiffxx5\
  libtimedate-perl\
  libtinfo5\
  libubsan1\
  libudev1\
  libudunits2-0 \
  libudunits2-dev \
  libunicode-linebreak-perl\
  libunistring2\
  libuuid1\
  libxcb-render0-dev\
  libxcb-shm0-dev\
  libxfont2\
  libxkbfile1\
  libxml2-dev \
  libxml-libxml-perl\
  libxml-namespacesupport-perl\
  libxml-sax-base-perl\
  libxml-sax-perl\
  libxmlsec1-dev \
  libz-dev\
  libzstd1\
  libzzip-0-13\
  llvm\
  login\
  lsb-base\
  m4\
  make\
  man-db\
  mawk\
  mesa-common-dev \
  mount\
  mpack\
  ncurses-base\
  ncurses-bin\
  openjdk-11-jdk\
  openjdk-11-jdk-headless\
  openjdk-11-jre\
  openjdk-11-jre-headless\
  openjdk-8-jdk\
  openjdk-8-jre\
  passwd\
  perl-base\
  po-debconf\
  poppler-data\
  procps\
  python\
  python2.7\
  python2.7-minimal\
  python-minimal\
  quilt\
  sed\
  sensible-utils\
  sysvinit-utils\
  t1utils\
  tar\
  tcl8.6-dev \
  tk-dev \
  tzdata\
  ubuntu-keyring\
  util-linux\
  vim\
  wget\
  x11-xkb-utils\
  xdg-utils\
  xfonts-base\
  xfonts-encodings\
  xfonts-utils\
  xserver-common\
  xvfb\
  xvfb\
  xz-utils\
  zlib1g


RUN apt-get install -y libcgal-dev libglu1-mesa-dev libglu1-mesa-dev libsbml5-dev libfftw3-dev freeglut3-dev bwidget libmariadbclient-dev libgtkmm-2.4-dev gtk2.0 libgtk2.0-dev libhts-dev mercurial


#MSGFplus needs a patch to work in ubuntu 18.04 with newer java version see https://github.com/thomasp85/MSGFplus/pull/13
