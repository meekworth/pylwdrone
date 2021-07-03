import binascii
import calendar
import datetime
import enum
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
        try:
            conf._time = datetime.datetime.fromtimestamp(time)
        except OverflowError:
            # For V300, unsure what the 64-bit value is, but it can be
            # negative. For now, just ignore the invalid timestamp and set
            # to 0.
            conf._time = datetime.datetime.fromtimestamp(0)
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
    def client_count(self):
        """Number of clients connected for streaming"""
        return self._client_cnt

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
        mounted, sdc_size, sdc_free, client_cnt, curr_time, _ = fields
        hb = Heartbeat()
        hb._sdc_mounted = mounted == 1
        hb._sdc_size = sdc_size
        hb._sdc_free = sdc_free
        hb._client_cnt = client_cnt
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
    def from_bytes(su, data):
        """Creates a VideoFrame instance from the given bytes"""
        flag, size, count, gphoto = struct.unpack_from('<LLQL', data)
        frame = VideoFrame._get_frame_bytes(
            su, data[VideoFrame._FRAME_OFF:], size, count)
        vframe = VideoFrame()
        vframe._flag = flag
        vframe._size = size
        vframe._count = count
        vframe._gphoto = gphoto
        vframe._frame_bytes = frame
        return vframe

    @staticmethod
    def _get_frame_bytes(su, data, size, count):
        if len(data) != size:
            raise ValueError('incomplete video frame')
        frame_bytes = bytearray(data)
        su.unmunge(frame_bytes, size, count)
        return frame_bytes


