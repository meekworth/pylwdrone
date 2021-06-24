#!/usr/bin/env python3

import argparse
import datetime
import ipaddress
import os
import os.path
import sys

from pylwdrone import __version__
from pylwdrone import utils
from pylwdrone.command import CameraFlip
from pylwdrone.defaults import *
from pylwdrone.lwdrone import LWDrone
from pylwdrone.responses import ConfigWiFiSec
from pylwdrone.responses import RecordPlan

def main():
    args = _create_argparser().parse_args()
    drone = _get_drone(args)
    if 'func' not in args:
        print('incomplete command', file=sys.stderr)
        return 1
    try:
        ret = args.func(drone, args)
    except KeyboardInterrupt:
        ret = False
        if 'stop_func' in args:
            ret = args.stop_func(drone, args)
    if not ret:
        if not args.quiet:
            print('failure', file=sys.stderr)
        return 1
    if not args.quiet:
        sys.stdout.flush()
        print('success', file=sys.stderr)
    return 0

def _cmd_baudrate_get(drone, args):
    print(drone.get_baudrate())
    return True

def _cmd_baudrate_set(drone, args):
    return drone.set_baudrate(args.rate)

def _subparser_baudrate(subparsers):
    desc = 'control baud rate for drone\'s flight control'
    parser = subparsers.add_parser('baud', help=desc, description=desc)
    subp2 = parser.add_subparsers(title='baud rate commands', metavar='')

    parser = subp2.add_parser('get', help='get baud rate')
    parser.set_defaults(func=_cmd_baudrate_get)

    parser = subp2.add_parser('set', help='set buad rate')
    parser.set_defaults(func=_cmd_baudrate_set)
    parser.add_argument(
        'rate',
        type=int,
        choices=[1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200],
        help='buad rate value')
    return

def _cmd_camflip_get(drone, args):
    print(drone.get_camera_flip().name)
    return True

def _cmd_camflip_set(drone, args):
    return drone.set_camera_flip(CameraFlip[args.mode])

def _subparser_camflip(subparsers):
    desc = 'control camera image orientation'
    parser = subparsers.add_parser('camflip', help=desc, description=desc)
    subp2 = parser.add_subparsers(title='flip camera commands', metavar='')

    parser = subp2.add_parser('get', help='get image flip mode')
    parser.set_defaults(func=_cmd_camflip_get)

    parser = subp2.add_parser('set', help='set image flip mode')
    parser.set_defaults(func=_cmd_camflip_set)
    parser.add_argument(
        'mode',
        choices=list(e.name for e in CameraFlip),
        help='camera flip mode')
    return

