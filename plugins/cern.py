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
    #url = 'http://hook.scumm.it/lhc1.png'
    r = urllib.request.urlopen(url)
    image_data = io.BytesIO(r.read())
    image = skimage.io.imread(image_data)
    split = []
    if image[530:,:image.shape[1]//2,:].sum() > 0:
        split.append(image[530:,:image.shape[1]//2,:]) # Status
    if image[530:,image.shape[1]//2:,:].sum() > 0:
        split.append(image[530:,image.shape[1]//2:,:]) # BIS
    if image[240:515,13:image.shape[1]//2,:].sum() > 0:
        split.append(image[240:515,13:image.shape[1]//2,:]) # Intensity
    if image[240:515,image.shape[1]//2:-13,:].sum() > 0:
        split.append(image[240:515,image.shape[1]//2:-13,:]) # Luminosity
    pics = []
    for img in split:
        if img.shape[2] == 4:
            img = img[:, :, :3]
        target_shape = (200, 320, 3)
        if img.shape != target_shape:
            img = skimage.transform.resize(img, target_shape, order=3)
        pics.append(Image.fromarray((img * 255).astype(numpy.uint8)))

    pic_pos = 0;
    while True:
        SendBitmap(conn,pics[pic_pos],gfxmode=gfxmodes.C64HI,preproc=PreProcess(contrast=1.5,saturation=1.5),dither=dithertype.NONE)

        sel = conn.ReceiveKey(' x')
        if sel == ' ':
            pic_pos = (pic_pos + 1)%len(pics)
            continue
        if sel == 'x':
            return()

    conn.SendTML('<SPINNER><CRSRL>')

    time.sleep(1)
    conn.socket.settimeout(conn.bbs.TOut)

