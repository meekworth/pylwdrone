import contextlib
import datetime
import os
import os.path
import sys

def cstr2str(cs, encoding='utf8'):
    """Convert a null-terminated C-string bytes to a Python string"""
    return cs.split(b'\0', 1)[0].decode(encoding)

def date_filename(ext='', prefix=''):
    """Return a filename named with the current datetime"""
    fmt = f'{prefix}%Y%m%d-%H%M%S.%f.{ext}'
    return datetime.datetime.now().strftime(fmt)

@contextlib.contextmanager
def fopen(filename=None):
    """Context manager to open a file to write in binary mode with the given
    filename, or use stdout if the filename is "-"."""
    if filename and filename != '-':
        fp = open(filename, 'wb')
    else:
        fp = sys.stdout.buffer
    try:
        yield fp
    except:
        if fp is not sys.stdout.buffer:
            fp.close()
    return

def hhmm_to_time(hhmm):
    """Convert HH:MM format to a datetime.time object"""
    return datetime.time.fromisoformat(hhmm)

def rotate_file(filename):
    """Moves file to next available "filename.###"."""
    i = 1
    newname = filename
    while os.path.exists(newname):
        newname = f'{filename}.{i:03}'
        i += 1
    if filename != newname:
        os.rename(filename, newname)
    return

def secs_to_time(t):
    """Convert seconds to a datetime.time object"""
    if t >= 86400:
        raise ValueError('seconds must be < 86400')
    h = int(t/86400 * 24)
    m = int((t % 3600) / 60)
    s = t % 60
    return datetime.time(hour=h, minute=m, second=s)

def time_to_secs(t):
    """Convert a datetime.time object to seconds"""
    return t.hour*3600 + t.minute*60 + t.second
