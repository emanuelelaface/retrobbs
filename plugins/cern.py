import urllib

import time

import io
import numpy
import skimage.color
import skimage.io
import skimage.transform
from PIL import Image

from common import turbo56k as TT
from common import connection
from common.imgcvt import convert_To, cropmodes, PreProcess, gfxmodes, dithertype, get_ColorIndex
from common.filetools import SendBitmap


###############
# Plugin setup
###############
def setup():
    fname = "CERN" #UPPERCASE function name for config.ini
    parpairs = [] #config.ini Parameter pairs (name,defaultvalue)
    return(fname,parpairs)

##################################################
# Plugin function
##################################################
def plugFunction(conn:connection.Connection):
    url = 'https://vistar-capture.s3.cern.ch/lhc1.png'
    r = urllib.request.urlopen(url)
    image_data = io.BytesIO(r.read())
    image = skimage.io.imread(image_data)
    if image.shape[2] == 4:
        # Discard alpha channel
        image = image[:, :, :3]
    target_shape = (200, 320, 3)
    if image.shape != target_shape:
        # Resize image if necessary
        image = skimage.transform.resize(image, target_shape, order=3)
    img = Image.fromarray((image * 255).astype(numpy.uint8))
    SendBitmap(conn,img,gfxmode=gfxmodes.C64HI,preproc=PreProcess(contrast=1.5,saturation=1.5),dither=dithertype.NONE)

    if conn.ReceiveKey(b'\rX') == b'X':
        return

    conn.SendTML('<SPINNER><CRSRL>')

    time.sleep(1)
    conn.socket.settimeout(conn.bbs.TOut)

