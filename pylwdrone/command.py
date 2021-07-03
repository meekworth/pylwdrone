import enum
import struct

@enum.unique
class CameraFlip(enum.IntEnum):
    """Represents the camera orientation. 'up' is default, 'down' is flipped
    vertically, and 'mirror' is flipped horizontally."""
    up = 0,
    up_mirror = 1,
    down_mirror = 2,
    down = 3

@enum.unique
class CommandType(enum.IntEnum):
    """Commands supported by the camera's lewei_cam server."""
    heartbeat = 1
    startstream = 2 # stream
    stopstream = 3 # stream
    settime = 4
    gettime = 5
    getrecplan = 6
    getreclist = 8
    startreplay = 9 # stream
    stopreplay = 16 # stream
    setrecplan = 17
    getfile = 18 # stream
    takepic = 19
    delfile = 20
    reformatsd = 21
    setwifiname = 22
    setwifipass = 23
    setwifichan = 24
    restartwifi = 25
    setwifidefs = 32
    getcamflip = 33
    setcamflip = 34
    getbaudrate = 35
    setbaudrate = 36
    getconfig = 37
    setconfig = 38
    getpiclist = 39
    get1080p = 40
    set1080p = 41
    getpiclist2 = 42
    takepic2 = 43
    getrectime = 48
    setrectime = 49
    retstream = 257
    retreplay = 259
    retreplayend = 261
    retgetfile = 262

class Command(object):
    """Class to represent a command request and response for the camera
    server. The command consists of a header and optional body."""
    _HDR_MAGIC = b'lewei_cmd\x00'
    _HDR_NUM_INTS = 9
    _HDR_MAGIC_LEN = len(_HDR_MAGIC)
    _HDR_INTS_OFF = _HDR_MAGIC_LEN # starts right after magic bytes
    HDR_LEN = _HDR_MAGIC_LEN + _HDR_NUM_INTS*4
    _BODY_OFF = HDR_LEN

    # index of various int fields in header
    # _IDX_ is an index into all the ints of the header
    # _ARG_ is an index into the arg ints of the header (_IDX_ - 1)
    _HDR_IDX_CMD = 0
    HDR_ARG_ARG1 = 0
    HDR_ARG_BODYSZ = 2
    HDR_ARG_STREAM_TYPE = 3
    HDR_ARG_STREAM_DEC1 = 4
    HDR_ARG_STREAM_DEC2 = 5

    def __init__(self, cmdtype, body=b''):
        """Initialize a Command with the given type and optional body."""
        self._cmdtype = cmdtype
        self._args = [0 for _ in range(Command._HDR_NUM_INTS - 1)]
        self._args[Command.HDR_ARG_BODYSZ] = len(body)
        self._body = body
        return

    @property
    def body(self):
        """bytes of the command body"""
        return self._body

    @body.setter
    def body(self, data):
        """set the bytes for the command body"""
        self._body = data
        self._args[Command.HDR_ARG_BODYSZ] = len(data)
        return

    @property
    def cmdtype(self):
        """CommandType of the command"""
        return self._cmdtype

    def get_arg(self, i):
        """returns the integer from the command header at the given index,
        which should be one of Command.HDR_ARG_* values."""
        return self._args[i]

    def set_arg(self, i, arg):
        """sets an argument (integer) in the command header at the given
        index, which should be one of Command.HDR_ARG_* values."""
        self._args[i] = arg
        return

    def to_bytes(self):
        """returns the packed bytes of the Command object for sending to the
        camera"""
        buf = bytearray(Command.HDR_LEN + len(self._body))
        bufv = memoryview(buf)
        bufv[:Command._HDR_MAGIC_LEN] = Command._HDR_MAGIC
        struct.pack_into('<9I', bufv, Command._HDR_INTS_OFF,
                         self._cmdtype.value, *self._args)
        bufv[Command._BODY_OFF:] = self._body
        bufv.release()
        return bytes(buf)

    @staticmethod
    def from_bytes(data):
        """returns a Command instance from the raw bytes"""
        if not data or len(data) < Command.HDR_LEN:
            raise IOError('not enough bytes for header')

        datav = memoryview(data)
        hdr = datav[:Command.HDR_LEN]
        body = datav[Command.HDR_LEN:]
        if datav[:Command._HDR_MAGIC_LEN] != Command._HDR_MAGIC:
            raise ValueError('invalid magic bytes')

        ints = struct.unpack_from('<9I', hdr, Command._HDR_INTS_OFF)
        cmd = Command(CommandType(ints[Command._HDR_IDX_CMD]))
        cmd._args = list(ints[Command._HDR_IDX_CMD+1:])
        cmd._body = body
        return cmd
