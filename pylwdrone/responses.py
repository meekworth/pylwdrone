import calendar
import datetime
import enum
import math
import struct

from pylwdrone import utils
from pylwdrone.command import CameraFlip
from pylwdrone.command import CommandType

class Config(object):
    """Class to represent the returned configuration information from the
    drone camera."""
    _LEN = 140
    MAX_WIFI_NAME_LEN = 32
    MAX_WIFI_PASS_LEN = 32

    @property
    def camera_flip(self):
        """element of CameraFlip enum"""
        return self._flip

    @camera_flip.setter
    def camera_flip(self, camflip):
        """set camera orientation with a value from the CameraFlip enum"""
        self._flip = camflip
        return

    @property
    def sdcard_free(self):
        """free bytes on SD card"""
        return self._sdc_free

    @property
    def sdcard_ismounted(self):
        """SD card mount status"""
        return self._sdc_mounted

    @property
    def sdcard_size(self):
        """total bytes on SD card"""
        return self._sdc_size

    @property
    def time(self):
        """datetime on camera"""
        return self._time

    @property
    def version(self):
        """camera software version"""
        return self._version

    @property
    def wifi_channel(self):
        """camera wifi channel"""
        return self._wifi_chan

    @wifi_channel.setter
    def wifi_channel(self, chan):
        """set wifi channel number in [1,13]"""
        if not 1 <= chan <= 13:
            raise ValueError('invalid WiFi channel')
        self._wifi_chan = chan
        return

    @property
    def wifi_name(self):
        """camera's wifi SSID"""
        return self._wifi_name

    @wifi_name.setter
    def wifi_name(self, name):
        """set camera's wifi SSID"""
        if len(name.encode()) > Config.MAX_WIFI_NAME_LEN:
            raise ValueError('WiFi name too long')
        self._wifi_name = name
        return

    @property
    def wifi_password(self):
        """camera's wifi password"""
        return self._wifi_pass

    @wifi_password.setter
    def wifi_password(self, passwd):
        """set camera's wifi password"""
        if len(passwd.encode()) > Config.MAX_WIFI_PASS_LEN:
            raise ValueError('WiFi password too long')
        self._wifi_pass = passwd
        return

    @property
    def wifi_security(self):
        """camera's security mode as ConfigWiFiSec"""
        return self._wifi_sec

    @wifi_security.setter
    def wifi_security(self, mode):
        """set camera's security mode as ConfigWiFiSec"""
        self._wifi_sec = mode
        return

    @property
    def wifi_security_name(self):
        """camera's security mode as a string"""
        if self._wifi_sec == ConfigWiFiSec.open:
            return 'open'
        elif self._wifi_sec == ConfigWiFiSec.wpa2_psk:
            return 'WPA2-PSK'
        else:
            raise ValueError('invalid wifi_sec field')
        return

    def to_bytes(self):
        """Returns packed bytes of the config, only sets the fields that can
        be changed."""
        data = bytearray(Config._LEN)
        struct.pack_into(
            '<BBB32s32s', data, 0, self._wifi_chan, self._flip.value,
            self._wifi_sec.value, self._wifi_name.encode(),
            self._wifi_pass.encode())
        return data

    @staticmethod
    def from_bytes(data):
        """Creates a Config instance from the given bytes"""
        if len(data) != Config._LEN:
            raise ValueError('invalid config length')
        fields = struct.unpack('<BBB32s32sQBQQ48s', data)
        (wifi_chan, flip, wifi_sec, wifi_name, wifi_pass, time,
            sdc_mounted, sdc_size, sdc_free, version) = fields
        conf = Config()
        conf._wifi_chan = wifi_chan
        conf._flip = CameraFlip(flip)
        conf._wifi_sec = ConfigWiFiSec(wifi_sec)
        conf._wifi_name = utils.cstr2str(wifi_name)
        conf._wifi_pass = utils.cstr2str(wifi_pass)
        conf._time = datetime.datetime.fromtimestamp(time)
        conf._sdc_mounted = sdc_mounted == 1
        conf._sdc_size = sdc_size
        conf._sdc_free = sdc_free
        conf._version = utils.cstr2str(version)
        return conf


class ConfigWiFiSec(enum.IntEnum):
    """Represents the available security modes for the camera's WiFi"""
    open = 0,
    wpa2_psk = 1


class FileFrameFlag(enum.IntEnum):
    """Represents frame types returned when downloading a file"""
    notfound = 0
    start = 1
    frame = 2
    end = 3


