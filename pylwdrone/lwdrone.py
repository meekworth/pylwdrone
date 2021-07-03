import datetime
import hashlib
import io
import ipaddress
import socket
import struct
import threading

from pylwdrone.command import (
    CameraFlip,
    Command,
    CommandType,
)
from pylwdrone.defaults import *
from pylwdrone.responses import (
    Config,
    ConfigWiFiSec,
    FileFrame,
    FileFrameFlag,
    Heartbeat,
    Picture,
    PictureListItem,
    RecordListItem,
    RecordPlan,
    ReplayFrame,
    VideoFrame,
    VideoFrameUnmunger,
)

class LWDrone(object):
    """Class to represent a connection to the drone camera. It can be used for
    multiple actions, but have only one stream at a time.

    Example usage:
    >>> drone = LWDrone()
    >>> drone.set_time()
    >>> with open('out.h264', 'wb') as fp:
    >>>     for frame in drone.start_video_stream():
    >>>         fp.write(frame.frame_bytes)
    """
    _CONNECT_TIMEOUT = 15
    _STREAM_HB_PERIOD = 1

    def __init__(self, ip=CAM_IP,
                 cmd_port=CMD_PORT, stream_port=STREAM_PORT):
        """Set the drone camera's IP and ports."""
        ip = str(ipaddress.ip_address(ip))
        self._cmd_addr = (ip, cmd_port)
        self._stream_addr = (ip, stream_port)
        self._lasttime = 0
        self._streaming = False
        self._streaming_lock = threading.Lock()
        return

    def delete_file(self, path):
        """Delete a remote file"""
        body = struct.pack('100s', path.encode())
        cmd = Command(CommandType.delfile, body)
        rcmd = self._send_cmd(cmd)
        return rcmd.get_arg(Command.HDR_ARG_ARG1) == 0

    def get_baudrate(self):
        """Returns current baudrate for the drone's flight control"""
        cmd = Command(CommandType.getbaudrate)
        rcmd = self._send_cmd(cmd)
        return rcmd.get_arg(Command.HDR_ARG_ARG1)

    def get_camera_flip(self):
        """Returns the CameraFlip element representing the camera's
        orientation"""
        cmd = Command(CommandType.getcamflip)
        rcmd = self._send_cmd(cmd)
        return CameraFlip(rcmd.get_arg(Command.HDR_ARG_ARG1))

    def get_config(self):
        """Returns a Config instance of the camera's configuration"""
        cmd = Command(CommandType.getconfig)
        rcmd = self._send_cmd(cmd)
        return Config.from_bytes(rcmd.body)

    def get_file(self, path, outfp):
        """Download a file from the camera's filesystem. `path` must be
        a full path, and the result is written to the writeable object
        `outfp`. Returns true if the supplied MD5 matches the received
        file. Raises FileNotFoundError if the file doesn't exist."""
        body = FileFrame.req_header(path)
        cmd = Command(CommandType.getfile, body)
        md5 = hashlib.md5()
        rmd5 = None
        started = False
        if not self._compare_and_set_streaming(False, True):
            return False
        for frame in self._stream_loop(cmd, FileFrame):
            if frame.flag == FileFrameFlag.start and not started:
                started = True
            elif frame.flag == FileFrameFlag.frame and started:
                outfp.write(frame.file_bytes)
                md5.update(frame.file_bytes)
            elif frame.flag == FileFrameFlag.end and started:
                rmd5 = frame.md5_hash
                break
            elif frame.flag == FileFrameFlag.notfound:
                raise FileNotFoundError('remote file not found')
            else:
                raise ValueError('invalid file download state')
        self._compare_and_set_streaming(True, False)
        if md5.hexdigest() != rmd5:
            return False
        return True

    def get_heartbeat(self):
        """Send a heartbeat and return a Heartbeat reponse instance containing
        some state information."""
        cmd = Command(CommandType.heartbeat)
        rcmd = self._send_cmd(cmd)
        return Heartbeat.from_bytes(rcmd.body)

    def get_record_plan(self):
        """Returns a RecordPlan instance with the current recording plan"""
        cmd = Command(CommandType.getrecplan)
        rcmd = self._send_cmd(cmd)
        return RecordPlan.from_bytes(rcmd.body)

    def get_record_rotate_duration(self):
        """Returns the recording rotation time (maximum length of each file)
        in seconds"""
        cmd = Command(CommandType.getrectime)
        rcmd = self._send_cmd(cmd)
        return rcmd.get_arg(Command.HDR_ARG_ARG1) * 60

    def get_recordings(self):
        """Returns a list of recordings the camera is tracking. The returned
        list might list all recordings present on the SD card if the tracking
        file was cleared from a reboot."""
        dt = datetime.datetime.now()
        t = int(dt.replace(year=dt.year + 10).timestamp())
        # pack values: channel number, type, max return, max date, zeros
        body = struct.pack('<LLLLL', 1, 1, 255, t, 0)
        cmd = Command(CommandType.getreclist, body)
        rcmd = self._send_cmd(cmd)
        return list(RecordListItem.iter_from_bytes(rcmd.body))

    def get_resolution(self):
        """Returns the camera's set resolution: '720p' or '1080p'"""
        cmd = Command(CommandType.get1080p)
        rcmd = self._send_cmd(cmd)
        return '1080p' if rcmd.get_arg(Command.HDR_ARG_ARG1) == 1 else '720p'

    def get_time(self):
        """Return a datetime of the camera's current time"""
        cmd = Command(CommandType.gettime)
        rcmd = self._send_cmd(cmd)
        tm, = struct.unpack('<Q', rcmd.body)
        return datetime.datetime.fromtimestamp(tm)

    def list_pictures(self):
        """Returns a list of pictures from /mnt/Photo (max 256)."""
        cmd = Command(CommandType.getpiclist)
        rcmd = self._send_cmd(cmd)
        if rcmd.get_arg(Command.HDR_ARG_ARG1) != 0:
            return None
        return list(PictureListItem.iter_from_bytes(rcmd.body))

    def list_pictures2(self, n):
        """Returns a list of up to `n` pictures from /mnt/Photo (max 512).
        Similar to `list_pictures()`, but the server implements this as a
        separate command."""
        if not 0 <= n <= 512:
            raise ValueError('invalid number for max pictures to list')
        cmd = Command(CommandType.getpiclist2)
        cmd.set_arg(Command.HDR_ARG_ARG1, n)
        rcmd = self._send_cmd(cmd)
        if rcmd.get_arg(Command.HDR_ARG_ARG1) != 0:
            return None
        return list(PictureListItem.iter_from_bytes(rcmd.body))

    def reformat_sd(self):
        """Reformats the SD card, wiping all the data"""
        cmd = Command(CommandType.reformatsd)
        rcmd = self._send_cmd(cmd)
        return rcmd.get_arg(Command.HDR_ARG_ARG1) == 0

    def restart_wifi(self):
        """Restart the camera's wifi. The wifi should shutdown 5 seconds after
        the response, and start 1 second later."""
        cmd = Command(CommandType.restartwifi)
        rcmd = self._send_cmd(cmd)
        return rcmd.get_arg(Command.HDR_ARG_ARG1) == 0

    def set_baudrate(self, rate):
        """Set baudrate for drone's flight control"""
        cmd = Command(CommandType.setbaudrate)
        cmd.set_arg(Command.HDR_ARG_ARG1, rate)
        rcmd = self._send_cmd(cmd)
        return rcmd.get_arg(Command.HDR_ARG_ARG1) == 0

    def set_camera_flip(self, flip):
        """Sets the camera orientation from the given CameraFlip element"""
        cmd = Command(CommandType.setcamflip)
        cmd.set_arg(Command.HDR_ARG_ARG1, flip.value)
        rcmd = self._send_cmd(cmd)
        return rcmd.get_arg(Command.HDR_ARG_ARG1) == 0

    def set_config(self, wifi_chan=None, wifi_name=None, wifi_pass=None,
                   wifi_sec=None, camflip=None):
        """Sets the settings available as arguments. Any not specified will
        keep the current value."""
        config = self.get_config()
        if wifi_chan:
            config.wifi_channel = wifi_chan
        if wifi_name != None:
            config.wifi_name = wifi_name
        if wifi_pass != None:
            config.wifi_pass = wifi_pass
            # force WPA if password is given
            config.wifi_security = ConfigWiFiSec.wpa2_psk
        if wifi_sec and not wifi_pass != None:
            if wifi_sec != ConfigWiFiSec.open.name:
                raise ValueError('enabling WiFi security requires a password')
            config.wifi_security = ConfigWiFiSec[wifi_sec]
        if camflip != None:
            config.camera_flip = camflip
        cmd = Command(CommandType.setconfig, config.to_bytes())
        rcmd = self._send_cmd(cmd)
        return rcmd.get_arg(Command.HDR_ARG_ARG1) == 0

    def set_record_plan(self, recplan=None):
        """Sets the recording plan from the RecordPlan instance."""
        if not recplan:
            recplan = RecordPlan()
        cmd = Command(CommandType.setrecplan, recplan.to_bytes())
        rcmd = self._send_cmd(cmd)
        return rcmd.get_arg(Command.HDR_ARG_ARG1) == 0

    def set_recording_rotate_duration(self, t):
        """Sets default recording length to t seconds (min 60, max 600).
        Change only seems to take affect after a server restart."""
        if not 60 <= t <= 600:
            raise ValueError('seconds is out of range')
        cmd = Command(CommandType.setrectime)
        cmd.set_arg(Command.HDR_ARG_ARG1, t // 60)
        rcmd = self._send_cmd(cmd)
        return rcmd.get_arg(Command.HDR_ARG_ARG1) == 0

    def set_resolution(self, res1080p):
        """True to set resolution to 1080p, false for 720p"""
        cmd = Command(CommandType.set1080p)
        cmd.set_arg(Command.HDR_ARG_ARG1, int(res1080p))
        rcmd = self._send_cmd(cmd)
        return rcmd.get_arg(Command.HDR_ARG_ARG1) == 0

    def set_time(self, dt=None):
        """Set the camera's time to the given datetime"""
        if not dt:
            dt = datetime.datetime.now()
        body = struct.pack('<Q', int(dt.timestamp()))
        cmd = Command(CommandType.settime, body)
        rcmd = self._send_cmd(cmd)
        return rcmd.get_arg(Command.HDR_ARG_ARG1) == 0

    def set_wifi_channel(self, chan):
        """Set the wifi channel"""
        if not 1 <= chan <= 13:
            raise ValueError('invalid wifi channel')
        cmd = Command(CommandType.setwifichan)
        cmd.set_arg(Command.HDR_ARG_ARG1, chan)
        rcmd = self._send_cmd(cmd)
        return rcmd.get_arg(Command.HDR_ARG_ARG1) == 0

    def set_wifi_defaults(self):
        """Set wifi defaults (no custom name, open access)"""
        cmd = Command(CommandType.setwifidefs)
        rcmd = self._send_cmd(cmd)
        return rcmd.get_arg(Command.HDR_ARG_ARG1) == 0

    def set_wifi_name(self, name):
        """Set wifi SSID"""
        body = name.encode()
        if len(body) > Config.MAX_WIFI_NAME_LEN:
            raise ValueError('wifi name too long')
        cmd = Command(CommandType.setwifiname, body)
        rcmd = self._send_cmd(cmd)
        return rcmd.get_arg(Command.HDR_ARG_ARG1) == 0

    def set_wifi_password(self, password):
        """Set wifi password"""
        p = password.encode()
        if len(p) > Config.MAX_WIFI_PASS_LEN:
            raise ValueError('wifi password too long')
        # first character is skipped, so prepend dummy byte
        body = struct.pack('s64s', b'_', p)
        cmd = Command(CommandType.setwifipass, body)
        rcmd = self._send_cmd(cmd)
        return rcmd.get_arg(Command.HDR_ARG_ARG1) == 0

    def start_recording_replay(self, index):
        """Start a stream to replay a recording at the given index (provided
        by `get_recordings()`)"""
        rec_list = self.get_recordings()
        if not 0 <= index < len(rec_list):
            raise ValueError(f'no video available at index {index}')
        rec = rec_list[index]
        body = struct.pack('<LL16s100s', int(rec.start_time.timestamp()),
                           int(rec.start_time.timestamp()) + rec.time_length,
                           b'', rec.path.encode())
        cmd = Command(CommandType.startreplay, body)
        if self._compare_and_set_streaming(False, True):
            for frame in self._stream_loop(cmd, ReplayFrame):
                yield frame
        return []

    def start_video_stream(self, highdef=True):
        """Start a live video stream"""
        cmd = Command(CommandType.startstream)
        cmd.set_arg(Command.HDR_ARG_ARG1, int(highdef))
        if self._compare_and_set_streaming(False, True):
            for frame in self._stream_loop(cmd, VideoFrame):
                yield frame
        return

    def stop_recording_replay(self):
        """Stop the replay recording stream"""
        return self._compare_and_set_streaming(True, False)

    def stop_video_stream(self):
        """Stop the live video stream"""
        return self._compare_and_set_streaming(True, False)

    def take_picture(self):
        """Take a picture, saving it to the SD card and returning the JPEG
        bytes."""
        cmd = Command(CommandType.takepic)
        rcmd = self._send_cmd(cmd)
        return Picture.from_bytes(rcmd.body)

    def take_picture2(self, save):
        """Take a picture, returning the JPEG bytes, with the option to save
        it to the SD card."""
        cmd = Command(CommandType.takepic2)
        cmd.set_arg(Command.HDR_ARG_ARG1, int(save))
        rcmd = self._send_cmd(cmd)
        return Picture.from_bytes(rcmd.body)

    def _compare_and_set_streaming(self, c, s):
        with self._streaming_lock:
            if self._streaming == c:
                self._streaming = s
                return True
        return False

    def _send_cmd(self, cmd):
        t = LWDrone._CONNECT_TIMEOUT
        with socket.create_connection(self._cmd_addr, timeout=t) as sock:
            cmd_bytes = cmd.to_bytes()
            sock.sendall(cmd_bytes)
            hdr_bytes = _recvall(sock, Command.HDR_LEN)
            hdr = Command.from_bytes(hdr_bytes)
            body_bytes = _recvall(sock, hdr.get_arg(Command.HDR_ARG_BODYSZ))
            hdr.body = body_bytes
        return hdr

    def _stream_loop(self, cmd, frame_cls):
        t = LWDrone._CONNECT_TIMEOUT
        hb_bytes = Command(CommandType.heartbeat).to_bytes()
        with socket.create_connection(self._stream_addr, timeout=t) as sock:
            cmd_bytes = cmd.to_bytes()
            sock.sendall(cmd_bytes)
            try:
                while self._streaming:
                    hdr, frame_packet = self._get_frame(sock)
                    if not frame_packet: # check for end of stream
                        break
                    stream_type = hdr.get_arg(Command.HDR_ARG_STREAM_TYPE)
                    dec1 = hdr.get_arg(Command.HDR_ARG_STREAM_DEC1)
                    dec2 = hdr.get_arg(Command.HDR_ARG_STREAM_DEC2)
                    fu = VideoFrameUnmunger(stream_type, dec1, dec2)
                    yield frame_cls.from_bytes(fu, frame_packet)
                    ts = datetime.datetime.now().timestamp()
                    if ts - self._lasttime > LWDrone._STREAM_HB_PERIOD:
                        sock.sendall(hb_bytes)
                        self._lasttime = ts
                stop_cmd = Command(frame_cls.STOP_CMDTYPE)
                sock.sendall(stop_cmd.to_bytes())
            except IOError:
                # assume stream is done on error
                pass
            self._compare_and_set_streaming(True, False)

    def _get_frame(self, sock):
        hdr_bytes = _recvall(sock, Command.HDR_LEN)
        hdr = Command.from_bytes(hdr_bytes)
        body_bytes = _recvall(sock, hdr.get_arg(Command.HDR_ARG_BODYSZ))
        if hdr.cmdtype == CommandType.heartbeat:
            # ignore heartbeat responses and just get next frame
            return self._get_frame(sock)
        if hdr.cmdtype == CommandType.retreplayend:
            return None, None
        return hdr, body_bytes


def _recvall(s, n):
    """Reads all requested bytes from socket, raises Exception otherwise"""
    with io.BytesIO() as buf:
        tot = 0
        while tot < n:
            data = s.recv(n - tot)
            if not data:
                break
            buf.write(data)
            tot += len(data)
        ret = buf.getvalue()
    if len(ret) != n:
        raise IOError('did not get enough bytes')
    return ret
