import os
import sys
import re
from os.path import abspath, basename, join, isdir, isfile, islink

from egginst.utils import on_win, rm_rf


verbose = False
executable = sys.executable
hashbang_pat = re.compile(r'#!.+$', re.M)


def write_exe(dst, script_type='console_scripts'):
    """
    This function is only used on Windows.   It either writes cli.exe or
    gui.exe to the destination specified, depending on script_type.

    The binary content of these files are read from the module exe_data,
    which may be generated by the following small script (run from the
    setuptools directory which contains the file cli.exe and gui.exe:
    fo = open('exe_data.py', 'w')
    for name in ['cli', 'gui']:
        data = open('%s.exe' % name, 'rb').read()
        fo.write('%s = %r\n' % (name, data))
    fo.close()
    """
    if script_type == 'console_scripts':
        from exe_data import cli as data
    elif script_type == 'gui_scripts':
        from exe_data import gui as data
    else:
        raise Exception("Did not except script_type=%r" % script_type)

    try:
        open(dst, 'wb').write(data)
    except IOError:
        # When bootstrapping, the file egginst.exe is in use and can therefore
        # not be rewritten, which is OK since its content is always the same.
        pass
    os.chmod(dst, 0755)


def create_proxy(src, bin_dir):
    """
    create a proxy of src in bin_dir (Windows only)
    """
    if verbose:
        print "Creating proxy executable to: %r" % src
    assert src.endswith('.exe')

    dst_name = basename(src)
    if dst_name.startswith('epd-'):
        dst_name = dst_name[4:]

    dst = join(bin_dir, dst_name)
    rm_rf(dst)
    write_exe(dst)

    dst_script = dst[:-4] + '-script.py'
    rm_rf(dst_script)
    fo = open(dst_script, 'w')
    fo.write('''\
#!"%(python)s"
# This proxy was created by egginst from an egg with special instructions
#
import sys
import subprocess

src = %(src)r

sys.exit(subprocess.call([src] + sys.argv[1:]))
''' % dict(python=executable, src=src))
    fo.close()
    return dst, dst_script


def create_proxies(egg):
    # This function is called on Windows only
    if not isdir(egg.bin_dir):
        os.makedirs(egg.bin_dir)

    for line in egg.lines_from_arcname('EGG-INFO/inst/files_to_install.txt'):
        arcname, action = line.split()
        if verbose:
            print "arcname=%r    action=%r" % (arcname, action)

        if action == 'PROXY':
            ei = 'EGG-INFO/'
            if arcname.startswith(ei):
                src = abspath(join(egg.meta_dir, arcname[len(ei):]))
            else:
                src = abspath(join(egg.prefix, arcname))
            if verbose:
                print "     src: %r" % src
            egg.files.extend(create_proxy(src, egg.bin_dir))
        else:
            data = egg.z.read(arcname)
            dst = abspath(join(egg.prefix, action, basename(arcname)))
            if verbose:
                print "     dst: %r" % dst
            rm_rf(dst)
            fo = open(dst, 'wb')
            fo.write(data)
            fo.close()
            egg.files.append(dst)


def write_script(path, entry_pt, egg_name):
    """
    Write an entry point script to path.
    """
    if verbose:
        print 'Creating script: %s' % path

    assert entry_pt.count(':') == 1
    module, func = entry_pt.strip().split(':')
    python = executable
    if on_win:
        if path.endswith('pyw'):
            p = re.compile('python\.exe$', re.I)
            python = p.sub('pythonw.exe', python)
        python = '"%s"' % python

    rm_rf(path)
    fo = open(path, 'w')
    fo.write('''\
#!%(python)s
# This script was created by egginst when installing:
#
#   %(egg_name)s
#
if __name__ == '__main__':
    import sys
    from %(module)s import %(func)s

    sys.exit(%(func)s())
''' % locals())
    fo.close()
    os.chmod(path, 0755)


def create(egg, conf):
    if not isdir(egg.bin_dir):
        os.makedirs(egg.bin_dir)

    for script_type in ['gui_scripts', 'console_scripts']:
        if script_type not in conf.sections():
            continue
        for name, entry_pt in conf.items(script_type):
            fname = name
            if on_win:
                exe_path = join(egg.bin_dir, '%s.exe' % name)
                try:
                    rm_rf(exe_path)
                except WindowsError:
                    pass
                write_exe(exe_path, script_type)
                egg.files.append(exe_path)
                fname += '-script.py'
                if script_type == 'gui_scripts':
                    fname += 'w'
            path = join(egg.bin_dir, fname)
            write_script(path, entry_pt, basename(egg.fpath))
            egg.files.append(path)


def fix_script(path):
    """
    Fixes a single located at path.
    """
    if islink(path) or not isfile(path):
        return

    fi = open(path)
    data = fi.read()
    fi.close()

    if ' egginst ' in data:
        # This string is in the comment when write_script() creates
        # the script, so there is no need to fix anything.
        return

    m = hashbang_pat.match(data)
    if not (m and 'python' in m.group().lower()):
        return

    python = executable
    if on_win:
        python = '"%s"' % python
    new_data = hashbang_pat.sub('#!' + python.replace('\\', '\\\\'),
                                data, count=1)
    if new_data == data:
        return
    if verbose:
        print "Updating: %r" % path
    fo = open(path, 'w')
    fo.write(new_data)
    fo.close()
    os.chmod(path, 0755)


def fix_scripts(egg):
    for path in egg.files:
        if path.startswith(egg.bin_dir):
            fix_script(path)


if __name__ == '__main__':
    write_exe('cli.exe')
    write_exe('gui.exe', 'gui_scripts')
