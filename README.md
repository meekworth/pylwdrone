pylwdrone
=========

Python package to communicate with a drone's lewei camera module. This module
does not control the drone's flight yet.

## Example Command-line Usage

#### Stream live video
```
$ pylwdrone stream start --out-file - | ffplay -i -
```

#### Stream live video, without buffer or "lag"
```
$ pylwdrone stream start --out-file - | ffplay -i -fflags nobuffer -flags low_delay -probesize 32 -sync ext -
```

#### Record live video then replay later
```
$ pylwdrone rec start
$ pylwdrone rec stop
$ pylwdrone rec list
index  start              duration  path
[  0]  20200604_04:01:27        95  /mnt/Video/20200604-040126.mp4
[  1]  20200604_04:10:40        20  /mnt/Video/20200604-041040.mp4
success
$ pylwdrone rec play 0 --out-file - | ffplay -i -
```

## Example Module Usage

#### Creating the object
```
>>> import pylwdrone
>>> drone = pylwdrone.LWDrone()
```

#### Stream live video
```
>>> for frame in drone.start_video_stream():
>>>     sys.stdout.buffer.write(frame.frame_bytes)
```

#### Get a file
```
>>> with open('video.mp4', 'wb') as fp:
>>>     drone.get_file('/mnt/Video/20200604-041040.mp', fp)
```

#### Take a picture
```
>>> with open('picture.jpg', 'wb') as fp:
>>>     fp.write(drone.take_picture())
```