class VideoFrameUnmunger(object):
    """Class to encapsulate parameters from the initial header for unmunging
    the video stream"""
    _TYPE_NONE = 0
    _TYPE_ONE = 1
    _TYPE_NEW = 129

    def __init__(self, stream_type, key1, key2):
        self._type = stream_type
        self._a = key1 & 0xffff
        self._b = (key1 >> 16) & 0xffff
        self._c = key2 & 0xffff
        return

    def unmunge(self, data, size, count):
        if self._type == VideoFrameUnmunger._TYPE_NEW:
            self._fix_midstream(data, size>>1, self._a, self._b, self._c)
        elif self._type == VideoFrameUnmunger._TYPE_ONE:
            idx = self._fix_byte(count, size)
            if 0 <= idx < size:
                data[idx] = ~data[idx] & 0xff
        return

    def _fix_byte(self, p1, p2):
        p2 &= 0xffffffff
        if (p2 & 1) == 0:
            v2 = (p2 + 1 + (p2 ^ p1)) ^ p2
        else:
            v2 = ((p2 ^ p1) + p2) ^ p2
        v1 = int(v2 / p2) if p2 != 0 else 0
        return (v2 - v1*p2) & 0xffffffff

    def _fix_midstream(self, data, idx, p1, p2, p3):
        for i, b in enumerate(VideoFrameUnmunger._MDATA1):
            if b == p1:
                data[idx] = i
                break
        for i, b in enumerate(VideoFrameUnmunger._MDATA2):
            if b == p2:
                data[idx+1] = data[idx] ^ i
                break
        for i, b in enumerate(VideoFrameUnmunger._MDATA3):
            if b == p3:
                data[idx+2] = data[idx] ^ data[idx+1] ^ i
                break
        return

    _MDATA1 = struct.unpack('<256H', binascii.unhexlify(
        '0000010008617b17515362711b7cab4a7a683b866d027801e706867bff55e50a'
        '432727456d08fe477e3c7a6cd93fc72e874aae403575277c9f0c8473690d8113'
        '5020e8202a631f7a7a7a201f04001c537540ef03c62267218b81a3449e554715'
        'b61c5a1eba2c8d4b681d4f77cf47861bf11516688e450730af6ac7009d17a643'
        '501eb417ab49ae47030dea7eb035994cc85751690951667f4271b426dd2e1624'
        '4a0b530f9e847d3e0d02ba879d1be8319d7246405d485e29825320070d61e068'
        'c524d0708d6d872013849f27af19b73e228112257407c5314a70266d7e57412d'
        '5564d84dec5db534bb3cc688a04bbf0aea19840284444106c37cb831127c6e7d'
        '466571801c140a307a7917083b471a89b76893658a5d9944574fdf541c37b181'
        '4966947e130bdd44de3cf607421f0821663a2737a325691f5e15006bca207723'
        'c837f705f96327782141c56ee621db3efa5af9395340da3e46788f163c140d89'
        '0339d151907b6c2fef090f39646b4e89d5303d53f76b551abd12306a3b292276'
        'ed6c7358f58048624038e87e1f07c90c472e490c011a0e49ba0d9c6aef1afc7b'
        '6b6014847c156541930cf919fb3bdc4f872d4361af5ec9258544811dab25525b'
        'de1a060c855527601f5464843e32d86ab849371cc05d0b6ba4525c2aee246e5a'
        'cb67aa1f465d5f21ef571e23122fe856fd5a0c0b7a23280ba85f3786de358e2e'))
    _MDATA2 = struct.unpack('<256H', binascii.unhexlify(
        '0000010064780174e6064a4be22abb0b13008b398b752b47d8564f4bb2529659'
        '7c58210e341f2656333e0167135ef0342305826154203d04f864d6542187d87a'
        '12835d15443fcb0e753911723f0fdf772838ba65cf011026544483838f3b5a88'
        '9b7f992bd2435e01b1609026ea3d2a687255cd17e86a2f3eb316f817bc17822f'
        '6901a73d6a6dbc012b4c7e771134683b4883ff6abf701f6596882c08ad4a1f7c'
        '61228070844db32f41509740875aa14d4a73ca260f897249c82088352930bd59'
        'd400ed33f480e51ff083d72c0a527a3587380745f76ba776643ffa5b17194868'
        '713bb25cfd38600aa611ed06547c8f63ee34b33c4f0be72dda479e62b56e796e'
        '00203058cd69fb59c046bc35348114350483a818a44eaa22000c611a4a0ab42f'
        '202b6550f625255f0f650f6df06b4f050d7d753ad84eeb799e2c2a267655dc5d'
        '515214624c4b94206717d604346416070121e519d0464380590dbf7ce44e6852'
        'c6006b6c82512c595b7c4f883e35631fc72b268044506c01340dab5330145d43'
        '9961040dd04bc088a61e860364400e37034292693345df61154e1e32002c1a18'
        '8040be2e23585f35bf47cc592c2089858750041c5a0cbe8796433c87893fd16f'
        'c58319456b25de83ef724334f656e16d1d64d3523512d622c906233772352265'
        'a55d672fd8034527b3883c20416a2e6c18871585cb25714f4e40c960d97c5b65'))
    _MDATA3 = struct.unpack('<256H', binascii.unhexlify(
        '00000100f648f37a4f6e148697430d00e94cf66cb585270b8b737916e47b0e49'
        'fa477536bc37117f194a9256955bf7564881ad8514169c1bad3bed14bc4ade10'
        'd2029f0e6702d05d9e54bd3b9b05955dbc27973611369f3aac464484b5015c7b'
        'f206a9002528b664704a874310257d28cc258f610980c5111471b056882f282a'
        'bb28204a3d0cce6ca043015bfd58bb12ef82785eb4692d35fb6f8c07bc2c484d'
        '4011770c45099f16b97f4456c8802f390c6124867f584711c588307e3520aa6d'
        'ab7cd925cf6241474d77ce714b19cc8764411c7da32f3e1b5d00f66a7c506821'
        '186f274ed468133d1e60a7119c86c6142f83c85cf52b8b141b69fd426125f906'
        'c144ee34ba009a758d22a90267178f3b06550f1eb581c76d3c01df63334f6173'
        '4c548e1cd672f2196559c845187ab784c46a5a6c195b0c4fd759694296839e0c'
        '2833131fd805b26a696b5f54ec2d2504741f9d61538763736e0d5e22b54e9558'
        'dd1db44e2e403a843510e686260ced131967fb546d516e2517100e5483845b49'
        'f10ab0578d61b00b9e58f45bf96e865923594039fe5f9a86cf3e9d6d0f4d6c5e'
        '2e8356578309dd378c0dd2586a329c521f33d751ac511b1c822624506c0d4d1c'
        'aa246929472fcd6ebe64790d6e2da4343a778d0449070885be179a7f3b1fc237'
        '0e51eb0501447b5f24011878697cc0037e3ae95cae0b43288e008f4fa9557848'))


class ReplayFrame(VideoFrame):
    """Class to represent an H264 frame returned from the camera while
    replaying a video stream."""
    STOP_CMDTYPE = CommandType.stopreplay

    @property
    def frame_num(self):
        """frame number of the replay stream"""
        return self._frame_num

    @staticmethod
    def from_bytes(su, data):
        """Creates a ReplayFrame instance from the given bytes"""
        rframe = ReplayFrame()
        # just copy over the fields from the temp superclass instance
        vframe = VideoFrame.from_bytes(su, data)
        rframe._flag = vframe._flag
        rframe._size = vframe._size
        rframe._count = vframe._count
        rframe._gphoto = vframe._gphoto
        rframe._frame_bytes = vframe._frame_bytes[8:]

        frame_num, count2 = struct.unpack_from('<LL', vframe._frame_bytes)
        rframe._frame_num = frame_num
        rframe._count2 = count2
        return rframe