class FileFrame(object):
    """Class to represent a chunk of a file while downloading"""
    _HDR_LEN = 196
    _HDR_PATH_OFF = 16
    _HDR_PATH_MAX = 100
    _HDR_MD5_OFF = _HDR_PATH_OFF + _HDR_PATH_MAX
    _HDR_MD5_LEN = 32
    _HDR_FMT = f'<LLLL{_HDR_PATH_MAX}s{_HDR_MD5_LEN}s'

    @property
    def file_bytes(self):
        """bytes of this file chunk"""
        return self._file_bytes

    @property
    def flag(self):
        """file frame flag"""
        return self._flag

    @property
    def frame_size(self):
        """size of this file chunk"""
        return self._size

    @property
    def md5_hash(self):
        """md5 hash as a hex string, only valid on last file frame"""
        return self._md5

    @property
    def total_size(self):
        """total size of the downloading file"""
        return self._tot_size

    @staticmethod
    def from_bytes(data):
        """Creates a FileFrame instance from the given bytes"""
        fields = struct.unpack_from(FileFrame._HDR_FMT, data)
        flag, size, tot_size, _, path, md5 = fields
        fframe = FileFrame()
        fframe._flag = FileFrameFlag(flag)
        fframe._size = size
        fframe._tot_size = tot_size
        fframe._path = utils.cstr2str(path)
        fframe._md5 = md5.decode()
        fframe._file_bytes = data[FileFrame._HDR_LEN:]
        if len(fframe._file_bytes) != fframe._size:
            raise ValueError('incomple file segment')
        return fframe

    @staticmethod
    def req_header(path):
        """creates a header to request a file download"""
        path_bytes = path.encode()
        if len(path_bytes) > (FileFrame._HDR_PATH_MAX):
            raise ValueError('path too long')
        buf = bytearray(FileFrame._HDR_LEN)
        struct.pack_into(f'{FileFrame._HDR_PATH_MAX}s',
                         buf, FileFrame._HDR_PATH_OFF, path_bytes)
        return buf


class Heartbeat(object):
    """Class to represent a Heartbeat response from the camera."""
    _LEN = 64

    @property
    def client_size(self):
        """Client size (?)"""
        return self._client_size

    @property
    def sdcard_free(self):
        """Free space on SD card in bytes"""
        return self._sdc_free

    @property
    def sdcard_ismounted(self):
        """True if SD card is mounted"""
        return self._sdc_mounted

    @property
    def sdcard_size(self):
        """Total size of SD card in bytes"""
        return self._sdc_size

    @property
    def time(self):
        """Current datetime of camera"""
        return self._dt

    @staticmethod
    def from_bytes(data):
        """Creates a Heartbeat instance from the given bytes"""
        if len(data) != Heartbeat._LEN:
            raise ValueError('invalid data length for heartbeat')
        fields = struct.unpack('<IQQIQ32s', data)
        mounted, sdc_size, sdc_free, client_size, curr_time, _ = fields
        hb = Heartbeat()
        hb._sdc_mounted = mounted == 1
        hb._sdc_size = sdc_size
        hb._sdc_free = sdc_free
        hb._client_size = client_size
        # cam returns epoch in GMT+8, so need TZ=-8 to get back to UTC
        tz = datetime.timezone(datetime.timedelta(hours=-8))
        dt = datetime.datetime.fromtimestamp(curr_time, tz)
        hb._dt = dt.replace(tzinfo=datetime.timezone.utc)
        return hb


