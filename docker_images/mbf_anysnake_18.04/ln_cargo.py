#!/usr/bin/python
import os
import glob
import stat
for binary in glob.glob("/opt/rust/bin/*"):
    is_executable = os.access(binary, os.X_OK)
    if is_executable:
        p = "/usr/local/bin/" + os.path.basename(binary)
        with open(p, 'w') as op:
            op.write("""#!/bin/sh

RUSTUP_HOME=/opt/rust exec /opt/rust/bin/${0##*/} "$@"
""")
        st = os.stat(p)
        os.chmod(p, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
