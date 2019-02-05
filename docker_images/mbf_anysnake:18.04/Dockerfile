FROM ubuntu:18.04 
RUN sed -Ei 's/^# deb-src /deb-src /' /etc/apt/sources.list
RUN apt-get update
ENV DEBIAN_FRONTEND noninteractive
RUN apt-get install -y \
 adduser\
 apt\
 base-files\
 base-passwd\
 bash\
 bsdutils\
 build-essential\
 build-essential\
 bzip2\
 ca-certificates\
 coreutils\
 curl\
 dash\
 debconf\
 debianutils\
 diffutils\
 dpkg\
 e2fsprogs\
 fdisk\
 findutils\
 gcc-8-base\
 gfortran\
 git\
 gpgv\
 grep\
 gzip\
 hostname\
 init-system-helpers\
 libacl1\
 libapt-pkg5.0\
 libattr1\
 libaudit1\
 libaudit-common\
 libblkid1\
 libbz2-1.0\
 libc6\
 libcap-ng0\
 libc-bin\
 libcom-err2\
 libdb5.3\
 libdebconfclient0\
 libext2fs2\
 libfdisk1\
 libffi6\
 libgcc1\
 libgcrypt20\
 libgmp10\
 libgnutls30\
 libgpg-error0\
 libhogweed4\
 libidn2-0\
 liblz4-1\
 liblzma5\
 libmount1\
 libncurses5\
 libncursesw5\
 libnettle6\
 libp11-kit0\
 libpam0g\
 libpam-modules\
 libpam-modules-bin\
 libpam-runtime\
 libpcre3\
 libprocps6\
 libseccomp2\
 libselinux1\
 libsemanage1\
 libsemanage-common\
 libsepol1\
 libsmartcols1\
 libss2\
 libssl1.0.0\
 libssl1.1\
 libstdc++6\
 libsystemd0\
 libtasn1-6\
 libtinfo5\
 libudev1\
 libunistring2\
 libuuid1\
 libzstd1\
 llvm\
 login\
 lsb-base\
 make\
 mawk\
 mount\
 ncurses-base\
 ncurses-bin\
 openjdk-8-jdk\
 openjdk-8-jre\
 passwd\
 perl-base\
 procps\
 sed\
 sensible-utils\
 sysvinit-utils\
 tar\
 tzdata\
 ubuntu-keyring\
 util-linux\
 vim\
 wget\
 xz-utils\
 zlib1g\
 libz-dev

RUN apt-get install -y libopenblas-base libreadline-dev tcl8.6-dev libopenmpi-dev gsl-bin libgsl23 libgsl0-dev libopenblas-base libopenblas-dev libpcre2-dev libpcre2-posix0 libcurl4-openssl-dev
RUN apt-get install -y libbz2-dev libssl-dev liblzma-dev libxmlsec1-dev libxml2-dev tk-dev libncurses5-dev libsqlite3-dev 
#RUN apt-get build-dep -y r-base
RUN apt-get install -y   autoconf automake autopoint bash-completion bison \
  bsdmainutils debhelper \
  default-jdk default-jdk-headless default-jre default-jre-headless \
  dh-autoreconf dh-strip-nondeterminism fonts-lmodern gettext gettext-base \
  gir1.2-freedesktop gir1.2-pango-1.0 groff-base intltool-debian \
  libarchive-zip-perl libbison-dev libblas-dev libblas3 \
  libcairo-script-interpreter2 libcairo2-dev libcupsimage2 \
  libfile-stripnondeterminism-perl libgs9 libgs9-common libidn11 libijs-0.35 \
  libjbig-dev libjbig2dec0 libjpeg-dev libjpeg-turbo8-dev libjpeg8-dev \
  libkpathsea6 liblapack-dev liblapack3 liblzo2-2 libmime-charset-perl \
  libpango1.0-dev libpangoxft-1.0-0 libpaper-utils libpaper1 libpixman-1-dev \
  libpoppler73 libpotrace0 libpython-stdlib libpython2.7-minimal \
  libpython2.7-stdlib libsigsegv2 libsombok3  \
  libtiff5-dev libtiffxx5 \
  libtimedate-perl libunicode-linebreak-perl libxcb-render0-dev \
  libxcb-shm0-dev libxfont2 libxkbfile1 libxml-libxml-perl \
  libxml-namespacesupport-perl libxml-sax-base-perl libxml-sax-perl \
  libzzip-0-13 m4 man-db mpack openjdk-11-jdk openjdk-11-jdk-headless \
  openjdk-11-jre openjdk-11-jre-headless po-debconf poppler-data \
  python python-minimal python2.7 python2.7-minimal \
  t1utils x11-xkb-utils xdg-utils xfonts-base \
  xfonts-encodings xfonts-utils xserver-common xvfb
# cleaned up python3.6 build-dep
RUN apt-get install -y blt-dev cpp-8 docutils-common g++-8 gcc-8 libasan5  libdb-dev libdb5.3-dev libgcc-8-dev libgdbm-dev libmpdec-dev libncursesw5-dev libsqlite3-dev libssl-dev libstdc++-8-dev libtext-unidecode-perl libubsan1 quilt xvfb

RUN addgroup --gid 2000 g2000

RUN useradd --uid 1000 --gid 2000 --home=/home/u1000 --create-home -p "$1$/wnlZvR6$/5QtKalJDVsM4lVvsmgMy0"--shell=/bin/bash u1000
RUN useradd --uid 1001 --gid 2000 --home=/home/u1001 --create-home -p "$1$/wnlZvR6$/5QtKalJDVsM4lVvsmgMy0"--shell=/bin/bash u1001
RUN useradd --uid 1002 --gid 2000 --home=/home/u1002 --create-home -p "$1$/wnlZvR6$/5QtKalJDVsM4lVvsmgMy0"--shell=/bin/bash u1002
RUN useradd --uid 1003 --gid 2000 --home=/home/u1003 --create-home -p "$1$/wnlZvR6$/5QtKalJDVsM4lVvsmgMy0"--shell=/bin/bash u1003
RUN useradd --uid 1004 --gid 2000 --home=/home/u1004 --create-home -p "$1$/wnlZvR6$/5QtKalJDVsM4lVvsmgMy0" --shell=/bin/bash u1004
RUN apt-get -y install fish libudunits2-0 libudunits2-dev