class Picture(object):
    """Class to represent a JPG picture from the camera."""
    _HDR_LEN = 128
    _PATH_MAX = 100

    @property
    def data(self):
        """image data"""
        return self._data

    @property
    def path(self):
        """remote path of the saved image"""
        return self._path

    @property
    def size(self):
        """size in bytes of the image"""
        return self._size

    @property
    def time(self):
        """time the image was taken"""
        return self._time

    @staticmethod
    def from_bytes(data):
        """Creates a Picture instance from the given bytes"""
        fields = struct.unpack_from(f'<LLL{Picture._PATH_MAX}s', data)
        size, time_ms, _, path = fields
        pic = Picture()
        pic._size = size
        pic._time = utils.secs_to_time(time_ms // 1000)
        pic._path = utils.cstr2str(path)
        pic._data = data[Picture._HDR_LEN:]
        return pic


class PictureListItem(object):
    """Class to represent an item in a list of pictures present on the
    camera's SD card. It does not contain the actual picture data."""
    _LEN = 124
    _PATH_MAX = 100

    def __init__(self, size, path):
        """initialize the object with the given parameters"""
        self._size = size
        self._path = path
        return

    @property
    def path(self):
        """remote path of picture"""
        return self._path

    @property
    def size(self):
        """size in bytes of picture"""
        return self._size

    @staticmethod
    def iter_from_bytes(data):
        """returns an iterator of PictureListItem instances from the given
        raw data"""
        if len(data) % PictureListItem._LEN != 0:
            raise ValueError('invalid picture list data')
        for i in range(0, len(data), PictureListItem._LEN):
            flag, size, _, path = struct.unpack_from(
                f'<LL16s{PictureListItem._PATH_MAX}s', data, i)
            if flag != 1:
                raise ValueError('invalid picture list entry')
            yield PictureListItem(size, utils.cstr2str(path))
        return


class RecordListItem(object):
    """Class to present a recording present on the camera's SD card. It does
    not contain the actual video data."""
    _LEN = 116
    _PATH_MAX = 100

    def __init__(self, start_time, time_len, path):
        """initialize the object with the given parameters"""
        self._start_time = start_time
        self._time_len = time_len
        self._path = path
        return

    @property
    def path(self):
        """remote path of the video recording"""
        return self._path

    @property
    def start_time(self):
        """start datetime in UTC of the video recording"""
        return self._start_time

    @property
    def time_length(self):
        """length in seconds of the video recording"""
        return self._time_len

    @staticmethod
    def iter_from_bytes(data):
        """returns an iterator of RecordListItem instances from the given
        raw data"""
        if len(data) % RecordListItem._LEN != 0:
            raise ValueError('invalid record list data')
        for i in range(0, len(data), RecordListItem._LEN):
            stime, tlen, _, path = struct.unpack_from(
                f'<LL8s{RecordListItem._PATH_MAX}s', data, i)
            # cam returns epoch in GMT+8, so need TZ=-8 to get back to UTC
            tz = datetime.timezone(datetime.timedelta(hours=-8))
            start = datetime.datetime.fromtimestamp(stime, tz)
            start = start.replace(tzinfo=datetime.timezone.utc)
            yield RecordListItem(start, tlen, utils.cstr2str(path))
        return


class RecordPlan(object):
    """Class to represent a Recording Plan for the camera."""
    _LEN = 20
    _DAY_ABBRS = [calendar.day_abbr[i]
                  for i in calendar.Calendar(calendar.SUNDAY).iterweekdays()]
    _DAY_NAMES = [calendar.day_name[i]
                  for i in calendar.Calendar(calendar.SUNDAY).iterweekdays()]

    def __init__(self, active=None, active_days=None, start_time=None,
                 end_time=None, max_duration_mins=None):
        """Create a RecordPlan object initialized from the given parameters.
        Defaults are set for any item not provided.

        Parameters:
            active - True/False
            active_days - array of day abbreviations (e.g. ['Sun', 'Mon']) or
                an integer where each enabled bit is an active day (e.g.
                0b0001011 is for Sun, Mon, Weds)
            start_time - start time of the day, 'HH:MM' or seconds
            end_time - start time of the day, 'HH:MM' or seconds
            max_duration_mins - total recording time in minutes

        Note: Setting the max duration does not seem to affect recording on
        version V202. It continuously records, rotating files at the
        configured interval."""
        fields = self._get_defaults()
        def_active, def_dayflags, def_stime, def_etime, def_maxdur = fields
        def_maxdur *= 60  # convert to secs

        # set instance variables to defaults first
        self._active = def_active == 1
        self._active_days = [(def_dayflags & (1 << i)) != 0 for i in range(7)]
        self._start_time = utils.secs_to_time(def_stime)
        self._end_time = utils.secs_to_time(def_etime)
        self._max_duration = def_maxdur

        # override any that were supplied as a parameter
        if active != None:
            self._active = active
        if active_days != None:
            if type(active_days) == int:
                self._active_days = [(active_days & (1 << i)) != 0
                                     for i in range(7)]
            else:
                self._active_days = [day in active_days
                                     for day in RecordPlan._DAY_ABBRS]
        if start_time != None:
            if type(start_time) == int:
                self._start_time = utils.secs_to_time(start_time)
            else:
                self._start_time = utils.hhmm_to_time(start_time)
        if end_time:
            if type(end_time) == int:
                self._end_time = utils.secs_to_time(end_time)
            else:
                self._end_time = utils.hhmm_to_time(end_time)
        if max_duration_mins:
            self._max_duration = max_duration_mins * 60
        return

    def _get_defaults(self):
        """Initial defaults to start recording now for 5 mins"""
        active = 1
        # camera's TZ is GMT+8
        tz = datetime.timezone(datetime.timedelta(hours=8))
        day_flags = 1 << (datetime.datetime.now(tz).isoweekday() % 7)
        # cover full 24-hr period so will cover "now" in any timezone
        start_time = 0
        end_time = 60*60*24 - 1  # 24 hrs
        max_dur = 5  # five mins
        return active, day_flags, start_time, end_time, max_dur

    @property
    def active_days(self):
        """list of seven boolean values (first is Sunday), true if recording
        on that day is enabled."""
        return self._active_days

    @property
    def active_days_abbr(self):
        """list of day name abbreviations for which recording is enabled"""
        return [RecordPlan._DAY_ABBRS[i]
                for i, active in enumerate(self._active_days) if active]

    @property
    def active_days_name(self):
        """list of full day names for which recording is enabled"""
        return [RecordPlan._DAY_NAMES[i]
                for i, active in enumerate(self._active_days) if active]

    @property
    def end_time(self):
        """datetime.time of the day to stop recording"""
        return self._end_time

    @property
    def is_active(self):
        """recording active state"""
        return self._active

    @property
    def max_duration(self):
        """maximum duration in seconds for recording"""
        return self._max_duration

    @property
    def start_time(self):
        """datetime.time of the day to start recording"""
        return self._start_time

    def to_bytes(self):
        """returns the packed bytes of this RecordPlan to send to the
        camera"""
        day_flags = 0
        for i, flag in enumerate(self._active_days):
            day_flags |= int(flag) << i
        return struct.pack(
            '<LLLLL', int(self._active), day_flags,
            utils.time_to_secs(self._start_time),
            utils.time_to_secs(self._end_time),
            self._max_duration)

    @staticmethod
    def from_bytes(data):
        """Creates a RecordPlan instance from the given bytes"""
        if len(data) != RecordPlan._LEN:
            raise ValueError('invalid data length for record plan')
        fields = struct.unpack_from('<LLLLL', data)
        active, dayflags, stime, etime, maxdur = fields
        return RecordPlan(bool(active), dayflags, stime, etime, maxdur)


class VideoFrame(object):
    """Class to represent an H264 frame returned from the camera while
    streaming."""
    _FRAME_OFF = 32
    STOP_CMDTYPE = CommandType.stopstream

    @property
    def frame_bytes(self):
        """raw bytes of the frame"""
        return self._frame_bytes

    @property
    def size(self):
        """size in bytes of frames"""
        return self._size

    @staticmethod
    def from_bytes(data):
        """Creates a VideoFrame instance from the given bytes"""
        flag, size, count, gphoto = struct.unpack_from('<LLQL', data)
        frame = VideoFrame._get_frame_bytes(
            data[VideoFrame._FRAME_OFF:], size, count)
        vframe = VideoFrame()
        vframe._flag = flag
        vframe._size = size
        vframe._count = count
        vframe._gphoto = gphoto
        vframe._frame_bytes = frame
        return vframe

    @staticmethod
    def _get_frame_bytes(data, size, count):
        def fix_byte(p1, p2):
            p2 &= 0xffffffff
            if (p2 & 1) == 0:
                v2 = (p2 + 1 + (p2 ^ p1)) ^ p2
            else:
                v2 = ((p2 ^ p1) + p2) ^ p2
            v1 = int(v2 / p2) if p2 != 0 else 0
            return (v2 - v1*p2) & 0xffffffff

        frame_bytes = bytearray(data)
        if len(frame_bytes) != size:
            raise ValueError('incomplete video frame')
        idx = fix_byte(count, size)
        if 0 <= idx < size:
            frame_bytes[idx] = ~frame_bytes[idx] & 0xff
        return frame_bytes


class ReplayFrame(VideoFrame):
    """Class to represent an H264 frame returned from the camera while
    replaying a video stream."""
    STOP_CMDTYPE = CommandType.stopreplay

    @property
    def frame_num(self):
        """frame number of the replay stream"""
        return self._frame_num

    @staticmethod
    def from_bytes(data):
        """Creates a ReplayFrame instance from the given bytes"""
        rframe = VideoFrame.from_bytes(data)
        frame_num, count2 = struct.unpack_from('<LL', rframe._frame_bytes)
        rframe._frame_num = frame_num
        rframe._count2 = count2
        rframe._frame_bytes = rframe._frame_bytes[8:]
        return rframe