def _cmd_config_get(drone, args):
    config = drone.get_config()
    print('Camera flip:   ', config.camera_flip.name)
    print('WiFi Channel:  ', config.wifi_channel)
    print('WiFi Security: ', config.wifi_security.name)
    print('WiFi Name:     ', config.wifi_name)
    print('WiFi Password: ', config.wifi_password)
    print('SD card ready: ', config.sdcard_ismounted)
    print('SD card size:  ', config.sdcard_size // 1024**2, 'MiB')
    print('SD card free:  ', config.sdcard_free // 1024**2, 'MiB')
    print('Version:       ', config.version)
    print('Current time:  ', config.time)
    return True

def _cmd_config_set(drone, args):
    flip = CameraFlip[args.camflip] if args.camflip else None
    return drone.set_config(args.wifi_channel, args.wifi_name,
                            args.wifi_password, args.wifi_security, flip)

def _subparser_config(subparsers):
    desc = 'get or set camera config'
    parser = subparsers.add_parser('config', help=desc, description=desc)
    subp2 = parser.add_subparsers(title='config commands', metavar='')

    parser = subp2.add_parser('get', help='get config')
    parser.set_defaults(func=_cmd_config_get)

    parser = subp2.add_parser('set', help='set config')
    parser.set_defaults(func=_cmd_config_set)
    parser.add_argument(
        '--wifi-channel',
        metavar='CHAN',
        type=int,
        choices=range(1, 14),
        help='set WiFi channel')
    parser.add_argument(
        '--wifi-name',
        metavar='NAME',
        help='set WiFi name')
    parser.add_argument(
        '--wifi-password',
        metavar='PASS',
        help='set WiFi password')
    parser.add_argument(
        '--wifi-security',
        choices=[e.name for e in ConfigWiFiSec],
        help='set WiFi security')
    parser.add_argument(
        '--camflip',
        choices=[e.name for e in CameraFlip],
        help='set camera orientation')
    return

def _cmd_file_delete(drone, args):
    return drone.delete_file(args.file)

def _cmd_file_get(drone, args):
    retsucc = True
    for file_ in args.files:
        dest = os.path.join(args.saveroot, file_.lstrip('/'))
        destdir = os.path.dirname(dest)
        if not os.path.exists(destdir):
            os.makedirs(destdir)
        utils.rotate_file(dest)

        with open(dest, 'wb') as fp:
            try:
                succ = drone.get_file(file_, fp)
            except FileNotFoundError as e:
                succ = False
                print(e, file=sys.stderr)
        if succ:
            print('file saved:', dest)
        else:
            retsucc = False
            if os.path.exists(dest):
                os.unlink(dest)
            print('download failed:', file_, file=sys.stderr)
    return retsucc

def _subparser_file(subparsers):
    desc = 'remote file command'
    parser = subparsers.add_parser('file', help=desc, description=desc)
    subp2 = parser.add_subparsers(title='file commands', metavar='')

    parser = subp2.add_parser('delete', help='delete remote file')
    parser.set_defaults(func=_cmd_file_delete)
    parser.add_argument(
        'file',
        metavar='FILE',
        help='remote file path and name to delete')

    parser = subp2.add_parser('get', help='get remote file')
    parser.set_defaults(func=_cmd_file_get)
    parser.add_argument(
        '--saveroot',
        metavar='PATH',
        default='.',
        help='save file as full path, starting at PATH (default ".")')
    parser.add_argument(
        'files',
        metavar='FILE',
        nargs='+',
        help='remote file path and name to download (multiple allowed)')
    return

def _cmd_heartbeat(drone, args):
    hb = drone.get_heartbeat()
    print('SD card ready:', hb.sdcard_ismounted)
    print('SD card size: ', hb.sdcard_size // 1024**2, 'MiB')
    print('SD card free: ', hb.sdcard_free // 1024**2, 'MiB')
    print('Client count: ', hb.client_count)
    print('Current time: ', hb.time.ctime(), 'UTC')
    return True

def _subparser_heartbeat(subparsers):
    desc = 'send heartbeat and receive some status information'
    parser = subparsers.add_parser('heartbeat', help=desc, description=desc)
    parser.set_defaults(func=_cmd_heartbeat)
    return

def _cmd_pic_list(drone, args):
    pics = drone.list_pictures()
    if pics == None:
        return False
    print('      size  path')
    for entry in pics:
        print(f'{entry.size:10}  {entry.path}')
    return True

def _cmd_pic_take(drone, args):
    pic = drone.take_picture()
    with utils.fopen(args.out_file) as fp:
        fp.write(pic.data)
    if args.out_file != '-':
        print(args.out_file)
    return True

def _subparser_pic(subparsers):
    desc = 'list saved pictures or take a picture'
    parser = subparsers.add_parser('pic', help=desc, description=desc)
    subp2 = parser.add_subparsers(title='pic commands', metavar='')

    parser = subp2.add_parser('list', help='list saved pictures')
    parser.set_defaults(func=_cmd_pic_list)

    parser = subp2.add_parser('take', help='take and download a picture')
    parser.set_defaults(func=_cmd_pic_take)
    parser.add_argument(
        '--out-file',
        metavar='FILE',
        default=utils.date_filename('jpg'),
        help='write photo to specified file ("-" for stdout)')
    return

def _cmd_pic2_list(drone, args):
    pics = drone.list_pictures2(args.count)
    if pics == None:
        return False
    print('      size  path')
    for entry in pics:
        print(f'{entry.size:10}  {entry.path}')
    return True

def _cmd_pic2_take(drone, args):
    pic = drone.take_picture2(args.save)
    with utils.fopen(args.out_file) as fp:
        fp.write(pic.data)
    if args.out_file != '-':
        print(args.out_file)
    return True

def _subparser_pic2(subparsers):
    desc = 'list saved pictures or take a picture (additional control)'
    parser = subparsers.add_parser('pic2', help=desc, description=desc)
    subp2 = parser.add_subparsers(title='pic commands', metavar='')

    parser = subp2.add_parser('list', help='list saved pictures')
    parser.set_defaults(func=_cmd_pic2_list)
    parser.add_argument(
        '--count',
        metavar='MAX',
        type=int,
        default=512,
        help='max number of entries to return (default 512)')

    parser = subp2.add_parser('take', help='take and download a picture')
    parser.set_defaults(func=_cmd_pic2_take)
    parser.add_argument(
        '--out-file',
        metavar='FILE',
        default=utils.date_filename('jpg'),
        help='write photo to specified file ("-" for stdout)')
    parser.add_argument(
        '--save',
        action='store_true',
        help=('in addition to returning the data, remotely save the picture '
              'on the SD card (default does not)'))
    return

def _cmd_record_list(drone, args):
    print('index  start              duration  path')
    for i, entry in enumerate(drone.get_recordings()):
        tm = entry.start_time.astimezone().strftime('%Y%m%d_%H:%M:%S')
        print(f'[{i:3}]  {tm}    {entry.time_length:6}  {entry.path}')
    return True

def _cmd_record_play(drone, args):
    if args.out_file != '-':
        print('streaming to:', args.out_file)
    with utils.fopen(args.out_file) as fp:
        for frame in drone.start_recording_replay(args.index):
            fp.write(frame.frame_bytes)
    return True

def _cmd_record_start(drone, args):
    if args.rotate_duration:
        drone.set_recording_rotate_duration(args.rotate_duration * 60)
    recplan = RecordPlan(
        active=True, active_days=args.days, start_time=args.start_time,
        end_time=args.stop_time, max_duration_mins=args.max_duration)
    return drone.set_record_plan(recplan)

def _cmd_record_status(drone, args):
    recplan = drone.get_record_plan()
    maxfile = drone.get_record_rotate_duration()
    print('Active:      ', recplan.is_active)
    print('Active Days: ', ', '.join(recplan.active_days_abbr))
    print('Start Time:  ', recplan.start_time.isoformat())
    print('End Time:    ', recplan.end_time.isoformat())
    print('Max Duration:', recplan.max_duration, 'secs')
    print('Max Per File:', maxfile, 'secs')
    return True

def _cmd_record_stop(drone, args):
    recplan = RecordPlan(active=False)
    return drone.set_record_plan(recplan)

def _cmd_record_stop_replay(drone, args):
    return drone.stop_recording_replay()

def _subparser_record(subparsers):
    desc = 'control video recording to the SD card'
    parser = subparsers.add_parser('rec', help=desc, description=desc)
    subp2 = parser.add_subparsers(title='recording commands', metavar='')

    parser = subp2.add_parser('list', help='list recordings')
    parser.set_defaults(func=_cmd_record_list)

    parser = subp2.add_parser('play', help='play saved recording')
    parser.set_defaults(func=_cmd_record_play)
    parser.set_defaults(stop_func=_cmd_record_stop_replay)
    parser.add_argument(
        '--out-file',
        metavar='FILE',
        default=utils.date_filename('h264'),
        help='write stream to file ("-" for stdout)')
    parser.add_argument(
        'index',
        type=int,
        help='file index # to play (from "record list" command)')

    parser = subp2.add_parser('start', help='start recording')
    parser.set_defaults(func=_cmd_record_start)
    # days doesn't actually matter in this version, lewei_cam just checks
    # if it's set
    parser.add_argument(
        '--days', metavar='DAY', nargs='+',
        choices=['Sun', 'Mon', 'Tues', 'Wed', 'Thurs', 'Fri', 'Sat'],
        help='record on specific days (default today)')
    parser.add_argument(
        '--max-duration',
        metavar='MINS',
        type=int,
        help='max recording duration')
    parser.add_argument(
        '--rotate-duration',
        metavar='MINS',
        type=int,
        help='max duration per file')
    parser.add_argument(
        '--start-time',
        metavar='HH:MM',
        help='recording start time (default 00:00)')
    parser.add_argument(
        '--stop-time',
        metavar='HH:MM',
        help='recording stop time (default 23:59)')

    parser = subp2.add_parser('status', help='get recording status')
    parser.set_defaults(func=_cmd_record_status)

    parser = subp2.add_parser('stop', help='stop recording')
    parser.set_defaults(func=_cmd_record_stop)
    return

def _cmd_reformat(drone, args):
    return drone.reformat_sd()

def _subparser_reformat(subparsers):
    desc = 'reformat SD card'
    parser = subparsers.add_parser('reformat', help=desc, description=desc)
    parser.set_defaults(func=_cmd_reformat)
    return

def _cmd_resolution_get(drone, args):
    print(drone.get_resolution())
    return True

def _cmd_resolution_set(drone, args):
    drone.set_resolution(args.mode == '1080p')
    return True

def _subparser_resolution(subparsers):
    desc = 'get or set camera resolution'
    parser = subparsers.add_parser('res', help=desc, description=desc)
    subp2 = parser.add_subparsers(title='resolution commands', metavar='')

    parser = subp2.add_parser('get', help='get resolution mode')
    parser.set_defaults(func=_cmd_resolution_get)

    parser = subp2.add_parser('set', help='set resolution mode')
    parser.set_defaults(func=_cmd_resolution_set)
    parser.add_argument(
        'mode',
        choices=['720p', '1080p'],
        help='resolution mode')
    return

def _cmd_stream_start(drone, args):
    if args.out_file != '-':
        print('streaming to:', args.out_file)
    with utils.fopen(args.out_file) as fp:
        for frame in drone.start_video_stream(not args.low_def):
            fp.write(frame.frame_bytes)
    return True

def _cmd_stream_stop(drone, args):
    return drone.stop_video_stream()

def _subparser_stream(subparsers):
    desc = 'control video streaming'
    parser = subparsers.add_parser('stream', help=desc, description=desc)
    subp2 = parser.add_subparsers(title='streaming commands', metavar='')

    parser = subp2.add_parser('start', help='start streaming')
    parser.set_defaults(func=_cmd_stream_start)
    parser.set_defaults(stop_func=_cmd_stream_stop)
    parser.add_argument(
        '--low-def',
        action='store_true',
        help='stream at lower fps (and bps), and smaller resolution')
    parser.add_argument(
        '--out-file',
        metavar='FILE',
        default=utils.date_filename('h264'),
        help='write stream to file ("-" for stdout)')
    return

def _cmd_time_get(drone, args):
    print(drone.get_time().ctime())
    return True

def _cmd_time_set(drone, args):
    dt = datetime.datetime.fromisoformat(args.time) if args.time else None
    return drone.set_time(dt)

def _subparser_time(subparsers):
    desc = 'get or set remote time'
    parser = subparsers.add_parser('time', help=desc, description=desc)
    subp2 = parser.add_subparsers(title='time commands', metavar='')

    parser = subp2.add_parser('get', help='get remote time')
    parser.set_defaults(func=_cmd_time_get)

    parser = subp2.add_parser('set', help='set remote time')
    parser.set_defaults(func=_cmd_time_set)
    parser.add_argument(
        '--time',
        help='format YYYY-MM-DD[HH[:MM[:SS]]] (default current time)')
    return

def _cmd_wifi_restart(drone, args):
    return drone.restart_wifi()

def _cmd_wifi_set_channel(drone, args):
    return drone.set_wifi_channel(args.channel)

def _cmd_wifi_set_defaults(drone, args):
    return drone.set_wifi_defaults()

def _cmd_wifi_set_name(drone, args):
    return drone.set_wifi_name(args.name)

def _cmd_wifi_set_password(drone, args):
    return drone.set_wifi_password(args.password)

def _subparser_wifi(subparsers):
    desc = 'control camera\'s wifi'
    parser = subparsers.add_parser('wifi', help=desc, description=desc)
    subp2 = parser.add_subparsers(title='wifi commands', metavar='')

    parser = subp2.add_parser('restart', help='restart wifi')
    parser.set_defaults(func=_cmd_wifi_restart)

    parser = subp2.add_parser('set', help='wifi set commands')
    subp3 = parser.add_subparsers(title='wifi set commands', metavar='')
    parser = subp3.add_parser('channel', help='set wifi channel')
    parser.set_defaults(func=_cmd_wifi_set_channel)
    parser.add_argument('channel', metavar='CHAN', type=int,
                        choices=range(1, 14), help='wifi channel')
    parser = subp3.add_parser('defaults', help='set wifi defaults')
    parser.set_defaults(func=_cmd_wifi_set_defaults)
    parser = subp3.add_parser('name', help='set wifi name')
    parser.set_defaults(func=_cmd_wifi_set_name)
    parser.add_argument('name', metavar='NAME', help='wifi name')
    parser = subp3.add_parser('password', help='set wifi password')
    parser.set_defaults(func=_cmd_wifi_set_password)
    parser.add_argument('password', metavar='PASS', help='wifi password')
    return

def _get_drone(args):
    return LWDrone(args.ip, args.command_port, args.stream_port)

def _create_argparser():
    parser = argparse.ArgumentParser(
        prog=__package__,
        description='LW Drone Controller')
    parser.add_argument(
        '--ip',
        default=CAM_IP,
        type=ipaddress.ip_address,
        help='IP address of drone')
    parser.add_argument(
        '--command-port',
        default=CMD_PORT,
        metavar='PORT',
        type=int,
        help='drone command port')
    parser.add_argument(
        '--stream-port',
        default=STREAM_PORT,
        metavar='PORT',
        type=int,
        help='drone stream port')
    parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='don\'t print success/failure messages')
    parser.add_argument(
        '-v', '--version',
        action='version',
        version=__version__,
        help='print the version and exit')

    subparsers = parser.add_subparsers(title='drone cam cmds', metavar='')
    _subparser_baudrate(subparsers)
    _subparser_camflip(subparsers)
    _subparser_config(subparsers)
    _subparser_file(subparsers)
    _subparser_heartbeat(subparsers)
    _subparser_pic(subparsers)
    _subparser_pic2(subparsers)
    _subparser_record(subparsers)
    _subparser_reformat(subparsers)
    _subparser_resolution(subparsers)
    _subparser_stream(subparsers)
    _subparser_time(subparsers)
    _subparser_wifi(subparsers)
    return parser

if __name__ == '__main__':
    exit(main())
